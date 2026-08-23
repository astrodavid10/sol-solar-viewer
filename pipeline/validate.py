"""Validate a published data tree (local directory or live URL).

Runs in CI with ``--strict`` so a bad product fails the build instead of being
served.  The checks are ordered cheapest-first and each one exists because
getting it wrong produces a *silent* visual bug rather than an error:

1. schema/keys      -- app pins on ``schema``; a rename must fail loudly.
2. topology.bin     -- monotone offsets, final offset == n_verts_total,
                       ar_index within regions.json bounds.
3. fNN.bin          -- magic, header agreement, EXACT byte length, polarity in
                       {-1,0,1}, valid in {0,1}.
4. dequantization   -- declared round-trip error under 1e-4 R_sun and every
                       valid line's radii inside [0.99, 2.61] (a line outside
                       that is a frame/units bug, e.g. metres for R_sun).
5. cross-frame      -- identical n_lines and n_verts_total in EVERY frame; this
                       is the morph guarantee, and violating it makes the GPU
                       lerp read a neighbouring line's vertices.
6. matrices         -- orthonormal, det +1, and equal to the closed form
                       mat3_hci . Rz(hci_rot_deg); catches a sunpy frame change.
7. quaternion       -- Rotation.from_quat(q).as_matrix() == mat3; catches an
                       x,y,z,w vs w,x,y,z mixup, which would look like a
                       plausible-but-wrong rotation.
8. texture          -- schema/keys, the JPEG actually decodes at the declared
                       size, byte budget, sub_earth longitude in [0, 360), and
                       the observation age AT GENERATION TIME (both timestamps
                       live in the file, so the answer never drifts with the
                       wall clock the way "now - obs_iso" would).
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import urljoin

import numpy as np

from .config import (CME_MIN_SPEED_KMS, EVENTS_MAX_BYTES,
                     EVENTS_WINDOW_SLACK_HOURS, LIM_RSUN, SCHEMA_AR,
                     SCHEMA_EPHEM, SCHEMA_EVENTS, SCHEMA_INDEX, SCHEMA_PFSS,
                     SCHEMA_STATS, SCHEMA_TEXTURE, TEX_MAX_BYTES,
                     TEX_MAX_OBS_AGE_HOURS, TEX_OUT_H, TEX_OUT_W,
                     WINDOW_HOURS)
from .io_utils import age_hours, http_get, parse_iso_z
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


def _check_side_products(rep: Report, get, idx: Optional[dict]
                         ) -> Optional[int]:
    n_regions: Optional[int] = None
    regions = _json(get, "ar/regions.json")
    if regions is None:
        if _claims_present(idx, "active_regions"):
            rep.check(False, "ar/regions.json present (index says ok)")
        else:
            rep.info("ar/regions.json absent (index does not claim it)")
    else:
        rep.check(regions.get("schema") == SCHEMA_AR, "regions.json schema")
        rep.check(isinstance(regions.get("regions"), list),
                  "regions.json regions is a list")
        n_regions = len(regions.get("regions") or [])
        rep.check(int(regions.get("count", -1)) == n_regions,
                  "regions.json count matches array length")

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

    stats = _json(get, "stats/summary.json")
    if stats is None:
        if _claims_present(idx, "stats"):
            rep.check(False, "stats/summary.json present (index says ok)")
        else:
            rep.info("stats/summary.json absent (index does not claim it)")
    else:
        rep.check(stats.get("schema") == SCHEMA_STATS, "summary.json schema")
        rep.check("carrington" in stats, "summary.json carrington block")
    return n_regions


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
    """events/events.json -- the flare + CME catalogue.

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
    rep.check((w, h) == (TEX_OUT_W, TEX_OUT_H), "texture declared dimensions",
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
        # have no wavelength (a magnetogram and a colourised continuum image),
        # so wavelength_angstrom is null for both and cannot tell them apart.
        codes = [lay.get("channel") for lay in layers if isinstance(lay, dict)]
        rep.check(all(isinstance(c, str) and c for c in codes),
                  "every texture layer names its channel", "got {0}".format(codes))
        rep.check(len(set(codes)) == len(codes),
                  "texture layer channels are unique", "got {0}".format(codes))

        # An honesty invariant, not a formatting one. farside_modulation
        # invents band-limited mottling for the hemisphere Earth cannot see.
        # That is a defensible stylisation in EUV; on a magnetogram it is
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
    else:
        rep.check(False, "texture.json has a non-empty layers array",
                  "got {0!r}".format(layers))
        _check_texture_jpeg(rep, get, doc, doc.get("url"), doc)


def _check_texture_jpeg(rep: Report, get, doc: dict, name, entry: dict) -> None:
    """One channel's JPEG: fetched, sized, decodable, and not flat."""
    w, h = doc.get("width"), doc.get("height")
    if not rep.check(isinstance(name, str) and name.endswith(".jpg")
                     and "/" not in name, "texture url is a sibling .jpg",
                     "got {0!r}".format(name)):
        return
    blob = get("texture/" + name)
    if not rep.check(blob is not None, "{0} fetched".format(name)):
        return
    rep.check(len(blob) < TEX_MAX_BYTES,
              "{0} under {1} bytes".format(name, TEX_MAX_BYTES),
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


def validate(root: Optional[str] = None, base_url: Optional[str] = None,
             strict: bool = False, verbose: bool = False) -> Tuple[bool, str]:
    """Validate a data tree.  Returns (ok, report_text)."""
    get = _loader(root, base_url)
    rep = Report(verbose=verbose)

    idx = _json(get, "index.json")
    _check_index(rep, idx)
    n_regions = _check_side_products(rep, get, idx)
    _check_texture(rep, get, idx)
    _check_events(rep, get, idx)

    man = _json(get, "pfss/manifest.json")
    if man is None:
        if _claims_present(idx, "pfss"):
            rep.check(False, "pfss/manifest.json present (index says ok)")
        else:
            rep.info("pfss/manifest.json absent (index does not claim it)")
    else:
        _check_manifest_schema(rep, man)
        if "geometry" in man and "frames" in man:
            _check_binaries(rep, get, man, n_regions)
            _check_matrices(rep, man)

    ok = rep.failures == 0 and (rep.warnings == 0 if strict else True)
    return ok, rep.text()
