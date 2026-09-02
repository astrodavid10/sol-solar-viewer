"""Validate a published data tree (local directory or live URL).

Runs in CI with ``--strict`` so a bad product is not served.  Two entry points,
and the difference between them is the whole failure policy:

* :func:`validate_products` judges ONE PRODUCT AT A TIME and returns a
  :class:`Report` each.  ``cmd_all`` runs it over a staging-over-published
  overlay (:func:`overlay_tree`) BEFORE the promote, so a product that fails
  can be rolled back on its own and the rest still publish.  This exists
  because all-or-nothing validation after the promote is what turned one bad
  record in someone else's feed into six stale products, twice: footgun 50
  (a frozen seed set's ar_index running off the end of a shrinking NOAA
  region list) and footgun 51 (NOAA keying a sunspot at latitude 98).
* :func:`validate` ANDs the lot for a tree that is already published, which
  is what ``python -m pipeline validate`` and the ``--url`` path want.

The checks are ordered cheapest-first and each one exists because getting it
wrong produces a *silent* visual bug rather than an error:

1. schema/keys      -- app pins on ``schema``; a rename must fail loudly.
2. topology.bin     -- monotone offsets, final offset == n_verts_total,
                       ar_index within regions.json bounds.
3. fNN.bin          -- magic, header agreement, EXACT byte length, polarity in
                       {-1,0,1}, valid in {0,1}.
4. dequantization   -- declared round-trip error under 1e-4 R_sun and every
                       valid line's radii inside [0.99, 2.61] (a line outside
                       that is a frame/units bug, e.g. meters for R_sun).
5. cross-frame      -- identical n_lines and n_verts_total in EVERY frame; this
                       is the morph guarantee, and violating it makes the GPU
                       lerp read a neighboring line's vertices.
6. matrices         -- orthonormal, det +1, and equal to the closed form
                       mat3_hci . Rz(hci_rot_deg); catches a sunpy frame change.
7. quaternion       -- Rotation.from_quat(q).as_matrix() == mat3; catches an
                       x,y,z,w vs w,x,y,z mixup, which would look like a
                       plausible-but-wrong rotation.
8. texture          -- schema/keys, the JPEG actually decodes at the declared
                       size, byte budget, sub_earth longitude in [0, 360), and
                       the observation age AT GENERATION TIME (both timestamps
                       live in the file, so the answer never drifts with the
                       wall clock the way "now - obs_iso" would). Each
                       layer's opt-in `high_res` block (schema /4) gets the
                       same JPEG checks when present, and is skipped cleanly
                       when absent -- additive only, most trees will not
                       have run with --with-hires.
"""

from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path
from typing import (Callable, Dict, Iterable, List, NamedTuple, Optional, Set,
                    Tuple)
from urllib.parse import urljoin

import numpy as np

from .config import (CME_MIN_SPEED_KMS, EVENTS_MAX_BYTES,
                     EVENTS_WINDOW_SLACK_HOURS, LIM_RSUN, SCHEMA_AR,
                     SCHEMA_EPHEM, SCHEMA_EVENTS, SCHEMA_INDEX, SCHEMA_PFSS,
                     SCHEMA_STATS, SCHEMA_TEXTURE,
                     TEX_NEAR_W, TEX_NEAR_H, TEX_NEAR_CDELT_DEG,
                     TEX_NEAR_LON_SPAN_DEG, TEX_NEAR_MAX_BYTES,
                     TEX_HIRES_H,
                     TEX_HIRES_MAX_BYTES, TEX_HIRES_W, TEX_MAX_BYTES,
                     TEX_MAX_OBS_AGE_HOURS, TEX_OFFLIMB_MAX_BYTES,
                     TEX_OUT_H, TEX_OUT_W, TEX_HIST_H, TEX_HIST_W,
                     TEX_HIST_MAX_BYTES, TEX_HIST_TOLERANCE_HOURS,
                     WIND_BIN_MINUTES, WINDOW_HOURS)
from .io_utils import age_hours, http_get, http_size, parse_iso_z
from .manifest_urls import iter_manifest_urls, manifest_url_set
from .pfss.export import (MAX_DEQUANT_ERR, dequantize, frame_bytes_expected,
                          topology_bytes_expected, unpack_frame,
                          unpack_topology)

MATRIX_TOL = 1e-9
R_MIN, R_MAX = 0.99, 2.61


class Report:
    """Accumulates pass/fail lines; ``ok`` is False if anything failed."""

    def __init__(self, verbose: bool = False) -> None:
        self.lines: List[str] = []
        self.failures = 0
        self.warnings = 0
        self.verbose = verbose

    def check(self, cond: bool, label: str, detail: str = "") -> bool:
        if cond:
            self.lines.append("  PASS  {0}".format(label))
        else:
            self.failures += 1
            self.lines.append("  FAIL  {0}{1}".format(
                label, "  -- " + detail if detail else ""))
        return bool(cond)

    def warn(self, label: str) -> None:
        self.warnings += 1
        self.lines.append("  WARN  {0}".format(label))

    def info(self, label: str) -> None:
        if self.verbose:
            self.lines.append("  ..    {0}".format(label))

    @property
    def ok(self) -> bool:
        return self.failures == 0

    def text(self) -> str:
        return "\n".join(self.lines + [
            "  {0}: {1} check(s) failed, {2} warning(s)".format(
                "FAILED" if self.failures else "OK", self.failures,
                self.warnings)])


def _loader(root: Optional[str], base_url: Optional[str]
            ) -> Callable[[str], Optional[bytes]]:
    if base_url:
        base = base_url if base_url.endswith("/") else base_url + "/"

        def get_url(rel: str) -> Optional[bytes]:
            try:
                return http_get(urljoin(base, rel))
            except Exception:
                return None
        return get_url

    rootp = Path(root or ".")

    def get_file(rel: str) -> Optional[bytes]:
        p = rootp / rel
        try:
            return p.read_bytes()
        except OSError:
            return None
    return get_file


def _prober(root: Optional[str], base_url: Optional[str]
            ) -> Callable[[str], Optional[int]]:
    """Cheap "is this file there, and non-empty?" probe -> size or None.

    Separate from ``_loader`` because the existence pass covers EVERY file a
    manifest names -- 110 of them in the published tree, ~28 MB -- and the
    point is to assert presence without paying to download it.  Locally that
    is a ``stat``; over HTTP it is a HEAD with a ranged-GET fallback (see
    ``io_utils.http_size``).
    """
    if base_url:
        base = base_url if base_url.endswith("/") else base_url + "/"

        def probe_url(rel: str) -> Optional[int]:
            return http_size(urljoin(base, rel))
        return probe_url

    rootp = Path(root or ".")

    def probe_file(rel: str) -> Optional[int]:
        p = rootp / rel
        try:
            return p.stat().st_size if p.is_file() else None
        except OSError:
            return None
    return probe_file


def _json(get: Callable[[str], Optional[bytes]], rel: str) -> Optional[dict]:
    import json
    raw = get(rel)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return None


def _rz(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


# Where each product's manifest lives.  Also the product-name vocabulary
# ``cli.build_index`` uses for index entries, deliberately -- a per-product
# report keyed on anything else would need a translation table.
PRODUCT_MANIFESTS = {
    "pfss": "pfss/manifest.json",
    "active_regions": "ar/regions.json",
    "ephemeris": "ephem/spacecraft.json",
    "stats": "stats/summary.json",
    "texture": "texture/texture.json",
    "events": "events/events.json",
}

# Products that own data files next to their manifest, and the globs that say
# what "every file in this directory" means for the orphan check.  Anything
# matching and unreferenced is an orphan; anything not matching (the manifest
# itself, a .nojekyll) is not this check's business.
_PRODUCT_OWNED_GLOBS = {
    "pfss": ("*.bin",),
    "texture": ("*.jpg",),
}


def _check_referenced_files(rep: Report, probe: Callable[[str], Optional[int]],
                            product: str, doc: Optional[dict]) -> int:
    """Every file this manifest names is present and non-empty.

    THE CHEAP CHECK THAT WAS MISSING.  ``_check_texture_frames`` decodes three
    frames per channel of eighteen, so 60 of 110 referenced files were never
    looked at in any way -- delete a non-sampled history frame from a copy of
    the published tree and ``validate --strict`` passed.  Footgun 35's
    production failure was precisely that shape: a ``texture.json`` naming
    fifteen history frames of which four were on disk, exit code 0.

    It runs BEFORE the decode sampling and does not replace it: presence is a
    different question from "decodes at the declared size and is not blank",
    and this one is affordable for all 110 files where that one is not.

    Returns the number of files probed, so the coverage is never silent.
    """
    if not doc:
        return 0
    directory = PRODUCT_MANIFESTS[product].rpartition("/")[0]
    names = list(iter_manifest_urls(doc))
    missing, empty = [], []
    for name in names:
        size = probe("{0}/{1}".format(directory, name) if directory else name)
        if size is None:
            missing.append(name)
        elif size <= 0:
            empty.append(name)
    rep.check(not missing,
              "{0}: every file the manifest names is in the tree".format(
                  product),
              "{0} of {1} missing: {2}".format(len(missing), len(names),
                                               sorted(missing)[:8]))
    rep.check(not empty,
              "{0}: no referenced file is zero bytes".format(product),
              "{0}".format(sorted(empty)[:8]))
    rep.info("{0}: {1} referenced file(s) probed".format(product, len(names)))
    return len(names)


def _check_no_orphans(rep: Report, root: Optional[str], product: str,
                      doc: Optional[dict]) -> None:
    """No file in the product's directory is unreferenced by its manifest.

    ROOT MODE ONLY (there is no directory listing over HTTP) and POST-PROMOTE
    only: before the prune runs, an orphan is the NORMAL state -- the window
    slid, last run's oldest history frame is still on disk, and the pruner has
    not been called yet.  Asserting it there would fail every healthy run,
    which is why ``check_orphans`` is a parameter and defaults to off.

    Why it is a FAIL and not a warning: ``publish_gh_pages.sh`` rsyncs the
    tree, so an orphan is bytes served forever.  The 443 KB of schema-1 maps
    that survived two schema revisions is what that looks like when nobody
    checks.
    """
    if not doc or root is None:
        return
    globs = _PRODUCT_OWNED_GLOBS.get(product)
    if not globs:
        return
    directory = Path(root) / PRODUCT_MANIFESTS[product].rpartition("/")[0]
    if not directory.is_dir():
        return
    keep = manifest_url_set(doc)
    if not keep:
        # Same refusal as the pruner's: a manifest that named nothing would
        # make every file an orphan, and that is a manifest bug, not 110 of
        # them.  Other checks will have failed already.
        rep.warn("{0}: manifest references no files; orphan check "
                 "skipped".format(product))
        return
    orphans = sorted(p.name for g in globs for p in directory.glob(g)
                     if p.name not in keep)
    rep.check(not orphans,
              "{0}: no unreferenced files in {1}/".format(
                  product, directory.name),
              "{0} orphan(s): {1}".format(len(orphans), orphans[:8]))


def _check_index(rep: Report, idx: Optional[dict]) -> None:
    if not rep.check(idx is not None, "index.json present"):
        return
    rep.check(idx.get("schema") == SCHEMA_INDEX, "index.json schema",
              "got {0!r}".format(idx.get("schema")))
    for key in ("generated_iso", "generated_unix", "run_id", "products",
                "last_attempt_iso", "last_attempt_status"):
        rep.check(key in idx, "index.json has {0}".format(key))
    products = idx.get("products") or {}
    rep.check(isinstance(products, dict), "index.json products is an object")
    for name in ("pfss", "ephemeris", "active_regions", "stats", "texture",
                 "events"):
        entry = products.get(name)
        if not rep.check(isinstance(entry, dict),
                         "index.json products.{0}".format(name)):
            continue
        rep.check(entry.get("status") in ("ok", "degraded", "stale", "absent",
                                          "failed"),
                  "products.{0}.status".format(name),
                  "got {0!r}".format(entry.get("status")))
        rep.check(isinstance(entry.get("stale"), bool),
                  "products.{0}.stale is bool".format(name))
        age = entry.get("age_hours")
        rep.check(age is None or isinstance(age, (int, float)),
                  "products.{0}.age_hours numeric-or-null".format(name))
        # last_error is additive: present only when the stage RAISED this run
        # and the previously published copy is being served.  The pairing is
        # the check that matters -- an entry carrying a failure while claiming
        # `ok` is the exact lie this field was added to make impossible.
        err = entry.get("last_error")
        if err is not None:
            rep.check(isinstance(err, str) and err.strip(),
                      "products.{0}.last_error is a non-empty string".format(
                          name), "got {0!r}".format(err))
            rep.check(entry.get("status") != "ok",
                      "products.{0} does not claim ok while carrying a "
                      "last_error".format(name),
                      "status {0!r}, last_error {1!r}".format(
                          entry.get("status"), err))


_MANIFEST_KEYS = ("schema", "pipeline_version", "generated_iso",
                  "generated_unix", "run_id", "status", "newest_mag_iso",
                  "newest_mag_age_hours", "window_hours",
                  "frame_spacing_hours", "model", "quantization", "geometry",
                  "constants", "render_hints", "frames", "active_regions_url")
_FRAME_KEYS = ("index", "url", "bytes", "target_iso", "mag_iso", "mag_unix",
               "mag_file", "mag_age_hours", "carrington_rotation", "l0_deg",
               "b0_deg", "p_deg", "hci_rot_deg", "quat_carr_to_ecl",
               "mat3_carr_to_ecliptic_j2000", "mat3_heeq_to_ecliptic_j2000",
               "n_valid", "n_closed", "n_open_pos", "n_open_neg", "reused")


def _check_manifest_schema(rep: Report, man: dict) -> None:
    rep.check(man.get("schema") == SCHEMA_PFSS, "manifest schema",
              "got {0!r}".format(man.get("schema")))
    for key in _MANIFEST_KEYS:
        rep.check(key in man, "manifest has {0}".format(key))
    rep.check(man.get("status") in ("ok", "degraded"), "manifest status",
              "got {0!r}".format(man.get("status")))
    geom = man.get("geometry") or {}
    for key in ("frame", "units", "n_lines", "n_verts_total", "n_bg_lines",
                "seed_set_id", "topology_url", "topology_bytes",
                "verts_per_line"):
        rep.check(key in geom, "manifest geometry.{0}".format(key))
    q = ((man.get("quantization") or {}).get("xyz") or {})
    for key in ("dtype", "layout", "normalized", "limit_rsun", "scale",
                "offset", "decode", "max_error_rsun", "max_error_km"):
        rep.check(key in q, "manifest quantization.xyz.{0}".format(key))
    rep.check(abs(float(q.get("limit_rsun", 0)) - LIM_RSUN) < 1e-12,
              "quantization limit_rsun == {0}".format(LIM_RSUN))
    err = float(q.get("max_error_rsun", 1.0))
    rep.check(err < MAX_DEQUANT_ERR, "declared dequant error < 1e-4 R_sun",
              "{0:.3e}".format(err))
    hints = man.get("render_hints") or {}
    for key in ("colors", "opacity_model", "load_order",
                "recommended_first_frame"):
        rep.check(key in hints, "manifest render_hints.{0}".format(key))
    frames = man.get("frames") or []
    rep.check(len(frames) >= 1, "manifest has frames")
    for i, fr in enumerate(frames):
        missing = [k for k in _FRAME_KEYS if k not in fr]
        rep.check(not missing, "frame {0} keys complete".format(i),
                  "missing {0}".format(missing))
        rep.check(fr.get("index") == i, "frame {0} index matches order".format(i))
        rep.check(fr.get("url") == "f{0:02d}.bin".format(i),
                  "frame {0} url".format(i), "got {0!r}".format(fr.get("url")))
    ordered = all(frames[i]["mag_unix"] <= frames[i + 1]["mag_unix"]
                  for i in range(len(frames) - 1))
    rep.check(ordered, "frames ordered oldest -> newest")

    # newest_mag_unix is ADDITIVE (schema /2): a manifest written before it
    # existed simply has no key, and that is not a failure.  When it IS there
    # it must be the integer twin of newest_mag_iso, i.e. exactly the newest
    # frame's magnetogram time -- the stale path reports data_age_hours from
    # it, and a value that drifted from the frames would understate how old
    # the field the app is drawing actually is.
    nmu = man.get("newest_mag_unix")
    if nmu is None:
        rep.info("manifest has no newest_mag_unix (schema /1 manifest)")
    else:
        want = max((int(f["mag_unix"]) for f in frames if "mag_unix" in f),
                   default=None)
        rep.check(isinstance(nmu, int) and nmu == want,
                  "newest_mag_unix == max(frames[*].mag_unix)",
                  "manifest says {0!r}, frames say {1!r}".format(nmu, want))
        iso = parse_iso_z(man.get("newest_mag_iso") or "")
        if iso is not None:
            rep.check(abs(iso.timestamp() - float(nmu)) < 1.0,
                      "newest_mag_unix agrees with newest_mag_iso",
                      "{0} vs {1}".format(nmu, int(iso.timestamp())))


def _check_matrices(rep: Report, man: dict) -> None:
    from scipy.spatial.transform import Rotation
    hci = np.asarray((man.get("constants") or {})
                     .get("mat3_hci_to_ecliptic_j2000") or [],
                     dtype=float)
    if not rep.check(hci.size == 9, "constants.mat3_hci_to_ecliptic_j2000"):
        return
    hci = hci.reshape(3, 3)
    for fr in man.get("frames") or []:
        i = fr.get("index")
        carr = np.asarray(fr["mat3_carr_to_ecliptic_j2000"],
                          dtype=float).reshape(3, 3)
        heeq = np.asarray(fr["mat3_heeq_to_ecliptic_j2000"],
                          dtype=float).reshape(3, 3)
        for m, name in ((carr, "carr"), (heeq, "heeq")):
            det_err = abs(float(np.linalg.det(m)) - 1.0)
            orth_err = float(np.abs(m @ m.T - np.eye(3)).max())
            rep.check(det_err < MATRIX_TOL and orth_err < MATRIX_TOL,
                      "f{0:02d} mat3_{1} orthonormal det=+1".format(i, name),
                      "det_err {0:.2e} orth_err {1:.2e}".format(det_err,
                                                                orth_err))
        e_carr = float(np.abs(carr - hci @ _rz(fr["hci_rot_deg"])).max())
        rep.check(e_carr < MATRIX_TOL,
                  "f{0:02d} mat3_carr == mat3_hci . Rz(hci_rot)".format(i),
                  "{0:.3e}".format(e_carr))
        e_heeq = float(np.abs(
            heeq - hci @ _rz(fr["l0_deg"] + fr["hci_rot_deg"])).max())
        rep.check(e_heeq < MATRIX_TOL,
                  "f{0:02d} mat3_heeq == mat3_hci . Rz(l0+hci_rot)".format(i),
                  "{0:.3e}".format(e_heeq))
        q = np.asarray(fr["quat_carr_to_ecl"], dtype=float)
        rep.check(q.size == 4, "f{0:02d} quat length 4".format(i))
        if q.size == 4:
            e_q = float(np.abs(Rotation.from_quat(q).as_matrix() - carr).max())
            rep.check(e_q < 1e-9,
                      "f{0:02d} quat matches mat3 (x,y,z,w)".format(i),
                      "{0:.3e}".format(e_q))


def _check_binaries(rep: Report, get, man: dict, n_regions: Optional[int]
                    ) -> None:
    geom = man["geometry"]
    n_lines = int(geom["n_lines"])
    n_verts = int(geom["n_verts_total"])

    raw = get("pfss/" + geom.get("topology_url", "topology.bin"))
    if not rep.check(raw is not None, "topology.bin fetched"):
        return
    rep.check(len(raw) == topology_bytes_expected(n_lines),
              "topology.bin exact length",
              "{0} vs {1}".format(len(raw), topology_bytes_expected(n_lines)))
    rep.check(len(raw) == int(geom.get("topology_bytes", -1)),
              "topology_bytes matches manifest")
    try:
        topo = unpack_topology(raw)
    except Exception as exc:
        rep.check(False, "topology.bin parses", str(exc))
        return
    rep.check(topo["n_lines"] == n_lines, "topology n_lines == manifest")
    rep.check(topo["n_verts_total"] == n_verts,
              "topology n_verts_total == manifest")
    rep.check(topo["n_bg_lines"] == int(geom["n_bg_lines"]),
              "topology n_bg_lines == manifest")
    rep.check(topo["seed_set_id"] == geom["seed_set_id"],
              "topology seed_set_id == manifest")
    rep.check(topo["reserved"] == 0, "topology reserved == 0")
    off = topo["line_offset"].astype(np.int64)
    rep.check(bool(np.all(np.diff(off) >= 0)), "line_offset monotonic")
    rep.check(bool(np.all(np.diff(off) >= 2)),
              "every line has >= 2 vertices")
    rep.check(int(off[0]) == 0, "line_offset[0] == 0")
    rep.check(int(off[-1]) == n_verts, "line_offset[n_lines] == n_verts_total")
    ar = topo["ar_index"].astype(np.int64)
    lo, hi = int(ar.min()), int(ar.max())
    if n_regions is None:
        rep.warn("regions.json missing; ar_index upper bound unchecked")
        rep.check(lo >= -1, "ar_index >= -1", "min {0}".format(lo))
    else:
        rep.check(lo >= -1 and hi < max(1, n_regions),
                  "ar_index within regions.json bounds",
                  "range [{0},{1}] vs {2} regions".format(lo, hi, n_regions))
    rep.check(int((ar[:int(geom["n_bg_lines"])] == -1).all()),
              "first n_bg_lines rows are background (ar_index == -1)")

    nv = np.diff(off)
    per_vertex_line = np.repeat(np.arange(n_lines), nv)

    for fr in man["frames"]:
        i = int(fr["index"])
        blob = get("pfss/" + fr["url"])
        if not rep.check(blob is not None, "{0} fetched".format(fr["url"])):
            continue
        exp = frame_bytes_expected(n_lines, n_verts)
        if not rep.check(len(blob) == exp, "{0} exact length".format(fr["url"]),
                         "{0} vs {1}".format(len(blob), exp)):
            continue
        rep.check(len(blob) == int(fr["bytes"]),
                  "{0} bytes matches manifest".format(fr["url"]))
        try:
            f = unpack_frame(blob)
        except Exception as exc:
            rep.check(False, "{0} parses".format(fr["url"]), str(exc))
            continue
        rep.check(f["frame_index"] == i, "{0} frame_index".format(fr["url"]))
        rep.check(f["n_lines"] == n_lines,
                  "{0} n_lines == topology (morph guarantee)".format(fr["url"]))
        rep.check(f["n_verts_total"] == n_verts,
                  "{0} n_verts_total == topology (morph guarantee)".format(
                      fr["url"]))
        rep.check(f["mag_unix"] == int(fr["mag_unix"]),
                  "{0} mag_unix matches manifest".format(fr["url"]))
        rep.check(f["reserved"] == (0, 0), "{0} reserved == 0".format(fr["url"]))
        pol = f["pol"].astype(np.int64)
        valid = f["valid"].astype(np.int64)
        rep.check(bool(np.isin(pol, (-1, 0, 1)).all()),
                  "{0} polarity in {{-1,0,1}}".format(fr["url"]))
        rep.check(bool(np.isin(valid, (0, 1)).all()),
                  "{0} valid in {{0,1}}".format(fr["url"]))
        rep.check(int(valid.sum()) == int(fr["n_valid"]),
                  "{0} n_valid matches manifest".format(fr["url"]))
        counts = (int(((pol == 0) & (valid == 1)).sum()),
                  int(((pol > 0) & (valid == 1)).sum()),
                  int(((pol < 0) & (valid == 1)).sum()))
        rep.check(counts == (int(fr["n_closed"]), int(fr["n_open_pos"]),
                             int(fr["n_open_neg"])),
                  "{0} closed/open counts match manifest".format(fr["url"]))

        xyz = dequantize(f["xyz"]).reshape(-1, 3)
        rep.check(float(np.abs(xyz).max()) <= LIM_RSUN + 1e-9,
                  "{0} dequantized within +/-{1} R_sun".format(fr["url"],
                                                               LIM_RSUN))
        r = np.linalg.norm(xyz, axis=1)
        vmask = valid[per_vertex_line] == 1
        if vmask.any():
            rmin, rmax = float(r[vmask].min()), float(r[vmask].max())
            rep.check(R_MIN <= rmin and rmax <= R_MAX,
                      "{0} valid-line radii in [{1}, {2}] R_sun".format(
                          fr["url"], R_MIN, R_MAX),
                      "range [{0:.4f}, {1:.4f}]".format(rmin, rmax))


def _claims_present(idx: Optional[dict], name: str) -> bool:
    """True if index.json claims this product is currently being served.

    A legitimately degraded tree (Horizons down, GONG outage) says ``stale`` or
    ``absent`` there, and a missing file is then correct rather than a bug -- so
    only an ``ok``/``degraded`` claim makes absence a failure.  Without this,
    ``validate --strict`` in CI would refuse to publish during exactly the
    outages the failure policy exists to survive.
    """
    entry = ((idx or {}).get("products") or {}).get(name) or {}
    return entry.get("status") in ("ok", "degraded")


def _check_day_regions(rep: Report, day: dict) -> None:
    """One history day's region positions (schema sol.ar/3).

    These drive the surface markers and the shader spots once the sphere
    texture became time-aligned, so a wrong latitude or Carrington longitude
    draws a sunspot where there was none -- on top of imagery that shows the
    real one somewhere else. Nothing would raise; a guest would just see the
    label miss the spot.

    ``region_count`` is asserted against the array's own length because the two
    come from different code paths: the count is summed in ``sources.srs`` and
    the array is normalized in ``regions.export``.
    """
    date = day.get("date")
    regs = day.get("regions")
    if not isinstance(regs, list):
        rep.check(False, "history {0} regions is a list".format(date),
                  "got {0}".format(type(regs).__name__))
        return
    rep.check(len(regs) == int(day.get("region_count") or -1),
              "history {0}: regions array matches region_count".format(date),
              "{0} entries vs {1}".format(len(regs), day.get("region_count")))

    numbers = []
    for r in regs:
        if not isinstance(r, dict):
            rep.check(False, "history {0} region is an object".format(date))
            continue
        num = r.get("number")
        numbers.append(num)
        tag = "history {0} AR{1}".format(date, num)
        rep.check(isinstance(num, int) and num > 0,
                  "{0}: number is a positive int".format(tag),
                  "got {0!r}".format(num))
        lat = r.get("lat_deg")
        # Active regions live inside the activity belts; anything beyond +/-60
        # would be a parse error, not a sunspot.
        rep.check(isinstance(lat, (int, float)) and abs(float(lat)) <= 60.0,
                  "{0}: lat_deg within +/-60".format(tag),
                  "got {0!r}".format(lat))
        clon = r.get("carr_lon_deg")
        rep.check(isinstance(clon, (int, float))
                  and 0.0 <= float(clon) < 360.0,
                  "{0}: carr_lon_deg in [0, 360)".format(tag),
                  "got {0!r}".format(clon))
        lon = r.get("lon_deg")
        rep.check(isinstance(lon, (int, float)) and abs(float(lon)) <= 180.0,
                  "{0}: lon_deg within +/-180".format(tag),
                  "got {0!r}".format(lon))
        ns = r.get("n_spots")
        rep.check(isinstance(ns, int) and ns >= 0,
                  "{0}: n_spots is a non-negative int".format(tag),
                  "got {0!r}".format(ns))
        # A history day carries no seed_count on purpose: the frozen seed set
        # describes today's trace, and a number here would imply field lines
        # that were never traced for that day.
        rep.check("seed_count" not in r,
                  "{0}: carries no seed_count".format(tag),
                  "got {0!r}".format(r.get("seed_count")))
    rep.check(len(set(numbers)) == len(numbers),
              "history {0}: region numbers are unique".format(date),
              "got {0}".format(numbers))


def _check_region_history(rep: Report, regions: dict) -> None:
    """The per-UT-day counts schema sol.ar/2 added.

    An EMPTY history is legal, not a failure: solar_regions.json can be down,
    and the app falls back to the live count exactly as it did before the array
    existed.  What must never happen is a MALFORMED one -- the chip reads a
    number out of it and puts it on screen next to a date.
    """
    history = regions.get("history")
    if not isinstance(history, list):
        rep.check(False, "regions.json history is a list",
                  "got {0}".format(type(history).__name__))
        return
    if not history:
        rep.info("regions.json history is empty (SRS history unavailable)")
        return

    dates = [h.get("date") for h in history if isinstance(h, dict)]
    rep.check(len(dates) == len(history), "every history entry is an object")
    parsed = []
    for d in dates:
        try:
            parsed.append(datetime.strptime(str(d), "%Y-%m-%d").date())
        except (TypeError, ValueError):
            rep.check(False, "history date parses", "got {0!r}".format(d))
            return
    rep.check(parsed == sorted(parsed), "history is ordered oldest first")
    rep.check(len(set(parsed)) == len(parsed), "history dates are unique")

    for h in history:
        n_reg = h.get("region_count")
        n_spot = h.get("spot_count")
        n_spotted = h.get("spotted_region_count")
        ok = all(isinstance(v, int) and v >= 0 for v in (n_reg, n_spot,
                                                          n_spotted))
        rep.check(ok, "history {0} counts are non-negative ints".format(
            h.get("date")), "got {0!r}".format(h))
        if not ok:
            continue
        # A spotted region has at least one spot, so the spot total can never
        # be under the number of spotted regions -- the check that catches the
        # `or 1` flooring bug this array was written around.
        rep.check(n_spotted <= n_reg,
                  "history {0}: spotted <= total regions".format(h.get("date")),
                  "{0} spotted of {1}".format(n_spotted, n_reg))
        _check_day_regions(rep, h)
        rep.check(n_spot >= n_spotted,
                  "history {0}: spot count >= spotted regions".format(
                      h.get("date")),
                  "{0} spot(s), {1} spotted region(s)".format(n_spot,
                                                              n_spotted))


def _check_regions(rep: Report, get, idx: Optional[dict]) -> Optional[int]:
    """ar/regions.json.  Returns the region count, or None if it is absent.

    Split out of a combined `_check_side_products` so a per-product report can
    exist: footguns 50 and 51 are both "one bad record in this file discarded
    the five products CI had just built correctly", and that is only fixable if
    the checks are addressable one product at a time.
    """
    n_regions: Optional[int] = None
    regions = _json(get, "ar/regions.json")
    if regions is None:
        if _claims_present(idx, "active_regions"):
            rep.check(False, "ar/regions.json present (index says ok)")
        else:
            rep.info("ar/regions.json absent (index does not claim it)")
        return None
    rep.check(regions.get("schema") == SCHEMA_AR, "regions.json schema")
    rep.check(isinstance(regions.get("regions"), list),
              "regions.json regions is a list")
    n_regions = len(regions.get("regions") or [])
    rep.check(int(regions.get("count", -1)) == n_regions,
              "regions.json count matches array length")
    _check_region_history(rep, regions)
    return n_regions


def _region_count(get) -> Optional[int]:
    """Region count WITHOUT reporting anything -- the cross-product read.

    pfss and events both address ``ar/regions.json`` by position, so both need
    this number; neither owns the file, so neither may report on it.  Keeping
    the read silent is what stops a regions defect from appearing as a failure
    of its two consumers as well (which is how one bad latitude took down six
    products).
    """
    doc = _json(get, "ar/regions.json")
    if doc is None:
        return None
    return len(doc.get("regions") or [])


def _check_ephem(rep: Report, get, idx: Optional[dict]) -> None:
    ephem = _json(get, "ephem/spacecraft.json")
    if ephem is None:
        if _claims_present(idx, "ephemeris"):
            rep.check(False, "ephem/spacecraft.json present (index says ok)")
        else:
            rep.info("ephem/spacecraft.json absent (index does not claim it)")
    else:
        rep.check(ephem.get("schema") == SCHEMA_EPHEM, "spacecraft.json schema")
        epochs = ephem.get("epochs_unix") or []
        rep.check(len(epochs) >= 2, "spacecraft.json epochs_unix populated")
        for body in ephem.get("bodies") or []:
            rep.check(len(body.get("xyz_au") or []) == len(epochs),
                      "spacecraft {0} xyz_au length == epochs".format(
                          body.get("id")))
        ni = ephem.get("now_index")
        rep.check(isinstance(ni, int) and 0 <= ni < max(1, len(epochs)),
                  "spacecraft.json now_index in range")


def _check_stats(rep: Report, get, idx: Optional[dict]) -> None:
    stats = _json(get, "stats/summary.json")
    if stats is None:
        if _claims_present(idx, "stats"):
            rep.check(False, "stats/summary.json present (index says ok)")
        else:
            rep.info("stats/summary.json absent (index does not claim it)")
    else:
        rep.check(stats.get("schema") == SCHEMA_STATS, "summary.json schema")
        rep.check("carrington" in stats, "summary.json carrington block")
        _check_wind_window(rep, stats)


def _check_wind_window(rep: Report, stats: dict) -> None:
    """The rolling solar-wind series.

    Two invariants, and both exist because a timezone bug in this series is
    INVISIBLE: the chip draws whatever points it is handed, so a shifted
    timestamp just moves the trace under the playhead.  Measured 2026-09-02,
    the served digest was generated at 15:23:30Z and carried hourly bins out
    to 20:00Z -- five samples of solar wind that had not been measured yet --
    because ``parse_iso_z`` returned a naive datetime for NOAA's zone-less
    ``time_tag`` and ``unix_s`` read it as Central time.  Nothing raised: the
    cache merged the shifted keys, the counts matched, the bytes were fine.

    ORDER, because the app interpolates between neighbours and a series that
    steps backwards makes it read across the wrong pair.  ``_merge_wind_series``
    builds the array from ``sorted(dict.items())``, so this is a guard on the
    merge, not on the source.

    FUTURE, with one bin of slack.  A bin is labelled by its START, so a
    legitimately-stamped sample can never begin after the run's own clock --
    except by the run's own duration: ``generated_iso`` is stamped at process
    start and the stats stage can fetch an hour later on a slow PFSS run, which
    can legitimately roll one further bin into the series.  Anything beyond
    that is a zone error, not a race.  One bin (60 min) would still have caught
    four of the five poisoned points above.
    """
    win = stats.get("windWindow")
    if win is None:
        # A dead RTSW fetch costs the chip its history and nothing else; the
        # app falls back to the live reading it already polls.
        rep.info("summary.json has no windWindow (RTSW unavailable)")
        return
    if not rep.check(isinstance(win, dict), "summary.json windWindow is an "
                     "object", "got {0}".format(type(win).__name__)):
        return
    points = win.get("points")
    if not rep.check(isinstance(points, list), "windWindow.points is a list",
                     "got {0}".format(type(points).__name__)):
        return
    if not points:
        rep.info("windWindow.points is empty (cold wind cache)")
        return

    times = [p.get("t") for p in points if isinstance(p, dict)]
    rep.check(len(times) == len(points),
              "every windWindow point is an object",
              "{0} of {1}".format(len(times), len(points)))
    numeric = all(isinstance(t, (int, float)) for t in times)
    if not rep.check(numeric, "windWindow point timestamps are numeric"):
        return
    rep.check(all(times[i] < times[i + 1] for i in range(len(times) - 1)),
              "windWindow.points timestamps strictly increasing",
              "{0} point(s)".format(len(times)))

    gen = stats.get("generated_unix")
    if gen is None:
        g = parse_iso_z(stats.get("generated_iso") or "")
        gen = None if g is None else g.timestamp()
    if not rep.check(isinstance(gen, (int, float)),
                     "summary.json generated_unix is numeric",
                     "got {0!r}".format(stats.get("generated_unix"))):
        return
    slack = (float(win.get("bin_minutes") or WIND_BIN_MINUTES)) * 60.0
    newest = float(max(times))
    ahead_h = (newest - float(gen)) / 3600.0
    rep.check(newest <= float(gen) + slack,
              "windWindow newest point is not in the future "
              "(<= generated + {0:.0f} min)".format(slack / 60.0),
              "{0:.2f} h ahead of generated_iso".format(ahead_h))


_TEXTURE_KEYS = ("schema", "generated_iso", "generated_unix", "url", "width",
                 "height", "projection", "lon_at_u0_deg", "north_up",
                 "wavelength_angstrom", "obs_iso", "sub_earth_carr_lon_deg",
                 "sub_earth_lat_deg", "near_side_half_angle_deg", "far_side",
                 "far_side_max_age_hours", "source", "layers")


_EVENTS_KEYS = ("schema", "pipeline_version", "generated_iso",
                "generated_unix", "status", "source", "window_hours",
                "counts", "events")

# dir_ecl survives a JSON round-trip through io_utils' float rounding, so the
# re-derivation below cannot be held to MATRIX_TOL. Measured residuals on live
# data are ~2e-7; 1e-5 catches a real frame error (which would be degrees) with
# room to spare.
_DIR_TOL = 1e-5


def _check_events(rep: Report, get, idx: Optional[dict]) -> None:
    """events/events.json -- the flare + CME catalog.

    Every rule here exists because getting it wrong is SILENT: a bad
    window_hours puts marks off the end of the scrubber, a bad dir_ecl aims a
    CME into empty sky, and a broken AR join anchors an eruption nowhere. None
    of those would raise anywhere.
    """
    doc = _json(get, "events/events.json")
    if doc is None:
        if _claims_present(idx, "events"):
            rep.check(False, "events/events.json present (index says ok)")
        else:
            rep.info("events/events.json absent (index does not claim it)")
        return

    rep.check(doc.get("schema") == SCHEMA_EVENTS, "events.json schema",
              "got {0!r}".format(doc.get("schema")))
    missing = [k for k in _EVENTS_KEYS if k not in doc]
    rep.check(not missing, "events.json keys complete",
              "missing {0}".format(missing))

    # The app puts these marks on the SAME track as the field-line frames.
    rep.check(doc.get("window_hours") == WINDOW_HOURS,
              "events window_hours == WINDOW_HOURS ({0})".format(WINDOW_HOURS),
              "got {0!r}".format(doc.get("window_hours")))

    events = doc.get("events")
    if not rep.check(isinstance(events, list), "events is an array",
                     "got {0}".format(type(events).__name__)):
        return

    # An empty window is DATA, not failure -- the Sun really does go quiet.
    if not events:
        rep.info("events list is empty (a quiet window is a valid result)")

    gen_unix = doc.get("generated_unix")
    if isinstance(gen_unix, (int, float)):
        oldest = float(gen_unix) - (WINDOW_HOURS + EVENTS_WINDOW_SLACK_HOURS) * 3600.0
        newest = float(gen_unix) + 3600.0
    else:
        oldest = newest = None
        rep.check(False, "events generated_unix is numeric",
                  "got {0!r}".format(gen_unix))

    counts = doc.get("counts") or {}
    n_flares = sum(1 for e in events if isinstance(e, dict) and e.get("kind") == "flare")
    n_cmes = sum(1 for e in events if isinstance(e, dict) and e.get("kind") == "cme")
    rep.check(counts.get("flares") == n_flares and counts.get("cmes") == n_cmes,
              "events counts match the array",
              "counts say {0}/{1}, array has {2}/{3}".format(
                  counts.get("flares"), counts.get("cmes"), n_flares, n_cmes))

    ids = [e.get("id") for e in events if isinstance(e, dict)]
    rep.check(len(set(ids)) == len(ids), "event ids are unique",
              "{0} id(s), {1} distinct".format(len(ids), len(set(ids))))

    n_regions = len((_json(get, "ar/regions.json") or {}).get("regions") or [])
    bad_time = bad_dir = bad_kin = bad_index = 0

    for e in events:
        if not isinstance(e, dict):
            rep.check(False, "event is an object")
            continue

        when = e.get("peak_unix") if e.get("kind") == "flare" else e.get("start_unix")
        if oldest is not None:
            if not isinstance(when, (int, float)) or not (oldest <= float(when) <= newest):
                bad_time += 1

        # ar_index must address ar/regions.json, or be the explicit -1.
        ai = e.get("ar_index", -1)
        if not isinstance(ai, int) or ai < -1 or (ai >= 0 and ai >= n_regions):
            bad_index += 1

        if e.get("kind") != "cme":
            continue

        speed = e.get("speed_kms")
        half = e.get("half_angle_deg")
        if not (isinstance(speed, (int, float)) and CME_MIN_SPEED_KMS <= float(speed) <= 4000.0):
            bad_kin += 1
        elif not (isinstance(half, (int, float)) and 0.0 < float(half) < 90.0):
            bad_kin += 1

        # Re-derive dir_ecl from (lat_deg, lon_deg) the long way. This is the
        # free regression test the manifest matrices already get: if the HEEQ
        # convention ever flips sign or transposes, the residual is degrees,
        # not rounding.
        d = e.get("dir_ecl")
        lat, lon = e.get("lat_deg"), e.get("lon_deg")
        when_iso = e.get("start_iso")
        if (isinstance(d, list) and len(d) == 3
                and all(isinstance(c, (int, float)) for c in d)):
            norm = math.sqrt(sum(float(c) ** 2 for c in d))
            if abs(norm - 1.0) > _DIR_TOL:
                bad_dir += 1
                continue
            if (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
                    and isinstance(when_iso, str)):
                when_dt = parse_iso_z(when_iso)
                if when_dt is not None:
                    try:
                        from .events.export import heeq_to_ecliptic
                        want = heeq_to_ecliptic(float(lat), float(lon), when_dt)
                    except Exception:                          # noqa: BLE001
                        want = None                # no sunpy in this env
                    if want is not None:
                        err = max(abs(float(a) - b) for a, b in zip(d, want))
                        if err > _DIR_TOL:
                            bad_dir += 1
        else:
            bad_dir += 1

    rep.check(bad_time == 0, "every event is inside the published window",
              "{0} outside".format(bad_time))
    rep.check(bad_index == 0, "every ar_index addresses ar/regions.json or is -1",
              "{0} out of range (regions: {1})".format(bad_index, n_regions))
    rep.check(bad_kin == 0, "every CME has usable kinematics",
              "{0} with speed/half-angle out of range".format(bad_kin))
    rep.check(bad_dir == 0, "every CME dir_ecl is a unit vector and re-derives "
              "from its Stonyhurst lat/lon", "{0} mismatched".format(bad_dir))

    blob = get("events/events.json")
    if blob is not None:
        rep.check(len(blob) < EVENTS_MAX_BYTES,
                  "events.json under {0} bytes".format(EVENTS_MAX_BYTES),
                  "{0} bytes".format(len(blob)))


def _check_texture(rep: Report, get, idx: Optional[dict]) -> None:
    """texture.json + the JPEG it names."""
    doc = _json(get, "texture/texture.json")
    if doc is None:
        if _claims_present(idx, "texture"):
            rep.check(False, "texture/texture.json present (index says ok)")
        else:
            rep.info("texture/texture.json absent (index does not claim it)")
        return
    rep.check(doc.get("schema") == SCHEMA_TEXTURE, "texture.json schema",
              "got {0!r}".format(doc.get("schema")))
    missing = [k for k in _TEXTURE_KEYS if k not in doc]
    rep.check(not missing, "texture.json keys complete",
              "missing {0}".format(missing))

    w, h = doc.get("width"), doc.get("height")
    rep.check((w, h) == (TEX_OUT_W, TEX_OUT_H),
              "texture declared dimensions (newest frame)",
              "got {0}x{1}, expected {2}x{3}".format(w, h, TEX_OUT_W,
                                                     TEX_OUT_H))
    rep.check(doc.get("lon_at_u0_deg") == 0.0,
              "texture lon_at_u0_deg == 0 (column 0 is Carrington 0)",
              "got {0!r}".format(doc.get("lon_at_u0_deg")))
    rep.check(doc.get("north_up") is True, "texture north_up is true")
    lon = doc.get("sub_earth_carr_lon_deg")
    rep.check(isinstance(lon, (int, float)) and 0.0 <= float(lon) < 360.0,
              "texture sub_earth_carr_lon_deg in [0, 360)",
              "got {0!r}".format(lon))
    blat = doc.get("sub_earth_lat_deg")
    rep.check(isinstance(blat, (int, float)) and abs(float(blat)) <= 7.5,
              "texture sub_earth_lat_deg within +/-7.5 (B0 range)",
              "got {0!r}".format(blat))
    rep.check(doc.get("far_side") in ("quiet", "mosaic"),
              "texture far_side", "got {0!r}".format(doc.get("far_side")))
    # far_side_max_age_hours is how the app decides whether it may tell a guest
    # the far side is OBSERVED, so it has to be null exactly when it is not.
    fs_age = doc.get("far_side_max_age_hours")
    if doc.get("far_side") == "quiet":
        rep.check(fs_age is None,
                  "texture far_side_max_age_hours is null for a quiet fill",
                  "got {0!r}".format(fs_age))
    elif doc.get("far_side") == "mosaic":
        rep.check(isinstance(fs_age, (int, float)) and float(fs_age) > 0.0,
                  "texture far_side_max_age_hours is positive for a mosaic",
                  "got {0!r}".format(fs_age))

    # Observation age measured against the file's OWN generation time, so a
    # tree validated days later still gives the same verdict.
    gen, obs = parse_iso_z(doc.get("generated_iso") or ""), \
        parse_iso_z(doc.get("obs_iso") or "")
    if rep.check(gen is not None and obs is not None,
                 "texture generated_iso and obs_iso parse"):
        obs_age = age_hours(obs, gen)
        rep.check(obs_age > -0.1, "texture obs_iso is not in the future",
                  "{0:.2f} h ahead".format(-obs_age))
        entry = ((idx or {}).get("products") or {}).get("texture") or {}
        if entry.get("status") == "ok":
            rep.check(obs_age < TEX_MAX_OBS_AGE_HOURS,
                      "texture observation < {0:.0f} h old for status ok"
                      .format(TEX_MAX_OBS_AGE_HOURS),
                      "{0:.2f} h at generation".format(obs_age))
        else:
            rep.info("texture status is {0!r}; obs age {1:.2f} h".format(
                entry.get("status"), obs_age))

    # Every published channel is validated, not just the default one: a layer
    # the app can offer but cannot decode is the same bug as a broken default,
    # it just takes a guest one extra tap to find.
    layers = doc.get("layers")
    if isinstance(layers, list) and layers:
        rep.check(
            any(lay.get("url") == doc.get("url") for lay in layers
                if isinstance(lay, dict)),
            "texture layers include the top-level url",
            "top-level {0!r} not among {1}".format(
                doc.get("url"),
                [lay.get("url") for lay in layers if isinstance(lay, dict)]))
        # Identity is the SDO product code, not the wavelength: HMIB and HMIIC
        # have no wavelength (a magnetogram and a colorized continuum image),
        # so wavelength_angstrom is null for both and cannot tell them apart.
        codes = [lay.get("channel") for lay in layers if isinstance(lay, dict)]
        rep.check(all(isinstance(c, str) and c for c in codes),
                  "every texture layer names its channel", "got {0}".format(codes))
        rep.check(len(set(codes)) == len(codes),
                  "texture layer channels are unique", "got {0}".format(codes))

        # An honesty invariant, not a formatting one. farside_modulation
        # invents band-limited mottling for the hemisphere Earth cannot see.
        # That is a defensible stylization in EUV; on a magnetogram it is
        # fabricated magnetic field, and on a continuum image the polar ramp
        # encodes coronal holes that image does not show.
        bad_fill = [lay.get("channel") for lay in layers
                    if isinstance(lay, dict)
                    and str(lay.get("channel", "")).startswith("HMI")
                    and lay.get("far_side") != "flat"]
        rep.check(not bad_fill,
                  "HMI layers use a flat far side (no invented structure)",
                  "got quiet fill on {0}".format(bad_fill))
        for lay in layers:
            if not isinstance(lay, dict):
                rep.check(False, "texture layer is an object")
                continue
            _check_texture_jpeg(rep, get, doc, lay.get("url"), lay)
            _check_offlimb(rep, get, lay)
            _check_texture_frames(rep, get, doc, lay)
            _check_hires(rep, get, lay)
    else:
        rep.check(False, "texture.json has a non-empty layers array",
                  "got {0!r}".format(layers))
        _check_texture_jpeg(rep, get, doc, doc.get("url"), doc)


def _check_texture_frames(rep: Report, get, doc: dict, layer: dict,
                         deep: int = 3) -> int:
    """One channel's time-aligned frame sequence.

    The point of the sequence is that scrubbing back three days shows the Sun
    as it was three days ago, so the invariants that matter are all about time:
    targets strictly increasing on the 4 h grid, each frame's observation
    actually near its target, and the file name's own stamp agreeing with the
    target it claims. That last one is what catches a name/target desync, which
    would otherwise fail silently -- the app would keep rebuilding frames it
    already has, and nothing would look wrong until the CI job timed out.

    ``deep`` bounds how many frames per channel are downloaded and decoded.
    Every frame is checked at the manifest level; a sample is checked at the
    pixel level, because a 19 x 5 tree is 95 files and a --url run would
    otherwise pull ~15 MB to re-assert the same thing ninety times. The count
    actually sampled is reported, so the cap is never silent.
    """
    from .texture.export import HIST_NAME_RE

    channel = layer.get("channel")
    frames = layer.get("frames")
    if not isinstance(frames, list) or not frames:
        rep.check(False, "{0} has a non-empty frames array".format(channel),
                  "got {0!r}".format(frames))
        return 0

    prev = None
    for i, fr in enumerate(frames):
        if not isinstance(fr, dict):
            rep.check(False, "{0} frame {1} is an object".format(channel, i))
            continue
        tag = "{0} frame {1}".format(channel, i)
        rep.check(fr.get("index") == i, "{0} index matches position".format(tag),
                  "got {0!r}".format(fr.get("index")))
        tgt = parse_iso_z(fr.get("target_iso") or "")
        obs = parse_iso_z(fr.get("obs_iso") or "")
        if not rep.check(tgt is not None and obs is not None,
                         "{0} target_iso and obs_iso parse".format(tag)):
            continue
        if prev is not None:
            rep.check(tgt > prev, "{0} target is after the previous".format(tag),
                      "{0} follows {1}".format(fr.get("target_iso"), prev))
        prev = tgt

        newest = (i == len(frames) - 1)
        name = fr.get("url")
        if newest:
            # The newest slot IS the full-resolution map, and it deliberately
            # carries the freshest available image rather than one snapped to
            # the grid -- that slot is what "the Sun right now" means.
            rep.check(name == layer.get("url"),
                      "{0} (newest) is the full-resolution map".format(tag),
                      "got {0!r} vs {1!r}".format(name, layer.get("url")))
            rep.check((fr.get("width"), fr.get("height"))
                      == (TEX_OUT_W, TEX_OUT_H),
                      "{0} (newest) is {1}x{2}".format(tag, TEX_OUT_W,
                                                       TEX_OUT_H),
                      "got {0}x{1}".format(fr.get("width"), fr.get("height")))
        else:
            rep.check((fr.get("width"), fr.get("height"))
                      == (TEX_HIST_W, TEX_HIST_H),
                      "{0} is {1}x{2}".format(tag, TEX_HIST_W, TEX_HIST_H),
                      "got {0}x{1}".format(fr.get("width"), fr.get("height")))
            m = HIST_NAME_RE.match(str(name))
            if rep.check(m is not None,
                         "{0} url is a history frame name".format(tag),
                         "got {0!r}".format(name)):
                want = tgt.strftime("%Y%m%dT%H%MZ")
                rep.check(m.group("stamp") == want,
                          "{0} file stamp matches its target".format(tag),
                          "name says {0}, target is {1}".format(
                              m.group("stamp"), want))
                rep.check(m.group("code") == channel,
                          "{0} file names its own channel".format(tag),
                          "name says {0}".format(m.group("code")))
            off = abs(age_hours(obs, tgt))
            rep.check(off <= TEX_HIST_TOLERANCE_HOURS + 1e-6,
                      "{0} observation is within {1:.1f} h of its target"
                      .format(tag, TEX_HIST_TOLERANCE_HOURS),
                      "{0:.2f} h off".format(off))
            nb = fr.get("bytes")
            rep.check(isinstance(nb, int) and 0 < nb < TEX_HIST_MAX_BYTES,
                      "{0} bytes under {1}".format(tag, TEX_HIST_MAX_BYTES),
                      "got {0!r}".format(nb))

        lon = fr.get("sub_earth_carr_lon_deg")
        rep.check(isinstance(lon, (int, float)) and 0.0 <= float(lon) < 360.0,
                  "{0} sub_earth_carr_lon_deg in [0, 360)".format(tag),
                  "got {0!r}".format(lon))
        blat = fr.get("sub_earth_lat_deg")
        rep.check(isinstance(blat, (int, float)) and abs(float(blat)) <= 7.5,
                  "{0} sub_earth_lat_deg within +/-7.5".format(tag),
                  "got {0!r}".format(blat))

    # Pixel-level sample: newest, oldest, and the middle. The newest is already
    # checked as the layer's own map, so only the history frames are fetched.
    hist = [fr for fr in frames[:-1] if isinstance(fr, dict)]
    picks: list = []
    if hist and deep > 0:
        want = [0, len(hist) // 2, len(hist) - 1][:max(1, deep)]
        for j in sorted(set(want)):
            picks.append(hist[j])
    for fr in picks:
        _check_texture_jpeg(rep, get, doc, fr.get("url"), fr,
                            max_bytes=TEX_HIST_MAX_BYTES)
    # Near-side windows: GEOMETRY on every frame (it is pure manifest
    # arithmetic and free), pixels only on the same sampled frames as above.
    # Geometry is checked everywhere on purpose -- a misregistered window
    # decodes perfectly and the sampling contract is the only thing that
    # exposes it, so checking three of nineteen would be checking the cheap
    # half of the wrong thing.
    picked_urls = {id(fr) for fr in picks}
    near_n = 0
    for fr in frames:
        if isinstance(fr, dict) and fr.get("near_side") is not None:
            near_n += 1
            _check_near_side(rep, get, channel, fr, deep=id(fr) in picked_urls)
    rep.info("{0}: {1} frame(s) checked in the manifest, {2} decoded, "
             "{3} near-side window(s)".format(
                 channel, len(frames), len(picks), near_n))
    return len(picks)


def _check_offlimb(rep: Report, get, layer: dict) -> None:
    """One channel's off-limb crop.

    The rule that matters is `half_width_rsun`: the app scales the billboard by
    it so the crop's blacked-out hole lands on the sphere's silhouette. A wrong
    value does not fail anywhere — it just draws the corona at the wrong size
    around the Sun, which is exactly the kind of thing nobody notices until a
    guest asks why the prominences float.
    """
    off = layer.get("off_limb")
    channel = layer.get("channel")
    if not isinstance(off, dict):
        rep.check(False, "{0} has an off_limb block".format(channel))
        return

    name = off.get("url")
    if not rep.check(isinstance(name, str) and name.endswith(".jpg")
                     and "/" not in name,
                     "{0} off-limb url is a sibling .jpg".format(channel),
                     "got {0!r}".format(name)):
        return

    half = off.get("half_width_rsun")
    # AIA reaches ~1.28 R_sun and HMI ~1.09; anything outside this band means
    # the limb fit or the crop geometry has moved.
    rep.check(isinstance(half, (int, float)) and 1.02 < float(half) < 1.60,
              "{0} off-limb half_width_rsun is plausible".format(channel),
              "got {0!r}".format(half))

    blob = get("texture/" + name)
    if not rep.check(blob is not None, "{0} fetched".format(name)):
        return
    rep.check(len(blob) < TEX_OFFLIMB_MAX_BYTES,
              "{0} under {1} bytes".format(name, TEX_OFFLIMB_MAX_BYTES),
              "{0} bytes".format(len(blob)))
    if "bytes" in off:
        rep.check(len(blob) == int(off["bytes"]),
                  "{0} size matches texture.json".format(name),
                  "{0} vs {1}".format(len(blob), off["bytes"]))
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(blob))
        img.load()
    except Exception as exc:                                   # noqa: BLE001
        rep.check(False, "{0} decodes".format(name), str(exc))
        return
    rep.check(img.size[0] == img.size[1], "{0} is square".format(name),
              "got {0}x{1}".format(*img.size))

    # The disk MUST be blacked out: the billboard is additively blended, so a
    # bright center would paint a second Sun over the sphere.
    import numpy as np
    arr = np.asarray(img.convert("L"), dtype=float)
    n = arr.shape[0]
    c = n // 2
    q = n // 8
    core = arr[c - q:c + q, c - q:c + q]
    rep.check(float(core.mean()) < 4.0,
              "{0} disk center is blacked out".format(name),
              "center mean {0:.1f}".format(float(core.mean())))

    _check_offlimb_tiers(rep, get, channel, off, name)


def _check_offlimb_tiers(rep: Report, get, channel, off: dict,
                         default_name: str) -> None:
    """The rest of the off-limb ladder, if this manifest publishes one.

    Absent `tiers` is NOT a failure -- it is what a schema-4 manifest looks
    like, and the additive contract says a reader must survive that.

    Every rung is a resampling of ONE masked crop, so they share
    `half_width_rsun` and there is nothing per-rung to check about geometry.
    What can go wrong is bookkeeping: a rung whose declared size does not match
    its pixels (which would size the billboard right and sample it wrong), a
    rung that was never written (the prune keep-set forgetting the nested urls
    is a real failure mode -- see cli.py's keep set), and the default rung not
    appearing in its own ladder.
    """
    tiers = off.get("tiers")
    if tiers is None:
        rep.info("{0} publishes no off-limb tier ladder (schema 4)".format(channel))
        return
    if not rep.check(isinstance(tiers, list) and tiers,
                     "{0} off_limb.tiers is a non-empty list".format(channel),
                     "got {0!r}".format(tiers)):
        return

    from PIL import Image
    names = []
    sizes = []
    for tier in tiers:
        if not rep.check(isinstance(tier, dict), "{0} tier is an object".format(channel)):
            continue
        size, url = tier.get("size"), tier.get("url")
        if not rep.check(isinstance(size, int) and size >= 256
                         and isinstance(url, str) and url.endswith(".jpg")
                         and "/" not in url,
                         "{0} off-limb tier is well formed".format(channel),
                         "got size={0!r} url={1!r}".format(size, url)):
            continue
        names.append(url)
        sizes.append(size)
        blob = get("texture/" + url)
        if not rep.check(blob is not None, "{0} fetched".format(url)):
            continue
        rep.check(len(blob) < TEX_OFFLIMB_MAX_BYTES,
                  "{0} under {1} bytes".format(url, TEX_OFFLIMB_MAX_BYTES),
                  "{0} bytes".format(len(blob)))
        if "bytes" in tier:
            rep.check(len(blob) == int(tier["bytes"]),
                      "{0} size matches texture.json".format(url),
                      "{0} vs {1}".format(len(blob), tier["bytes"]))
        try:
            img = Image.open(io.BytesIO(blob))
            img.load()
        except Exception as exc:                               # noqa: BLE001
            rep.check(False, "{0} decodes".format(url), str(exc))
            continue
        # The declared size IS the sampling contract; a mismatch draws the
        # corona at the right scale from the wrong pixels.
        rep.check(img.size == (size, size),
                  "{0} pixel size matches its declared tier".format(url),
                  "got {0}x{1}, declared {2}".format(img.size[0], img.size[1], size))

    rep.check(sizes == sorted(set(sizes)),
              "{0} off-limb tiers are ascending and distinct".format(channel),
              "got {0}".format(sizes))
    rep.check(default_name in names,
              "{0} default off-limb rung appears in its own ladder".format(channel),
              "{0} not in {1}".format(default_name, names))


_HIRES_KEYS = ("url", "width", "height", "bytes", "obs_iso",
              "sub_earth_carr_lon_deg", "sub_earth_lat_deg", "source_url")


def _check_hires(rep: Report, get, layer: dict) -> None:
    """One channel's OPT-IN high-res newest-frame map (SCHEMA_TEXTURE /4).

    ADDITIVE ONLY: most published trees will never have run with
    --with-hires, so an ABSENT block is not a failure -- only a malformed
    PRESENT one is. This is the same discipline TEX_CHANNELS' `frames` and
    `off_limb` already follow, extended to a field that is also opt-in at
    build time, not just sometimes-empty.
    """
    channel = layer.get("channel")
    hires = layer.get("high_res")
    if hires is None:
        rep.info("{0} has no high_res block (pipeline run without "
                  "--with-hires, or this channel's hi-res build failed)"
                  .format(channel))
        return
    if not rep.check(isinstance(hires, dict),
                     "{0} high_res is an object".format(channel),
                     "got {0!r}".format(type(hires).__name__)):
        return
    missing = [k for k in _HIRES_KEYS if k not in hires]
    rep.check(not missing, "{0} high_res keys complete".format(channel),
              "missing {0}".format(missing))
    rep.check((hires.get("width"), hires.get("height"))
              == (TEX_HIRES_W, TEX_HIRES_H),
              "{0} high_res is {1}x{2}".format(channel, TEX_HIRES_W,
                                               TEX_HIRES_H),
              "got {0}x{1}".format(hires.get("width"), hires.get("height")))
    lon = hires.get("sub_earth_carr_lon_deg")
    rep.check(isinstance(lon, (int, float)) and 0.0 <= float(lon) < 360.0,
              "{0} high_res sub_earth_carr_lon_deg in [0, 360)".format(
                  channel),
              "got {0!r}".format(lon))
    blat = hires.get("sub_earth_lat_deg")
    rep.check(isinstance(blat, (int, float)) and abs(float(blat)) <= 7.5,
              "{0} high_res sub_earth_lat_deg within +/-7.5".format(channel),
              "got {0!r}".format(blat))
    rep.check(parse_iso_z(hires.get("obs_iso") or "") is not None,
              "{0} high_res obs_iso parses".format(channel),
              "got {0!r}".format(hires.get("obs_iso")))
    # Reuses _check_texture_jpeg exactly as the normal map and every history
    # frame do (fetch, byte budget, decode, declared-size match, not
    # blank/flat) -- an empty `doc` is fine because `entry` (== hires) always
    # carries its OWN width/height, so the doc-level fallback never fires.
    _check_texture_jpeg(rep, get, {}, hires.get("url"), hires,
                        max_bytes=TEX_HIRES_MAX_BYTES)


_NEAR_KEYS = ("url", "width", "height", "bytes", "lon_center_deg",
              "crval1_deg", "crpix1", "crpix2", "cdelt_deg",
              "lon_span_deg", "lat_span_deg")


def _check_near_side(rep: Report, get, channel, frame: dict, deep: bool) -> None:
    """One timeline slot's NEAR-SIDE WINDOW (SCHEMA_TEXTURE /5).

    ADDITIVE ONLY, same discipline as `high_res`: a slot built without
    --with-near-side simply has no `near_side` key, and that is not a failure.

    The check that matters, and the reason this function exists at all, is
    `cdelt_deg * width == lon_span_deg`. Everything else about a windowed map
    can be right while the window is centred on the wrong meridian or cut with
    the wrong CRPIX, and the JPEG would still decode, still be the right size,
    and still look like a plausible piece of Sun -- it would just be
    misregistered by degrees, and nothing downstream would notice. The app
    computes longitude from `lon_center_deg` and `cdelt_deg`, so those two plus
    the width ARE the sampling contract.
    """
    near = frame.get("near_side")
    if near is None:
        return
    tag = "{0} {1} near_side".format(channel, frame.get("target_iso"))
    if not rep.check(isinstance(near, dict), "{0} is an object".format(tag),
                     "got {0!r}".format(type(near).__name__)):
        return
    missing = [k for k in _NEAR_KEYS if k not in near]
    if not rep.check(not missing, "{0} keys complete".format(tag),
                     "missing {0}".format(missing)):
        return

    w, h = near.get("width"), near.get("height")
    rep.check((w, h) == (TEX_NEAR_W, TEX_NEAR_H),
              "{0} is {1}x{2}".format(tag, TEX_NEAR_W, TEX_NEAR_H),
              "got {0}x{1}".format(w, h))

    cdelt = near.get("cdelt_deg")
    rep.check(isinstance(cdelt, (int, float))
              and abs(float(cdelt) - TEX_NEAR_CDELT_DEG) < 1e-12,
              "{0} cdelt_deg pins to the declared full grid".format(tag),
              "got {0!r}, want {1!r}".format(cdelt, TEX_NEAR_CDELT_DEG))

    # The geometry contract: span must be cdelt * pixels, on BOTH axes. This is
    # what catches a crop done with the wrong CRPIX or NAXIS.
    for axis, span_key, npx in (("lon", "lon_span_deg", w),
                                ("lat", "lat_span_deg", h)):
        span = near.get(span_key)
        ok = (isinstance(span, (int, float)) and isinstance(cdelt, (int, float))
              and isinstance(npx, int)
              and abs(float(span) - float(cdelt) * npx) < 1e-9)
        rep.check(ok, "{0} {1}_span == cdelt * pixels".format(tag, axis),
                  "span {0!r} vs {1!r}".format(span, span if not ok else ""))
    rep.check(near.get("lon_span_deg") == TEX_NEAR_LON_SPAN_DEG,
              "{0} lon_span is {1} deg".format(tag, TEX_NEAR_LON_SPAN_DEG),
              "got {0!r}".format(near.get("lon_span_deg")))

    lon0 = near.get("lon_center_deg")
    rep.check(isinstance(lon0, (int, float)) and 0.0 <= float(lon0) < 360.0,
              "{0} lon_center_deg in [0, 360)".format(tag),
              "got {0!r}".format(lon0))
    # lon_center_deg is the SAME quantity as the frame's sub-earth longitude --
    # the window is centred on the observed meridian by definition. A mismatch
    # means the window was built for a different frame's l0, which is the one
    # way to get a perfectly valid map of the wrong moment.
    se = frame.get("sub_earth_carr_lon_deg")
    if isinstance(lon0, (int, float)) and isinstance(se, (int, float)):
        d = abs(((float(lon0) - float(se) + 180.0) % 360.0) - 180.0)
        rep.check(d < 0.05,
                  "{0} lon_center matches the frame's sub-earth meridian".format(tag),
                  "{0:.4f} vs {1:.4f} deg apart by {2:.4f}".format(lon0, se, d))
    # crval1 may legitimately sit outside [0, 360) -- the window runs past 360
    # or below 0 depending on l0 -- but it must agree with lon_center modulo a
    # full turn, or the raw WCS and the app's arithmetic describe different maps.
    crval = near.get("crval1_deg")
    if isinstance(crval, (int, float)) and isinstance(lon0, (int, float)):
        rep.check(abs((float(crval) % 360.0) - float(lon0)) < 1e-6,
                  "{0} crval1_deg agrees with lon_center_deg".format(tag),
                  "crval1 {0!r} % 360 vs {1!r}".format(crval, lon0))

    if deep:
        _check_texture_jpeg(rep, get, {}, near.get("url"), near,
                            max_bytes=TEX_NEAR_MAX_BYTES)


def _check_texture_jpeg(rep: Report, get, doc: dict, name, entry: dict,
                        max_bytes: int = TEX_MAX_BYTES) -> None:
    """One channel's JPEG: fetched, sized, decodable, and not flat.

    The expected pixel size comes from the ENTRY when it declares one, because
    a history frame is half the linear resolution of the newest map. Falling
    back to the document's top-level width/height keeps a schema-2 tree (one
    map per channel, no `frames` array) validating unchanged.
    """
    w = entry.get("width", doc.get("width"))
    h = entry.get("height", doc.get("height"))
    if not rep.check(isinstance(name, str) and name.endswith(".jpg")
                     and "/" not in name, "texture url is a sibling .jpg",
                     "got {0!r}".format(name)):
        return
    blob = get("texture/" + name)
    if not rep.check(blob is not None, "{0} fetched".format(name)):
        return
    rep.check(len(blob) < max_bytes,
              "{0} under {1} bytes".format(name, max_bytes),
              "{0} bytes".format(len(blob)))
    if "bytes" in entry:
        rep.check(len(blob) == int(entry["bytes"]),
                  "{0} size matches texture.json".format(name),
                  "{0} vs {1}".format(len(blob), entry["bytes"]))
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(blob))
        img.load()                      # force a full decode, not just headers
    except Exception as exc:
        rep.check(False, "{0} decodes".format(name), str(exc))
        return
    rep.check(img.size == (int(w or 0), int(h or 0)),
              "{0} pixel size matches texture.json".format(name),
              "got {0}x{1}".format(*img.size))
    rep.check(img.mode in ("RGB", "L"), "{0} mode".format(name),
              "got {0}".format(img.mode))
    # A structurally valid but black/flat JPEG is a real failure mode (SDO
    # eclipse frames, or a reprojection that produced nothing), and every
    # check above passes for one.
    px = np.asarray(img.convert("RGB"), dtype=np.float32)
    mean, std = float(px.mean()), float(px.std())
    rep.check(15.0 < mean < 245.0 and std > 8.0,
              "{0} is not blank or flat".format(name),
              "mean {0:.1f} std {1:.1f}".format(mean, std))


def _check_pfss(rep: Report, get, idx: Optional[dict],
                n_regions: Optional[int]) -> None:
    """pfss/manifest.json + topology.bin + every fNN.bin."""
    man = _json(get, "pfss/manifest.json")
    if man is None:
        if _claims_present(idx, "pfss"):
            rep.check(False, "pfss/manifest.json present (index says ok)")
        else:
            rep.info("pfss/manifest.json absent (index does not claim it)")
        return
    _check_manifest_schema(rep, man)
    if "geometry" in man and "frames" in man:
        _check_binaries(rep, get, man, n_regions)
        _check_matrices(rep, man)


# -----------------------------------------------------------------------------
# Trees: where a validation run reads its files from
# -----------------------------------------------------------------------------

class Tree(NamedTuple):
    """A readable data tree: bytes, a cheap size probe, and a label.

    ``root`` is the local directory when there is exactly one, and None
    otherwise (a URL, or the staging overlay).  Only the orphan check needs
    it, and only a single real directory can answer that question.
    """

    get: Callable[[str], Optional[bytes]]
    probe: Callable[[str], Optional[int]]
    root: Optional[str]
    label: str


def tree_from_root(root: str) -> Tree:
    return Tree(_loader(str(root), None), _prober(str(root), None),
                str(root), str(root))


def tree_from_url(base_url: str) -> Tree:
    return Tree(_loader(None, base_url), _prober(None, base_url), None,
                base_url)


def overlay_tree(staging_dir, published_dir) -> Tree:
    """Staging over published: the tree AS IT WILL BE after ``promote()``.

    THE POINT OF THE WHOLE REFACTOR.  Validation used to run in CI *after* the
    publish, so its only available verdict was "fail the workflow" and every
    product went down together -- footgun 50 (a frozen seed set's ar_index
    running off the end of a shrinking region list) and footgun 51 (NOAA
    keying a sunspot at latitude 98) each discarded five products that had
    been built correctly, leaving the site 11-13 h stale on EVERYTHING.  Six
    of forty-four runs.

    ``Staging.promote()`` walks ``produced`` and ``os.replace``s each staged
    file over ``out``, touching nothing else -- so "after promote" is exactly
    "staging if it has this path, else published".  That is a two-line
    resolver, and having it means a product can be judged, and rolled back
    ALONE, before anything is moved.

    No orphan check is possible here (``root`` is None) and none is wanted:
    before the pruner runs, an unreferenced file in ``out`` is normal.
    """
    staging = Path(staging_dir)
    published = Path(published_dir)

    def resolve(rel: str) -> Optional[Path]:
        for base in (staging, published):
            p = base / rel
            if p.is_file():
                return p
        return None

    def get(rel: str) -> Optional[bytes]:
        p = resolve(rel)
        if p is None:
            return None
        try:
            return p.read_bytes()
        except OSError:
            return None

    def probe(rel: str) -> Optional[int]:
        p = resolve(rel)
        if p is None:
            return None
        try:
            return p.stat().st_size
        except OSError:
            return None

    return Tree(get, probe, None,
                "{0} over {1}".format(staging, published))


def _as_tree(target) -> Tree:
    return target if isinstance(target, Tree) else tree_from_root(str(target))


# -----------------------------------------------------------------------------
# Per-product entry point
# -----------------------------------------------------------------------------

# The order a full report prints in, chosen to match what `validate` printed
# before it was split up, so a diff of two runs' output stays readable.
PRODUCT_ORDER = ("index", "active_regions", "ephemeris", "stats", "texture",
                 "events", "pfss")

# Consumer -> the products it addresses BY POSITION, and therefore cannot be
# judged independently of.  `ar_index` is an index into `ar/regions.json`, in
# both the pfss topology and every event record; if that list reverts to the
# published copy, its consumers have to be re-checked against the copy they
# will actually be served next to.  See footgun 23 (an ar_index of -1 is
# normal) and footgun 50 (the coupling is real -- which is why it is written
# down here rather than the checks being deleted).
CONSUMES = {"pfss": ("active_regions",), "events": ("active_regions",)}


def plan_rollbacks(failures: Dict[str, List[str]],
                   consumes: Optional[Dict[str, Tuple[str, ...]]] = None
                   ) -> Tuple[Set[str], Set[str]]:
    """(products to roll back, products to RE-CHECK) from a failure map.

    Pure, because the only other way to test this is a five-minute pipeline
    run against a deliberately corrupted feed.

    A consumer is NOT rolled back transitively.  After its producer reverts to
    the published copy the consumer may well still be valid against it (an
    ar_index that addressed five regions is fine if the published list also
    has five), and rolling back a correct product would discard good work for
    nothing.  So the answer is "re-check it", and the caller iterates to a
    fixed point.
    """
    consumes = CONSUMES if consumes is None else consumes
    roll = {name for name, fails in failures.items() if fails}
    recheck = {consumer for consumer, producers in consumes.items()
               if consumer not in roll and set(producers) & roll}
    return roll, recheck


def validate_products(target, *, strict: bool = False,
                      products: Optional[Iterable[str]] = None,
                      check_orphans: bool = False, verbose: bool = False
                      ) -> "Dict[str, Report]":
    """Validate a tree PRODUCT BY PRODUCT.  Returns {product: Report}.

    ``target`` is a :class:`Tree` or a local root path; ``products`` selects a
    subset (default: everything, including the "index" pseudo-product).  The
    names are the ones ``cli.build_index`` uses for index entries, so a caller
    can map a report straight onto the entry it has to rewrite.

    Cross-product checks belong to the CONSUMER, not the producer: pfss's
    ar_index bound and events' ar_index bound are both asserted inside the
    report of the product that does the addressing.  So a defect in
    ``ar/regions.json`` lands on ``active_regions`` and, at worst, on its
    consumers -- never the other way round.  ``_region_count`` reads that file
    silently for exactly this reason.
    """
    tree = _as_tree(target)
    get, probe = tree.get, tree.probe
    want = set(PRODUCT_ORDER) if products is None else set(products)
    unknown = sorted(want - set(PRODUCT_ORDER))
    if unknown:
        raise ValueError("unknown product(s): {0}".format(unknown))

    idx = _json(get, "index.json")
    reports: "Dict[str, Report]" = {}

    def report(name: str) -> Report:
        rep = Report(verbose=verbose)
        reports[name] = rep
        return rep

    if "index" in want:
        _check_index(report("index"), idx)

    n_regions: Optional[int] = None
    if want & {"pfss", "events"}:
        n_regions = _region_count(get)

    for name in PRODUCT_ORDER:
        if name == "index" or name not in want:
            continue
        rep = report(name)
        doc = _json(get, PRODUCT_MANIFESTS[name])
        # Cheap, total, and FIRST: every file this manifest names is in the
        # tree.  Affordable for all 110 texture files, where the decode
        # sampling further down is not.
        if doc is not None:
            _check_referenced_files(rep, probe, name, doc)
            if check_orphans:
                _check_no_orphans(rep, tree.root, name, doc)
        if name == "active_regions":
            _check_regions(rep, get, idx)
        elif name == "ephemeris":
            _check_ephem(rep, get, idx)
        elif name == "stats":
            _check_stats(rep, get, idx)
        elif name == "texture":
            _check_texture(rep, get, idx)
        elif name == "events":
            _check_events(rep, get, idx)
        elif name == "pfss":
            _check_pfss(rep, get, idx, n_regions)

    return reports


def failing_checks(rep: Report) -> List[str]:
    """The FAIL lines of a report, trimmed to the check label + detail."""
    out = []
    for line in rep.lines:
        text = line.strip()
        if text.startswith("FAIL"):
            out.append(text[4:].strip())
    return out


def product_ok(rep: Report, strict: bool = False) -> bool:
    """One product's verdict.  ``strict`` makes warnings count."""
    return rep.failures == 0 and (rep.warnings == 0 if strict else True)


def validate(root: Optional[str] = None, base_url: Optional[str] = None,
             strict: bool = False, verbose: bool = False,
             check_orphans: bool = False) -> Tuple[bool, str]:
    """Validate a whole data tree.  Returns (ok, report_text).

    A thin wrapper over :func:`validate_products` that ANDs every product's
    verdict and concatenates the reports, kept because ``cmd_validate`` and the
    ``--url`` path want exactly one answer for a tree that is already
    published.  The per-product entry point is what ``cmd_all`` uses to roll a
    single failing product back before the promote.

    ``check_orphans`` asserts that nothing in ``pfss/`` or ``texture/`` is
    unreferenced.  Root mode only, and only meaningful POST-promote: before
    the pruner runs an orphan is the normal state.  See _check_no_orphans.
    """
    tree = tree_from_url(base_url) if base_url else tree_from_root(root or ".")
    reports = validate_products(tree, strict=strict, verbose=verbose,
                                check_orphans=check_orphans)
    merged = Report(verbose=verbose)
    for name in PRODUCT_ORDER:
        rep = reports.get(name)
        if rep is None:
            continue
        merged.lines.extend(rep.lines)
        merged.failures += rep.failures
        merged.warnings += rep.warnings
    ok = merged.failures == 0 and (merged.warnings == 0 if strict else True)
    return ok, merged.text()
