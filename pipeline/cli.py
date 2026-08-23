"""Command-line entry point: ``python -m pipeline <subcommand>``.

Subcommands
-----------
``all``            pfss + ephem + regions + stats (+ texture with
                   ``--with-texture``) + index.json
``pfss``           field-line frames only
``ephem``          spacecraft ephemerides only
``regions``        active-region table only
``stats``          activity digest only
``texture``        AIA Carrington texture only (patches index.json in place)
``validate``       check a data tree (``--root DIR`` or ``--url BASE``)
``plan``           print the 13-slot table without computing anything
``probe-sources``  one-shot upstream health check

Failure policy (from the plan, implemented in :func:`run_pfss`)
--------------------------------------------------------------
* a slot with no GONG file within 3 h reuses the previously published frame if
  its magnetogram is within 8 h of the slot target (frame ``reused: true``,
  manifest ``status: degraded``);
* reusing anything forces this run to adopt the PREVIOUS vertex plan, read back
  out of the published ``topology.bin`` -- otherwise the reused frame's vertex
  count would disagree with the new frames' and the morph would read across
  line boundaries;
* fewer than 6 usable slots -> ``pfss/`` is not written at all, ``index.json``
  reports ``stale``, and the previously published frames keep being served;
* SRS down -> the frozen seed arrays are reloaded from the seed cache;
* Horizons down -> the previous ``spacecraft.json`` is left in place, marked
  stale;
* the texture is a SOFT failure inside ``all``: it never changes the exit code,
  because a non-zero exit fails the CI step and would stop the publish, taking
  the freshly traced field lines down with a decorative product.  The previous
  JPEG and texture.json keep being served and the index entry goes stale.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import frames_orient
from .config import (CACHE_DIR, DEFAULT_OUT, FRAME_SPACING_HOURS,
                     GONG_BASE, GONG_TOLERANCE_HOURS,
                     KEEP_FRAME_CACHE_SETS,
                     MIN_FRAMES_TO_PUBLISH, PIPELINE_VERSION, SCHEMA_INDEX,
                     EVENTS_MAX_BYTES, EVENTS_WINDOW_SLACK_HOURS,
                     STALE_HOURS, TEX_CHANNELS, TEX_HIST_H,
                     TEX_HIST_MAX_NEW_PER_RUN, TEX_HIST_W,
                     TEX_OUT_H, TEX_OUT_W, WINDOW_HOURS)
from .io_utils import (PipelineError, Staging, age_hours, human_bytes, iso_z,
                       json_dumps, parse_iso_z, prune_dirs, read_json, unix_s,
                       utcnow, write_json)
from .pfss import export as pfss_export
from .pfss import seeds as pfss_seeds
from .pfss import solve as pfss_solve
from .pfss import timeline as pfss_timeline
from .sources import gong as gong_src
from .sources import srs as srs_src

# ─────────────────────────────────────────────────────────────────────────────
# Run context
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ProductResult:
    """One product's outcome, folded into index.json."""

    name: str
    url: str
    status: str                       # ok | degraded | stale | absent | failed
    generated: Optional[datetime] = None
    extra: Dict = field(default_factory=dict)
    note: str = ""


@dataclass
class Ctx:
    now: datetime
    out: Path
    cache: Path
    staging: Staging
    run_id: str
    verbose: bool = False
    force: bool = False
    keep_npz: bool = False
    from_cache: bool = False
    max_frames: Optional[int] = None
    simulate_gong_outage: int = 0
    simulate_srs_outage: bool = False
    simulate_donki_outage: bool = False
    with_texture: bool = False
    max_new_textures: Optional[int] = None

    def log(self, msg: str) -> None:
        if self.verbose:
            print(msg)


def make_ctx(args: argparse.Namespace) -> Ctx:
    out = Path(getattr(args, "out", DEFAULT_OUT))
    cache = Path(getattr(args, "cache", CACHE_DIR))
    now = utcnow()
    run_id = os.environ.get("GITHUB_RUN_ID") or "{0}-{1}".format(
        now.strftime("%Y%m%dT%H%M%SZ"), uuid.uuid4().hex[:6])
    return Ctx(
        now=now, out=out, cache=cache, staging=Staging(out), run_id=run_id,
        verbose=bool(getattr(args, "verbose", False)),
        force=bool(getattr(args, "force", False)),
        keep_npz=bool(getattr(args, "keep_npz", False)),
        from_cache=bool(getattr(args, "from_cache", False)),
        max_frames=getattr(args, "max_frames", None),
        simulate_gong_outage=int(getattr(args, "simulate_gong_outage", 0) or 0),
        simulate_srs_outage=bool(getattr(args, "simulate_srs_outage", False)),
        simulate_donki_outage=bool(
            getattr(args, "simulate_donki_outage", False)),
        with_texture=bool(getattr(args, "with_texture", False)),
        max_new_textures=getattr(args, "max_new_textures", None),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Seeds
# ─────────────────────────────────────────────────────────────────────────────

def acquire_seed_set(ctx: Ctx) -> pfss_seeds.SeedSet:
    """Freeze the seed set from the newest SRS, or fall back to the cache."""
    if ctx.from_cache:
        # --from-cache promises zero network: the cached arrays ARE the seed set
        # (and their id is what the cached frame npz files are filed under).
        cached = pfss_seeds.load_newest_seed_set(ctx.cache)
        if cached is None:
            raise PipelineError("--from-cache: no cached seed set")
        print("  seeds: {0}: {1} line(s) id={2}".format(
            cached.source, cached.n_lines, cached.seed_set_id))
        return cached
    regions, epoch, source = srs_src.newest_regions(
        ctx.cache / "srs", simulate_outage=ctx.simulate_srs_outage)
    if epoch is not None:
        ss = pfss_seeds.freeze_seed_set(regions, epoch, ctx.cache, source)
        print("  seeds: {0} line(s) ({1} background + {2} region) from {3} "
              "[{4}] id={5}".format(ss.n_lines, ss.n_bg,
                                    ss.n_lines - ss.n_bg, source,
                                    epoch.isoformat(), ss.seed_set_id))
        return ss
    cached = pfss_seeds.load_newest_seed_set(ctx.cache)
    if cached is None:
        raise PipelineError("no SRS and no cached seed set; cannot build "
                            "field lines")
    print("  seeds: SRS unavailable -> {0}: {1} line(s) id={2}".format(
        cached.source, cached.n_lines, cached.seed_set_id))
    return cached


# ─────────────────────────────────────────────────────────────────────────────
# PFSS
# ─────────────────────────────────────────────────────────────────────────────

def _plan_path(ctx: Ctx, seed_set_id: str) -> Path:
    return pfss_solve.frame_cache_dir(ctx.cache, seed_set_id) / "plan.json"


def _prev_published(ctx: Ctx) -> Tuple[Optional[dict], Optional[dict]]:
    """(manifest, topology) currently served from ``out``, if any."""
    man = read_json(ctx.out / "pfss" / "manifest.json")
    topo = None
    raw_path = ctx.out / "pfss" / "topology.bin"
    if raw_path.exists():
        try:
            topo = pfss_export.unpack_topology(raw_path.read_bytes())
        except Exception as exc:
            print("  WARN previous topology.bin unreadable: {0}".format(exc))
    return man, topo


def _resolve_slots(ctx: Ctx, ss: pfss_seeds.SeedSet
                   ) -> List[pfss_timeline.Slot]:
    if ctx.from_cache:
        data = read_json(_plan_path(ctx, ss.seed_set_id))
        if not data:
            raise PipelineError(
                "--from-cache: no cached plan for seed set {0}; run without it "
                "once first".format(ss.seed_set_id))
        slots = pfss_timeline.slots_from_json(data["slots"])
        print("  timeline: {0} cached slot(s) from {1}".format(
            len(slots), data.get("generated_iso")))
    else:
        slots = pfss_timeline.resolve_slots(
            ctx.now, WINDOW_HOURS, FRAME_SPACING_HOURS, GONG_TOLERANCE_HOURS,
            simulate_gong_outage=ctx.simulate_gong_outage,
            verbose=ctx.verbose)
    if ctx.max_frames:
        slots = slots[-int(ctx.max_frames):]
        for i, s in enumerate(slots):        # renumber; f<last> stays newest
            s.index = i
        # shared_with indices refer to the old numbering; recompute.
        first: Dict[str, int] = {}
        for s in slots:
            s.shared_with = None
            if not s.gong_key:
                continue
            if s.gong_key in first:
                s.shared_with = first[s.gong_key]
            else:
                first[s.gong_key] = s.index
    return slots


def _trace_all(ctx: Ctx, ss: pfss_seeds.SeedSet,
               slots: List[pfss_timeline.Slot]
               ) -> Tuple[Dict[str, pfss_solve.TracedFrame], List[dict]]:
    """Pass A: one solve+trace per distinct magnetogram, with an npz cache."""
    traced: Dict[str, pfss_solve.TracedFrame] = {}
    timings: List[dict] = []
    keys = pfss_timeline.unique_keys(slots)
    if not keys:
        return traced, timings
    print("  tracing {0} distinct magnetogram(s) for {1} slot(s)".format(
        len(keys), len(slots)))
    for key in keys:
        cache_path = pfss_solve.frame_cache_path(ctx.cache, ss.seed_set_id, key)
        if cache_path.exists() and not ctx.force:
            tf = pfss_solve.load_traced(cache_path)
            if tf is not None and tf.n_lines == ss.n_lines:
                traced[key] = tf
                ctx.log("    {0}: cache hit".format(key))
                continue
        if ctx.from_cache:
            print("    {0}: MISSING from cache (skipped)".format(key))
            continue
        slot = next(s for s in slots if s.gong_key == key)
        fits = gong_src.gong_download(slot.url, ctx.cache / "gong")
        if fits is None:
            print("    {0}: download failed".format(key))
            continue
        res = pfss_solve.trace_frame(fits, ss, verbose=ctx.verbose)
        if res is None:
            print("    {0}: PFSS failed".format(key))
            continue
        tf, tm = res
        pfss_solve.save_traced(cache_path, tf)
        traced[key] = tf
        tm["key"] = key
        timings.append(tm)
        if not ctx.verbose:
            print("    {0}: solve {1:.2f}s trace {2:.2f}s valid {3}/{4}".format(
                key, tm["solve_s"], tm["trace_s"], tm["n_valid"],
                tm["n_lines"]))
    return traced, timings


def _reuse_candidate(prev_man: Optional[dict], target: datetime
                     ) -> Optional[dict]:
    """Closest previously published frame within STALE_HOURS of ``target``."""
    if not prev_man:
        return None
    best, best_dt = None, None
    for fr in prev_man.get("frames") or []:
        try:
            dt = abs(int(fr["mag_unix"]) - unix_s(target)) / 3600.0
        except (KeyError, TypeError, ValueError):
            continue
        if dt <= STALE_HOURS and (best_dt is None or dt < best_dt):
            best, best_dt = fr, dt
    return best


def _nv_from_topology(topo: dict) -> "object":
    import numpy as np
    off = topo["line_offset"].astype(np.int64)
    return np.diff(off).astype(np.int32)


def run_pfss(ctx: Ctx, ss: Optional[pfss_seeds.SeedSet] = None
             ) -> Tuple[ProductResult, Optional[pfss_seeds.SeedSet]]:
    """Build + write the PFSS product.  Returns (result, seed set used)."""
    import numpy as np

    print("[pfss]")
    t_start = time.perf_counter()
    ss = ss or acquire_seed_set(ctx)
    slots = _resolve_slots(ctx, ss)
    n_resolved = sum(1 for s in slots if s.resolved)
    print("  slots: {0}/{1} have a magnetogram within {2:.0f} h".format(
        n_resolved, len(slots), GONG_TOLERANCE_HOURS))

    # A --max-frames run is a truncated view; persisting its plan would make a
    # later --from-cache re-export silently produce only those few frames.
    if not ctx.from_cache and not ctx.max_frames and n_resolved:
        write_json(_plan_path(ctx, ss.seed_set_id), {
            "generated_iso": iso_z(ctx.now),
            "seed_set_id": ss.seed_set_id,
            "slots": pfss_timeline.slots_to_json(slots),
        })

    traced, timings = _trace_all(ctx, ss, slots)
    prev_man, prev_topo = _prev_published(ctx)

    # Decide each slot's fate: own traced frame, reuse, or drop.
    plan: List[dict] = []
    for s in slots:
        tf = traced.get(s.gong_key) if s.gong_key else None
        if tf is not None:
            plan.append({"slot": s, "traced": tf, "reused": None})
            continue
        cand = _reuse_candidate(prev_man, s.target)
        if cand is not None and prev_topo is not None and \
                prev_topo.get("seed_set_id") == ss.seed_set_id:
            plan.append({"slot": s, "traced": None, "reused": cand})
        else:
            print("  f{0:02d} dropped ({1})".format(
                s.index, s.note or "no data and nothing reusable"))

    n_reused = sum(1 for p in plan if p["reused"] is not None)
    n_own = len(plan) - n_reused
    # The threshold counts FRESHLY TRACED frames only.  Reuse exists to patch
    # gaps, not to republish a whole stale window: if it counted, a multi-day
    # GONG outage would keep re-emitting the same frames as "degraded" forever
    # and the app would never be told the field data has gone stale.
    # An explicitly truncated local run (--max-frames 2) still publishes what
    # it asked for.
    min_needed = min(MIN_FRAMES_TO_PUBLISH, len(slots))
    if n_own < min_needed:
        print("  only {0} freshly traced frame(s) (< {1}); NOT publishing "
              "pfss/ -- previous frames keep being served, index marks it "
              "stale".format(n_own, min_needed))
        gen = parse_iso_z((prev_man or {}).get("generated_iso", ""))
        return (ProductResult(
            name="pfss", url="pfss/manifest.json",
            status="stale" if prev_man else "absent", generated=gen,
            note="{0} freshly traced frame(s) of {1} slot(s)".format(
                n_own, len(slots)),
            extra={"frames": 0}), ss)

    # Pass B: vertex plan.  Reusing a published frame forces the published
    # vertex plan on the whole run so every frame keeps identical topology.
    own = [p["traced"] for p in plan if p["traced"] is not None]
    arclen_max = np.zeros(ss.n_lines, dtype=np.float32)
    for tf in own:
        arclen_max = np.maximum(arclen_max, tf.arclen)
    nv = pfss_export.plan_verts(arclen_max)
    if n_reused and prev_topo is not None:
        nv_prev = _nv_from_topology(prev_topo)
        if nv_prev.size == nv.size:
            if not np.array_equal(nv_prev, nv):
                print("  adopting previous vertex plan for {0} reused "
                      "frame(s) ({1} -> {2} verts)".format(
                          n_reused, int(nv.sum()), int(nv_prev.sum())))
            nv = nv_prev
        else:
            print("  WARN previous topology has {0} lines, current has {1}; "
                  "dropping reused frames".format(nv_prev.size, nv.size))
            plan = [p for p in plan if p["reused"] is None]
            n_reused = 0
            if len(plan) < min_needed:                   # pragma: no cover
                return (ProductResult(
                    name="pfss", url="pfss/manifest.json", status="stale",
                    generated=parse_iso_z(
                        (prev_man or {}).get("generated_iso", "")),
                    note="topology change dropped reused frames"), ss)

    n_verts_total = int(nv.sum())
    topo_blob = pfss_export.pack_topology(ss, nv)
    ctx.staging.write_bytes("pfss/topology.bin", topo_blob)

    # Write frames in slot order, renumbered 0..n-1 (f<last> is newest).
    frames: List[dict] = []
    max_err = 0.0
    sizes: List[int] = []
    for new_index, p in enumerate(plan):
        s: pfss_timeline.Slot = p["slot"]
        if p["traced"] is not None:
            tf: pfss_solve.TracedFrame = p["traced"]
            mag_dt = pfss_solve.mag_datetime(tf)
            orient = frames_orient.orient_for(mag_dt)
            blob, stats = pfss_export.build_frame_payload(
                new_index, tf, nv, orient["unix"])
            mag_file = s.gong_key or ""
            reused = False
        else:
            cand = p["reused"]
            src = ctx.out / "pfss" / cand["url"]
            blob = src.read_bytes()
            # Rewrite the header's frame_index: the file's name (and therefore
            # its index) changes when the window slides.
            blob = (blob[:8] + struct.pack("<I", new_index) + blob[12:])
            mag_dt = datetime.fromtimestamp(int(cand["mag_unix"]),
                                            tz=timezone.utc)
            orient = frames_orient.orient_for(mag_dt)
            stats = {"bytes": len(blob),
                     "max_error_rsun": float(
                         (prev_man.get("quantization", {}).get("xyz", {})
                          or {}).get("max_error_rsun", 0.0)),
                     "n_valid": int(cand.get("n_valid", 0)),
                     "n_closed": int(cand.get("n_closed", 0)),
                     "n_open_pos": int(cand.get("n_open_pos", 0)),
                     "n_open_neg": int(cand.get("n_open_neg", 0))}
            mag_file = str(cand.get("mag_file") or "")
            reused = True
            print("  f{0:02d} reused published frame from {1} "
                  "(target {2})".format(new_index, orient["iso"],
                                        iso_z(s.target)))
        ctx.staging.write_bytes("pfss/f{0:02d}.bin".format(new_index), blob)
        sizes.append(len(blob))
        max_err = max(max_err, float(stats["max_error_rsun"]))
        frames.append(pfss_export.frame_entry(
            index=new_index, target_iso=iso_z(s.target), orient=orient,
            mag_file=mag_file,
            mag_age_hours=abs((mag_dt - s.target).total_seconds()) / 3600.0,
            stats=stats, reused=reused))

    newest = frames[-1]
    newest_dt = datetime.fromtimestamp(newest["mag_unix"], tz=timezone.utc)
    status = "degraded" if (n_reused or len(plan) < len(slots)) else "ok"
    manifest = pfss_export.build_manifest(
        generated=ctx.now, run_id=ctx.run_id, status=status, ss=ss, nv=nv,
        topology_bytes=len(topo_blob), frames=frames,
        tracer=pfss_solve.tracer_name(), newest_mag_iso=newest["mag_iso"],
        newest_mag_age_hours=age_hours(newest_dt, ctx.now),
        window_hours=WINDOW_HOURS, frame_spacing_hours=FRAME_SPACING_HOURS,
        constants=frames_orient.constants_block(
            frames_orient.orient_for(newest_dt)),
        max_error_rsun=max_err)
    ctx.staging.write_json("pfss/manifest.json", manifest)

    if not ctx.keep_npz:
        removed = prune_dirs(ctx.cache / "frames", KEEP_FRAME_CACHE_SETS)
        for p in removed:
            ctx.log("  pruned stale frame cache {0}".format(p.name))

    print("  {0} frame(s), {1} lines, {2} verts, frame {3}..{4} "
          "({5} total), dequant err {6:.2e} R_sun, {7:.1f}s".format(
              len(frames), ss.n_lines, n_verts_total, human_bytes(min(sizes)),
              human_bytes(max(sizes)), human_bytes(sum(sizes) + len(topo_blob)),
              max_err, time.perf_counter() - t_start))
    return (ProductResult(
        name="pfss", url="pfss/manifest.json", status=status,
        generated=ctx.now,
        extra={"frames": len(frames), "reused": n_reused,
               "data_age_hours": round(age_hours(newest_dt, ctx.now), 3),
               "n_lines": ss.n_lines, "n_verts_total": n_verts_total,
               "seed_set_id": ss.seed_set_id}), ss)


# ─────────────────────────────────────────────────────────────────────────────
# Other products
# ─────────────────────────────────────────────────────────────────────────────

def run_ephem(ctx: Ctx) -> ProductResult:
    from .ephem import export as ephem_export
    print("[ephem]")
    t0 = time.perf_counter()
    try:
        doc = ephem_export.build_spacecraft(ctx.now, verbose=ctx.verbose)
    except Exception as exc:
        print("  FAILED: {0}".format(exc))
        prev = read_json(ctx.out / "ephem" / "spacecraft.json")
        gen = parse_iso_z((prev or {}).get("generated_iso", ""))
        return ProductResult(name="ephemeris", url="ephem/spacecraft.json",
                             status="stale" if prev else "failed",
                             generated=gen, note=str(exc))
    ctx.staging.write_json("ephem/spacecraft.json", doc)
    print("  {0} bodies x {1} epochs, {2}, {3:.1f}s".format(
        len(doc["bodies"]), len(doc["epochs_unix"]),
        human_bytes(len(json_dumps(doc))), time.perf_counter() - t0))
    return ProductResult(name="ephemeris", url="ephem/spacecraft.json",
                         status="ok", generated=ctx.now,
                         extra={"bodies": len(doc["bodies"]),
                                "epochs": len(doc["epochs_unix"])})


def run_regions(ctx: Ctx, ss: Optional[pfss_seeds.SeedSet]) -> ProductResult:
    from .regions import export as regions_export
    print("[regions]")
    ss = ss or acquire_seed_set(ctx)

    # Per-UT-day spot counts covering the scrubber's window, so the app's
    # sunspot chip can follow the playhead instead of always reporting today.
    # +1 day because a 72 h window anchored mid-day touches four UT dates, and
    # the app resolves a frame time to the date it falls in.
    days = WINDOW_HOURS // 24 + 1
    try:
        history = srs_src.daily_history(days, now=ctx.now)
    except Exception as exc:                                   # noqa: BLE001
        # Optional enrichment of an otherwise-good product: the chip falls back
        # to the current count, which is what it showed before this existed.
        print("  WARN daily history unavailable: {0}".format(exc))
        history = []

    doc = regions_export.build_regions(
        ss.regions, ss.region_seed_counts, ss.srs_epoch, ss.source, ctx.now,
        status="degraded" if ss.source.startswith("cached") else "ok",
        history=history)
    ctx.staging.write_json("ar/regions.json", doc)
    complex_n = sum(1 for r in doc["regions"] if r["is_complex"])
    print("  {0} region(s) ({1} delta), epoch {2}, source {3}".format(
        doc["count"], complex_n, doc["srs_epoch_date"], ss.source))
    if history:
        print("  history: {0}/{1} day(s) -> {2}".format(
            len(history), days,
            ", ".join("{0} {1} spot(s)/{2} region(s)".format(
                h["date"][5:], h["spot_count"], h["region_count"])
                for h in history)))
        # The top-level `count` comes from srs.txt and this series from
        # solar_regions.json; they legitimately disagree (see daily_history).
        if history[-1]["region_count"] != doc["count"]:
            print("  note: today's srs.txt lists {0} region(s), the history "
                  "product {1} -- different epochs and Section I only, both "
                  "expected".format(doc["count"], history[-1]["region_count"]))
    else:
        print("  history: none available ({0} day(s) requested)".format(days))
    return ProductResult(name="active_regions", url="ar/regions.json",
                         status=doc["status"], generated=ctx.now,
                         extra={"count": doc["count"],
                                "history_days": len(history)})


def _regions_for_check(ctx: Ctx) -> List[dict]:
    """Active regions to score the texture's registration against.

    Staging first: inside ``all`` the table this run just built has not been
    promoted yet, and it is the one contemporaneous with the image.
    """
    for p in (ctx.staging.dir / "ar" / "regions.json",
              ctx.out / "ar" / "regions.json"):
        doc = read_json(p)
        if isinstance(doc, dict) and isinstance(doc.get("regions"), list):
            return doc["regions"]
    return []


def _published_texture_frames(ctx: Ctx) -> Dict[Tuple[str, str], dict]:
    """{(channel, target_iso): frame} from the texture.json already on disk.

    In CI ``out`` is seeded from the published gh-pages tree before the build
    (footgun 31), so this is how a run learns which history frames it does NOT
    have to rebuild.  Without it every run would re-reproject ninety maps and
    blow the job's whole time budget.
    """
    doc = read_json(ctx.out / "texture/texture.json") or {}
    found: Dict[Tuple[str, str], dict] = {}
    for layer in (doc.get("layers") or []):
        code = layer.get("channel")
        for fr in (layer.get("frames") or []):
            tgt, url = fr.get("target_iso"), fr.get("url")
            if code and tgt and url:
                found[(code, tgt)] = fr
    return found


def _texture_history(ctx: Ctx, layers: List[dict], primary: dict) -> dict:
    """Fill each layer's ``frames`` array, building only what is missing.

    The newest slot is the full-resolution map every layer already built, so it
    is listed rather than rebuilt -- and it deliberately carries the FRESHEST
    available image rather than one snapped to the 4 h grid, because that slot
    is what "the Sun right now" means.  Older slots get their own
    reduced-resolution map, keyed on the slot's target time.

    Slots are filled NEWEST-MISSING-FIRST with the channels interleaved, so a
    capped run spreads its budget across all five channels near the present
    rather than completing one channel back to three days ago.
    """
    from .texture import export as texture_export

    targets = pfss_timeline.slot_targets(ctx.now)
    newest = targets[-1]
    published = _published_texture_frames(ctx)
    by_code = {ly["channel"]: ly for ly in layers}
    frames: Dict[str, Dict[str, dict]] = {c: {} for c in by_code}

    # The newest slot: the full-res map, already built and staged.
    for code, layer in by_code.items():
        frames[code][iso_z(newest)] = {
            "target_iso": iso_z(newest),
            "url": layer["url"],
            "bytes": layer["bytes"],
            "width": TEX_OUT_W,
            "height": TEX_OUT_H,
            "obs_iso": layer["obs_iso"],
            "sub_earth_carr_lon_deg": layer["sub_earth_carr_lon_deg"],
            "sub_earth_lat_deg": layer["sub_earth_lat_deg"],
            "source_url": layer["source_url"],
        }

    reused = built = failed = 0
    cap = (TEX_HIST_MAX_NEW_PER_RUN if ctx.max_new_textures is None
           else int(ctx.max_new_textures))
    budget = cap
    todo: List[Tuple[datetime, str]] = []
    for target in reversed(targets[:-1]):             # newest history first
        for code in by_code:
            key = (code, iso_z(target))
            have = published.get(key)
            if have and (ctx.out / "texture" / str(have.get("url"))).exists():
                frames[code][iso_z(target)] = have
                ctx.staging.note("texture/" + str(have["url"]))
                reused += 1
            else:
                todo.append((target, code))

    for target, code in todo:
        if budget <= 0:
            break
        try:
            blob, meta = texture_export.build_history_frame(
                target, code, verbose=ctx.verbose)
        except Exception as exc:                          # noqa: BLE001
            # A slot with no usable source is left OUT of the manifest. The app
            # falls back to the nearest frame it does have, which is honest;
            # substituting today's Sun for a three-day-old one is not.
            print("    {0} {1}: {2}".format(code, iso_z(target), exc))
            failed += 1
            budget -= 1
            continue
        ctx.staging.write_bytes("texture/" + meta["url"], blob)
        frames[code][iso_z(target)] = meta
        built += 1
        budget -= 1

    hist_bytes = 0
    for code, layer in by_code.items():
        ordered = [frames[code][iso_z(t)] for t in targets
                   if iso_z(t) in frames[code]]
        for i, fr in enumerate(ordered):
            fr["index"] = i
        layer["frames"] = ordered
        hist_bytes += sum(int(fr.get("bytes") or 0) for fr in ordered[:-1])

    want = len(targets) * len(by_code)
    have = sum(len(v) for v in frames.values())
    # Frames the cap stopped us from even attempting. Kept separate from
    # `failed` on purpose: one is our own throttle and will resolve itself next
    # run, the other is an upstream gap that may never resolve. Reporting them
    # as one number tells the operator to wait for something that is not coming.
    skipped = max(0, len(todo) - built - failed)
    print("  history: {0} slot(s) x {1} channel(s) = {2}; {3} reused, {4} "
          "built, {5} unavailable upstream, {6} deferred by the cap ({7} at "
          "{8}x{9})".format(
              len(targets), len(by_code), want, reused, built, failed, skipped,
              human_bytes(hist_bytes), TEX_HIST_W, TEX_HIST_H))
    if skipped:
        # Net progress per run is (cap - channels), because one new slot per
        # channel scrolls into the window every 4 h just to stand still. Say so:
        # a cap at or below the channel count would never converge.
        net = cap - len(by_code)
        print("    capped at {0} new frame(s) this run; net {1:+d}/run, so ~{2} "
              "more run(s) to fill (or pass --max-new-textures {3} locally)"
              .format(cap, net,
                      "?" if net <= 0 else int(-(-skipped // net)),
                      skipped))
    if failed:
        # An archive gap, not a bug and not something a re-run fixes soon. The
        # app falls back to the nearest frame it does have. Measured 2026-08-23:
        # the SDO browse archive for 2026-08-21 stops at 12:42 UT in EVERY
        # channel at every resolution, so three slots x five channels are simply
        # not obtainable for that window.
        print("    {0} slot(s) have no source image within {1:.1f} h and are "
              "omitted from the manifest; the app falls back to the nearest "
              "frame it has".format(failed, TEX_HIST_TOLERANCE_HOURS))
    primary["frames"] = by_code[primary["channel"]]["frames"]
    return {"history_bytes": hist_bytes, "history_reused": reused,
            "history_built": built, "history_pending": skipped,
            "history_failed": failed, "slots": len(targets)}


def run_texture(ctx: Ctx) -> ProductResult:
    """Publish one Carrington map per TEX_CHANNELS entry.

    The document keeps its original top-level shape, describing the FIRST
    channel (TEX_WAVELENGTH, the app's default), and adds a `layers` array with
    one entry per published channel — so a reader that only knows schema 1 still
    finds a complete, correct texture at the top level. The app fetches exactly
    one layer's JPEG, whichever the guest is looking at.

    A channel that fails is SKIPPED rather than failing the stage: one AIA
    channel being down (or in eclipse) should cost the guest that one option,
    not the whole textured Sun. Losing the DEFAULT channel is different — with
    no top-level document there is nothing to publish, so that propagates.
    """
    from .texture import export as texture_export
    print("[texture]")
    t0 = time.perf_counter()
    regions = _regions_for_check(ctx)

    layers: List[dict] = []
    primary_doc: Optional[dict] = None
    primary_info: Optional[dict] = None
    total_bytes = 0

    for channel in TEX_CHANNELS:
        code = channel["code"]
        try:
            blob, doc, info, offlimb = texture_export.build_texture(
                ctx.now, regions, verbose=ctx.verbose, code=code)
        except Exception as exc:                       # noqa: BLE001
            if code == TEX_CHANNELS[0]["code"]:
                raise
            print("  {0} skipped: {1}".format(code, exc))
            continue
        ctx.staging.write_bytes("texture/" + doc["url"], blob)
        ctx.staging.write_bytes("texture/" + doc["off_limb"]["url"], offlimb)
        texture_export.log_texture(info, len(blob), verbose=ctx.verbose)
        print("    off-limb {0} ({1}, reaches {2:.2f} R_sun)".format(
            doc["off_limb"]["url"], human_bytes(len(offlimb)),
            doc["off_limb"]["half_width_rsun"]))
        total_bytes += len(blob) + len(offlimb)
        layers.append({
            "channel": doc["channel"],
            "label": doc["label"],
            "wavelength_angstrom": doc["wavelength_angstrom"],
            "far_side": doc["far_side"],
            "off_limb": doc["off_limb"],
            "url": doc["url"],
            "bytes": doc["bytes"],
            "obs_iso": doc["obs_iso"],
            "sub_earth_carr_lon_deg": doc["sub_earth_carr_lon_deg"],
            "sub_earth_lat_deg": doc["sub_earth_lat_deg"],
            "source_url": doc["source_url"],
        })
        if primary_doc is None:
            primary_doc = doc
            primary_info = info

    assert primary_doc is not None and primary_info is not None
    primary_doc["layers"] = layers
    hist = _texture_history(ctx, layers, primary_doc)
    total_bytes += hist["history_bytes"]
    ctx.staging.write_json("texture/texture.json", primary_doc)
    print("  {0} layer(s), {1} total, {2:.1f}s".format(
        len(layers), human_bytes(total_bytes), time.perf_counter() - t0))

    status = texture_export.texture_status(primary_info["obs_age_hours"])
    return ProductResult(
        name="texture", url="texture/texture.json", status=status,
        generated=ctx.now,
        note=("" if status == "ok" else
              "newest AIA frame is {0:.1f} h old".format(
                  primary_info["obs_age_hours"])),
        extra={"obs_iso": primary_doc["obs_iso"],
               "obs_age_hours": round(primary_info["obs_age_hours"], 3),
               "bytes": total_bytes, "layers": len(layers),
               "width": primary_doc["width"],
               "height": primary_doc["height"],
               "slots": hist["slots"],
               "history_built": hist["history_built"],
               "history_reused": hist["history_reused"],
               "history_pending": hist["history_pending"],
               "history_unavailable": hist["history_failed"]})


def run_events(ctx: Ctx) -> ProductResult:
    """Flare + CME catalog from CCMC DONKI.

    Never fatal by design (see run_all): DONKI has no SLA, and field lines are
    the headline product. A DONKI outage falls back to the cached response and,
    failing that, leaves the previously published events.json in place.
    """
    from .events import export as events_export
    from .sources import donki as donki_src
    print("[events]")
    t0 = time.perf_counter()

    # The drill fails the HTTP call, NOT this function: that is the realistic
    # outage, and it exercises the cache fallback and the degraded status. With
    # no cache either, the PipelineError propagates and run_all rolls back to
    # the published file.
    hours = WINDOW_HOURS + EVENTS_WINDOW_SLACK_HOURS
    outage = ctx.simulate_donki_outage
    flares, src_f = donki_src.fetch_flares(
        ctx.now, hours, ctx.cache, ctx.verbose, simulate_outage=outage)
    cmes, src_c = donki_src.fetch_cmes(
        ctx.now, hours, ctx.cache, ctx.verbose, simulate_outage=outage)
    source = "CCMC DONKI (kauai.ccmc.gsfc.nasa.gov)"
    cached = "cached" in (src_f, src_c)
    if cached:
        source += " [cached]"

    doc = events_export.build_events(
        ctx.now, flares, cmes, _regions_for_check(ctx), source,
        status="degraded" if cached else "ok")

    blob = json_dumps(doc).encode("utf-8")
    if len(blob) > EVENTS_MAX_BYTES:
        raise PipelineError(
            "events.json is {0} B, over the {1} B ceiling -- DONKI's shape has "
            "probably changed".format(len(blob), EVENTS_MAX_BYTES))
    ctx.staging.write_json("events/events.json", doc)

    c = doc["counts"]
    matched = sum(1 for e in doc["events"] if e.get("ar_index", -1) >= 0)
    withar = sum(1 for e in doc["events"] if e.get("ar_number"))
    print("  {0} flare(s) ({1} X), {2} CME(s) ({3} fast), {4} B".format(
        c["flares"], c["x_class"], c["cmes"], c["fast_cmes"], len(blob)))
    # The AR join is the silent-failure risk here (DONKI numbers regions 10000
    # higher than SRS does), so the match rate is printed every run.
    print("  AR join: {0}/{1} event(s) with a region matched a current one"
          .format(matched, withar))
    print("  {0:.1f}s".format(time.perf_counter() - t0))

    return ProductResult(
        name="events", url="events/events.json", status=doc["status"],
        generated=ctx.now,
        note="DONKI unreachable; served from cache" if cached else "",
        extra={"flares": c["flares"], "cmes": c["cmes"],
               "x_class": c["x_class"], "fast_cmes": c["fast_cmes"],
               "bytes": len(blob)})


def run_stats(ctx: Ctx, region_count: Optional[int]) -> ProductResult:
    from .stats import export as stats_export
    print("[stats]")
    if region_count is None:
        regions = read_json(ctx.out / "ar" / "regions.json") or {}
        region_count = int(regions.get("count", 0))
    orient = frames_orient.orient_for(ctx.now)
    carrington = {"rotation": orient["carrington_rotation"],
                  "l0Deg": orient["l0_deg"], "b0Deg": orient["b0_deg"]}
    doc = stats_export.build_stats(ctx.now, ctx.cache, region_count,
                                   carrington, verbose=ctx.verbose)
    ctx.staging.write_json("stats/summary.json", doc)
    degraded = doc["sunspotNumber"] is None or doc["f107"] is None
    print("  digest written ({0})".format(
        "degraded" if degraded else "complete"))
    return ProductResult(name="stats", url="stats/summary.json",
                         status="degraded" if degraded else "ok",
                         generated=ctx.now)


# ─────────────────────────────────────────────────────────────────────────────
# index.json
# ─────────────────────────────────────────────────────────────────────────────

_PRODUCT_URLS = {
    "pfss": "pfss/manifest.json",
    "ephemeris": "ephem/spacecraft.json",
    "active_regions": "ar/regions.json",
    "stats": "stats/summary.json",
    "texture": "texture/texture.json",
    "events": "events/events.json",
}


def _existing_product(ctx: Ctx, name: str) -> ProductResult:
    """Describe a product this run did not touch, from what is on disk."""
    url = _PRODUCT_URLS[name]
    doc = read_json(ctx.out / url)
    if not doc:
        return ProductResult(name=name, url=url, status="absent")
    gen = parse_iso_z(doc.get("generated_iso", ""))
    stale = gen is None or age_hours(gen, ctx.now) > STALE_HOURS
    return ProductResult(name=name, url=url,
                         status="stale" if stale else "ok", generated=gen,
                         note="not regenerated this run")


def _index_entry(ctx: Ctx, r: ProductResult) -> dict:
    age = round(age_hours(r.generated, ctx.now), 3) if r.generated else None
    entry = {
        "url": r.url,
        "generated_iso": iso_z(r.generated) if r.generated else None,
        "generated_unix": unix_s(r.generated) if r.generated else None,
        "status": r.status,
        "age_hours": age,
        "stale": bool(r.status in ("stale", "absent", "failed")
                      or (age is not None and age > STALE_HOURS)),
    }
    if r.note:
        entry["note"] = r.note
    entry.update(r.extra)
    return entry


def build_index(ctx: Ctx, results: List[ProductResult],
                attempt_status: str) -> dict:
    by_name = {r.name: r for r in results}
    products = {name: _index_entry(ctx, by_name.get(name)
                                   or _existing_product(ctx, name))
                for name in _PRODUCT_URLS}
    return {
        "schema": SCHEMA_INDEX,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(ctx.now),
        "generated_unix": unix_s(ctx.now),
        "run_id": ctx.run_id,
        "stale_after_hours": STALE_HOURS,
        "products": products,
        "last_attempt_iso": iso_z(ctx.now),
        "last_attempt_status": attempt_status,
    }


def patch_index_texture(ctx: Ctx, res: ProductResult) -> None:
    """Stage index.json with ONLY ``products.texture`` replaced.

    A read-modify-write rather than a rebuild, because the other entries carry
    per-product detail this run knows nothing about (pfss's frame count, reuse
    flags and seed_set_id; the ephemeris' epoch count) and re-deriving them from
    the files on disk would silently drop it.  Promotion does the atomic
    ``os.replace``, so a reader sees either the old index or the whole new one.

    ``last_attempt_*`` is deliberately left alone: it describes the last FULL
    run, and a texture-only invocation must not relabel an earlier partial
    failure as a success.
    """
    prev = read_json(ctx.out / "index.json")
    if not isinstance(prev, dict) or not isinstance(prev.get("products"), dict):
        ctx.staging.write_json("index.json",
                               build_index(ctx, [res], "partial:texture-only"))
        return
    products = {k: (dict(v) if isinstance(v, dict) else v)
                for k, v in prev["products"].items()}
    for name in _PRODUCT_URLS:          # an index written before this product
        if not isinstance(products.get(name), dict):    # existed can lack keys
            products[name] = _index_entry(ctx, _existing_product(ctx, name))
    products["texture"] = _index_entry(ctx, res)
    # The kept entries' own timestamps stay untouched, but age_hours/stale are
    # DERIVED from the index's generation time, which this run moves forward --
    # leaving them would report a 9 h old PFSS product as fresh.
    for name, entry in products.items():
        if name == "texture":
            continue
        gen = parse_iso_z(entry.get("generated_iso") or "")
        entry["age_hours"] = (round(age_hours(gen, ctx.now), 3)
                              if gen else None)
        entry["stale"] = bool(
            entry.get("status") in ("stale", "absent", "failed")
            or (entry["age_hours"] is not None
                and entry["age_hours"] > STALE_HOURS))
    doc = dict(prev)
    doc.update({
        "schema": SCHEMA_INDEX,
        "pipeline_version": PIPELINE_VERSION,
        "generated_iso": iso_z(ctx.now),
        "generated_unix": unix_s(ctx.now),
        "run_id": ctx.run_id,
        "stale_after_hours": STALE_HOURS,
        "products": products,
    })
    doc.setdefault("last_attempt_iso", iso_z(ctx.now))
    doc.setdefault("last_attempt_status", "partial:texture-only")
    ctx.staging.write_json("index.json", doc)


# ─────────────────────────────────────────────────────────────────────────────
# Subcommands
# ─────────────────────────────────────────────────────────────────────────────

_STAGE_PREFIX = {"pfss": "pfss/", "active_regions": "ar/",
                 "ephemeris": "ephem/", "stats": "stats/",
                 "texture": "texture/", "events": "events/"}


def _prune_orphan_frames(ctx: Ctx, results: List[ProductResult]) -> None:
    """Delete published fNN.bin files the new manifest no longer references.

    A run that publishes fewer frames than the last one (window truncated by
    --max-frames, or a partial outage) would otherwise leave unreferenced
    binaries behind, and the publisher's rsync would carry them to gh-pages
    forever.
    """
    res = next((r for r in results if r.name == "pfss"), None)
    if res is None or res.status not in ("ok", "degraded"):
        return
    n = int(res.extra.get("frames") or 0)
    if n <= 0:
        return
    pfss_dir = ctx.out / "pfss"
    for p in sorted(pfss_dir.glob("f*.bin")):
        try:
            idx = int(p.stem[1:])
        except ValueError:
            continue
        if idx >= n:
            p.unlink(missing_ok=True)
            ctx.log("  removed orphan {0}".format(p.name))


def _prune_orphan_textures(ctx: Ctx, results: List[ProductResult]) -> None:
    """Delete published history frames the new texture.json no longer lists.

    Names are keyed on the slot's target time, so "orphan" is exactly "outside
    the current window" -- a run publishes 18 history frames per channel and
    the oldest one falls off every four hours.  Without this the publisher's
    rsync would carry every frame ever built to gh-pages forever; the 443 KB of
    stale schema-1 maps this stage left behind before the switch to per-slot
    names is what that looks like at one file per channel.
    """
    res = next((r for r in results if r.name == "texture"), None)
    if res is None or res.status not in ("ok", "degraded"):
        return
    doc = read_json(ctx.out / "texture/texture.json")
    if not doc:
        return
    keep = {str(fr.get("url")) for layer in (doc.get("layers") or [])
            for fr in (layer.get("frames") or []) if fr.get("url")}
    keep |= {str(layer.get("url")) for layer in (doc.get("layers") or [])}
    if not keep:
        return
    from .texture.export import HIST_NAME_RE
    tex_dir = ctx.out / "texture"
    for f in sorted(tex_dir.glob("*.jpg")):
        if HIST_NAME_RE.match(f.name) and f.name not in keep:
            f.unlink(missing_ok=True)
            ctx.log("  removed orphan texture {0}".format(f.name))


def cmd_all(args: argparse.Namespace) -> int:
    ctx = make_ctx(args)
    ctx.staging.reset()
    print("sol pipeline {0} run {1} -> {2}".format(
        PIPELINE_VERSION, ctx.run_id, ctx.out))
    results: List[ProductResult] = []
    failures: List[str] = []
    soft_failures: List[str] = []
    ss: Optional[pfss_seeds.SeedSet] = None

    def failed(name: str, exc: Exception) -> None:
        """Un-stage the half-written product and fall back to what is served."""
        print("  {0} FAILED: {1}".format(name, exc))
        ctx.staging.rollback(_STAGE_PREFIX[name])
        failures.append(name)
        results.append(_existing_product(ctx, name))

    try:
        try:
            res, ss = run_pfss(ctx)
            results.append(res)
        except Exception as exc:
            failed("pfss", exc)

        for name, fn in (("active_regions", lambda: run_regions(ctx, ss)),
                         ("ephemeris", lambda: run_ephem(ctx))):
            try:
                results.append(fn())
            except Exception as exc:
                failed(name, exc)

        # SOFT failure, same reasoning as texture below: DONKI has no SLA and
        # must never cost us a PFSS publish.
        try:
            results.append(run_events(ctx))
        except Exception as exc:                              # noqa: BLE001
            import traceback
            if ctx.verbose:
                traceback.print_exc()
            print("  events FAILED: {0}".format(exc))
            ctx.staging.rollback(_STAGE_PREFIX["events"])
            soft_failures.append("events")
            results.append(_existing_product(ctx, "events"))

        region_count = next((r.extra.get("count") for r in results
                             if r.name == "active_regions"), None)
        try:
            results.append(run_stats(ctx, region_count))
        except Exception as exc:
            failed("stats", exc)

        if ctx.with_texture:
            try:
                results.append(run_texture(ctx))
            except Exception as exc:
                # SOFT failure: see the module docstring.  SDO's web server
                # being down must not cost us a PFSS publish.
                import traceback
                if ctx.verbose:
                    traceback.print_exc()
                print("  texture FAILED: {0}".format(exc))
                ctx.staging.rollback(_STAGE_PREFIX["texture"])
                soft_failures.append("texture")
                results.append(_existing_product(ctx, "texture"))

        attempt = "ok"
        if failures or soft_failures:
            attempt = "partial:" + ",".join(failures + soft_failures)
        elif any(r.status in ("degraded", "stale")
                 for r in results if r.name != "texture"):
            # The texture's own status is excluded on purpose: a 20 h old AIA
            # frame is a cosmetic wobble, not a degraded data run.
            attempt = "degraded"
        # index.json is ALWAYS written, even when everything else failed: it is
        # the app's heartbeat and its only way to learn the data is stale.
        ctx.staging.write_json("index.json",
                               build_index(ctx, results, attempt))
        moved = ctx.staging.promote()
        _prune_orphan_frames(ctx, results)
        _prune_orphan_textures(ctx, results)
    finally:
        ctx.staging.cleanup()

    print("[publish] {0} file(s) into {1}".format(len(moved), ctx.out))
    for r in results:
        print("  {0:15s} {1:9s} {2}".format(r.name, r.status, r.note or ""))
    return 1 if failures else 0


_SINGLE_TO_PRODUCT = {"pfss": "pfss", "ephem": "ephemeris",
                      "regions": "active_regions", "stats": "stats",
                      "texture": "texture", "events": "events"}


def _single(args: argparse.Namespace, which: str) -> int:
    ctx = make_ctx(args)
    ctx.staging.reset()
    name = _SINGLE_TO_PRODUCT[which]
    results: List[ProductResult] = []
    rc = 0
    try:
        try:
            if which == "pfss":
                res, _ = run_pfss(ctx)
            elif which == "ephem":
                res = run_ephem(ctx)
            elif which == "regions":
                res = run_regions(ctx, None)
            elif which == "texture":
                res = run_texture(ctx)
            elif which == "events":
                res = run_events(ctx)
            else:
                res = run_stats(ctx, None)
            results.append(res)
            if res.status == "failed":
                rc = 1
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print("  {0} FAILED: {1}".format(which, exc))
            ctx.staging.rollback(_STAGE_PREFIX[name])
            results.append(_existing_product(ctx, name))
            rc = 1
        if which == "texture":
            patch_index_texture(ctx, results[0])
        else:
            ctx.staging.write_json("index.json", build_index(
                ctx, results, "ok" if rc == 0 else "partial:" + which))
        moved = ctx.staging.promote()
        _prune_orphan_frames(ctx, results)
        _prune_orphan_textures(ctx, results)
    finally:
        ctx.staging.cleanup()
    print("[publish] {0} file(s) into {1}".format(len(moved), ctx.out))
    return rc


def cmd_plan(args: argparse.Namespace) -> int:
    import contextlib
    ctx = make_ctx(args)
    want_json = bool(getattr(args, "json", False))
    # With --json, stdout must be parseable, so progress chatter goes to stderr.
    with contextlib.redirect_stdout(sys.stderr if want_json else sys.stdout):
        ss = acquire_seed_set(ctx)
        slots = pfss_timeline.resolve_slots(
            ctx.now, WINDOW_HOURS, FRAME_SPACING_HOURS, GONG_TOLERANCE_HOURS,
            simulate_gong_outage=ctx.simulate_gong_outage,
            verbose=ctx.verbose)
    if want_json:
        print(json_dumps({
            "now_iso": iso_z(ctx.now),
            "seed_set_id": ss.seed_set_id,
            "n_seeds": ss.n_lines,
            "n_bg": ss.n_bg,
            "srs_epoch_date": (ss.srs_epoch.isoformat() if ss.srs_epoch
                               else None),
            "slots": pfss_timeline.slots_to_json(slots),
        }))
        return 0
    print("now {0} (snapped to {1})".format(
        iso_z(ctx.now), iso_z(pfss_timeline.snap_down(ctx.now))))
    print("seed_set_id {0}  n_seeds {1} ({2} background)  srs {3}".format(
        ss.seed_set_id, ss.n_lines, ss.n_bg,
        ss.srs_epoch.isoformat() if ss.srs_epoch else "-"))
    print(pfss_timeline.plan_table(slots))
    resolved = sum(1 for s in slots if s.resolved)
    print("{0}/{1} slot(s) resolved, {2} distinct magnetogram(s)".format(
        resolved, len(slots), len(pfss_timeline.unique_keys(slots))))
    return 0 if resolved >= MIN_FRAMES_TO_PUBLISH else 1


def cmd_probe(args: argparse.Namespace) -> int:
    ctx = make_ctx(args)
    rc = 0
    print("[SRS]")
    regions, epoch, source = srs_src.newest_regions(
        ctx.cache / "srs", simulate_outage=ctx.simulate_srs_outage)
    if epoch is None:
        print("  UNAVAILABLE")
        rc = 1
    else:
        print("  source {0}, issued {1}, {2} region(s)".format(
            source, epoch.isoformat(), len(regions)))
        for r in regions[:12]:
            print("    AR{0}  lat {1:+3d}  cLon {2:3d}  area {3:5d}  "
                  "{4:6s} {5}".format(r["rnumber"], r["lat"], r["cLon"],
                                      r["area"], r["zurich"], r["magtype"]))
        if len(regions) > 12:
            print("    ... {0} more".format(len(regions) - 12))

    print("[GONG]")
    # Say which path is being exercised. Without this, a green probe leaves you
    # unable to tell whether NSO unblocked us or the relay is doing the work --
    # and a red one leaves you unable to tell whether the relay is even wired
    # up (see docs/GONG-RELAY.md and footgun 33).
    if gong_src.relay_enabled():
        from .config import GONG_PROXY_BASE, GONG_PROXY_TOKEN
        print("  via relay {0} (token {1})".format(
            GONG_PROXY_BASE, "set" if GONG_PROXY_TOKEN else "MISSING"))
    else:
        print("  direct to {0} (no relay configured)".format(GONG_BASE))
    cand = gong_src.gong_list(ctx.now)
    if not cand:
        print("  UNAVAILABLE (no listing)")
        rc = 1
    else:
        print("  {0} file(s) across 3 day directories; newest 5:".format(
            len(cand)))
        for dt, url in cand[-5:]:
            print("    {0}  age {1:5.2f} h  {2}".format(
                iso_z(dt), age_hours(dt, ctx.now),
                gong_src.gong_file_key(url)))
        newest_age = age_hours(cand[-1][0], ctx.now)
        ok = newest_age < GONG_TOLERANCE_HOURS
        print("  newest magnetogram age {0:.2f} h -> {1}".format(
            newest_age, "OK" if ok else "STALE (> tolerance)"))
        if not ok:
            rc = 1

    print("[SWPC digest endpoints]")
    from .config import F107_URL, SUNSPOTS_URL, XRAY_FLARES_URL
    from .io_utils import http_get_json
    for label, url in (("sunspots", SUNSPOTS_URL), ("flares", XRAY_FLARES_URL),
                       ("f10.7", F107_URL)):
        try:
            data = http_get_json(url)
            n = len(data) if isinstance(data, list) else 1
            print("  {0:9s} OK ({1} record(s))".format(label, n))
        except Exception as exc:
            print("  {0:9s} FAIL {1}".format(label, exc))
            rc = 1
    return rc


def cmd_validate(args: argparse.Namespace) -> int:
    from .validate import validate
    ok, text = validate(root=args.root, base_url=args.url,
                        strict=bool(args.strict), verbose=bool(args.verbose))
    print("[validate] {0}".format(args.url or args.root or "."))
    print(text)
    return 0 if ok else 1


# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────

def _add_common(p: argparse.ArgumentParser, *, pfss_flags: bool = True) -> None:
    p.add_argument("--out", default=DEFAULT_OUT,
                   help="output data root (default: %(default)s)")
    p.add_argument("--cache", default=CACHE_DIR,
                   help="cache root (default: %(default)s)")
    p.add_argument("-v", "--verbose", action="store_true")
    # Above the pfss_flags gate on purpose: the outage drill has to be
    # reachable from `pipeline events`, which does not take the PFSS flags.
    p.add_argument("--simulate-donki-outage", action="store_true",
                   help="pretend DONKI is down (exercises the events cache "
                        "and the rollback-to-published path)")
    # TEX_HIST_MAX_NEW_PER_RUN exists to protect a ~9 minute CI job. A
    # workstation has no such limit, so warming the whole 72 h window in one
    # go (95 frames, ~13 min measured) and publishing it is the fast way to
    # give CI a complete window to seed from.
    p.add_argument("--max-new-textures", type=int, default=None, metavar="N",
                   help="override the per-run cap on NEW history texture "
                        "frames (default {0}; use a large number locally to "
                        "fill the whole window)".format(
                            TEX_HIST_MAX_NEW_PER_RUN))
    if not pfss_flags:
        return
    p.add_argument("--max-frames", type=int, default=None,
                   help="use only the N newest slots (quick local test)")
    p.add_argument("--keep-npz", action="store_true",
                   help="do not prune old traced-frame caches")
    p.add_argument("--from-cache", action="store_true",
                   help="re-export from cached npz: no network, no PFSS solve")
    p.add_argument("--force", action="store_true",
                   help="ignore traced-frame caches and retrace")
    p.add_argument("--simulate-gong-outage", type=int, default=0,
                   metavar="N", help="pretend the N newest slots have no GONG")
    p.add_argument("--simulate-srs-outage", action="store_true",
                   help="pretend SRS is down (exercises the seed cache)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Sol data pipeline {0}".format(PIPELINE_VERSION))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("all", help="build every product + index.json")
    _add_common(p)
    p.add_argument("--with-texture", action="store_true",
                   help="also build texture/ (default ON in the CI workflow)")
    p.set_defaults(func=cmd_all)

    p = sub.add_parser("pfss", help="PFSS field-line frames")
    _add_common(p)
    p.set_defaults(func=lambda a: _single(a, "pfss"))

    p = sub.add_parser("ephem", help="spacecraft ephemerides")
    _add_common(p, pfss_flags=False)
    p.set_defaults(func=lambda a: _single(a, "ephem"))

    p = sub.add_parser("regions", help="active-region table")
    _add_common(p)
    p.set_defaults(func=lambda a: _single(a, "regions"))

    p = sub.add_parser("stats", help="solar-activity digest")
    _add_common(p, pfss_flags=False)
    p.set_defaults(func=lambda a: _single(a, "stats"))

    p = sub.add_parser("texture", help="AIA 171 Carrington sphere texture")
    _add_common(p, pfss_flags=False)
    p.set_defaults(func=lambda a: _single(a, "texture"))

    p = sub.add_parser("events", help="flare + CME catalog (CCMC DONKI)")
    _add_common(p, pfss_flags=False)
    p.set_defaults(func=lambda a: _single(a, "events"))

    p = sub.add_parser("plan", help="print the slot table")
    _add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("probe-sources", help="upstream health check")
    _add_common(p)
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("validate", help="validate a data tree")
    p.add_argument("--root", default=None, help="local data directory")
    p.add_argument("--url", default=None, help="base URL of a published tree")
    p.add_argument("--strict", action="store_true",
                   help="treat warnings as failures")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_validate)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "validate" and not (args.root or args.url):
        args.root = DEFAULT_OUT
    try:
        return int(args.func(args))
    except PipelineError as exc:
        print("PIPELINE ERROR: {0}".format(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":                                # pragma: no cover
    raise SystemExit(main())
