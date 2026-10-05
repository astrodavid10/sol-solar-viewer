# The data contract between `pipeline/` and `src/`

Everything the app reads lives under `data/` on the `gh-pages` branch, written by
`python -m pipeline` and fetched same-origin by the app. This file is the single written
record of that contract. `pipeline/validate.py` enforces most of it; the app's parsers
(`src/data/pfss.ts`, `src/three/sunSurface.ts`, `src/data/*.ts`) read it.

**Rules**

1. **Additive only.** A new field or file may be added; an existing one is never renamed,
   retyped or removed without bumping the schema AND keeping the app able to read the old
   one. A reader must ignore keys it does not know.
2. **Change it in all three places in one commit**: the pipeline writer, the app reader,
   and this file. The validator gets a check for anything a guest would see wrong.
3. **Times** are UTC ISO 8601 with a `Z` (`2026-10-05T10:30:00Z`); every `*_iso` that has a
   `*_unix` twin agrees with it to the second. Upstream timestamps without a zone are UTC
   (footgun 52).
4. **Binary files are little-endian, raw, never pre-gzipped** (footgun 13: GitHub Pages
   gzips transparently and would not set Content-Encoding on a `.gz`).
5. **Frames of reference:** field lines, the Sun's surface, sunspots and the solar wind are
   in the rotating Carrington frame and reach the scene through each frame's
   `quat_carr_to_ecl`. CME directions are already in ecliptic J2000 and take NO rotation
   (footgun 25). WWT's own world frame is ecliptic with Y and Z swapped (footgun 47); that
   swap lives in the three.js camera, never in this data.

---

## `index.json` — `sol.index/1`

The heartbeat. Written on every run that promoted anything, even when every product failed.

| field | meaning |
|---|---|
| `generated_iso`, `generated_unix`, `run_id`, `pipeline_version` | this run |
| `last_attempt_iso`, `last_attempt_status` | `ok`, `degraded` (some product is), or `partial:<products>` (stages that raised or were rolled back) |
| `stale_after_hours` | 8; a product older than this is `stale` |
| `products.<name>` | one entry per product below |

Each product entry: `status` (`ok` / `degraded` / `stale` / `absent`), `url`,
`generated_iso`/`generated_unix`, `age_hours` (age of the manifest WRITE, which says nothing
about the data), `note`, and `last_error` when a stage raised or failed validation.
`last_error` starting `UPSTREAM MOVED:` means an endpoint moved (footgun 58). Products add
their own fields:

- `pfss`: `data_age_hours` (the honest freshness number), `frames`, `reused`, `seed_set_id`,
  `n_lines`, `n_verts_total`.
- `texture`: `obs_iso`, `obs_age_hours` (default channel), `layers` (count),
  `layers_expected`, `layers_missing`, `layers_carried`, `layer_ages_hours`, history counters.
- `active_regions`: `count`, `history_days`. `events`: `flares`, `cmes`, `x_class`,
  `fast_cmes`. `ephemeris`: `bodies`, `epochs`.

## `pfss/` — `sol.pfss/2` (field lines)

`manifest.json`: `window_hours` (72), `frame_spacing_hours` (4), `newest_mag_iso`,
`newest_mag_unix`, `newest_mag_age_hours`, `status`, `model` (PFSS settings),
`constants`, `render_hints`, `active_regions_url`, `seed_regions` (NOAA numbers aligned with
`ar_index`, see below), and:

- `geometry`: `topology_url`, `topology_bytes`, `n_lines`, `n_bg_lines`, `n_verts_total`,
  `seed_set_id`, `frame` (`HeliographicCarrington`), `units` (`R_sun`), `verts_per_line`.
- `quantization.xyz`: `uint16`, interleaved, `world_rsun = q / 65535 * 5.2 - 2.6`
  (`limit_rsun` 2.6, max error ~28 km).
- `frames[]`, oldest first: `index`, `url` (`fNN.bin`), `bytes`, `target_iso` (the 4 h slot
  this frame fills), `mag_iso`/`mag_unix`/`mag_age_hours`/`mag_file` (the GONG magnetogram
  actually used), `reused` (true when a slot had no fresh magnetogram and repeats an older
  one), `carrington_rotation`, `l0_deg`, `b0_deg`, `p_deg`, `hci_rot_deg`,
  `quat_carr_to_ecl`, `mat3_carr_to_ecliptic_j2000`, `mat3_heeq_to_ecliptic_j2000`,
  `n_valid`, `n_closed`, `n_open_pos`, `n_open_neg`.

`topology.bin`, written once per seed set and shared by every frame:

```
char[8]            "SOLTOPO1"
uint32             n_lines
uint32             n_verts_total
uint32             n_bg_lines         first n_bg_lines rows are the background grid
uint32             reserved (0)
char[8]            seed_set_id        ascii hex
uint32[n_lines+1]  line_offset        cumulative; [n_lines] == n_verts_total
int16[n_lines]     seed_lat_cdeg      seed latitude * 100, degrees
uint16[n_lines]    seed_lon_u16       seed Carrington longitude * 65536/360
int16[n_lines]     ar_index           index into manifest.seed_regions; -1 = background
```

`fNN.bin`, one per frame (highest index newest):

```
char[8]                  "SOLPFRM1"
uint32                   frame_index
uint32                   n_lines            == topology
uint32                   n_verts_total      == topology
uint32                   mag_unix
uint32                   reserved (0)
uint32                   reserved (0)
uint16[n_verts_total*3]  xyz, interleaved x,y,z (quantization above)
int8[n_lines]            polarity           0 closed, +1 open out, -1 open in (per frame)
uint8[n_lines]           valid              1 real line, 0 padding (footgun 9)
```

`ar_index i` means `seed_regions[i]`, the regions the seed set was frozen against. It is
NOT an index into today's `ar/regions.json`, which CI regenerates every 4 h (footgun 50).

## `texture/` — `sol.texture/5` (sphere maps)

`texture.json` keeps its schema-1 top level describing the DEFAULT channel's newest map
(`url`, `width` 4096, `height` 2048, `projection` plate carree, `lon_at_u0_deg` 0,
`north_up`, `obs_iso`, `sub_earth_carr_lon_deg`, `sub_earth_lat_deg`, `far_side`,
`far_side_max_age_hours`, `source`, `near_side_half_angle_deg`), so an old reader still works.
`disk_still` (optional, since 2026-10-05): `url`, `width` and `height` (1024), `bytes`,
`obs_iso`, `source_url` — the default channel's newest SDO still as a plain picture. The app
shows it behind its loading cover and on the failure cards when the 3D view cannot load
(T33). Absent means the app shows text only; it never substitutes another image.

`layers[]` is one entry per channel published this run, default first:

- `channel` (SDO product code: `0171`, `0304`, `0193`, `HMIIC`, `HMIB`), `label`,
  `wavelength_angstrom` (null for HMI), `far_side` (`quiet` for EUV, `flat` for HMI: no
  invented structure, footgun 22), `url`, `bytes`, `obs_iso`, `sub_earth_*`, `source_url`.
- `status` and `obs_age_hours` (per layer, since 2026-10-05), and `carried: true` when the
  channel failed this run and its last good layer stands in (inside its age ceiling).
- `off_limb`: `url`, `size`, `bytes`, `half_width_rsun`, `tiers[]` (`size`, `url`, `bytes`)
  — camera-facing corona billboard, black where the disk is (footgun 29).
- `high_res` (optional): an 8192x4096 newest map, `url`, `width`, `height`, `bytes`,
  `obs_iso`, `sub_earth_*`, `source_url` (footgun 40).
- `frames[]`, oldest first: one map per PFSS slot, keyed on `target_iso` (footgun 36):
  `index`, `target_iso`, `url`, `bytes`, `width`, `height`, `obs_iso`, `sub_earth_*`,
  `source_url`, optional `near_side` (`url`, `width`, `height`, `bytes`, `lon_center_deg`,
  `crval1_deg`, `crpix1`, `crpix2`, `cdelt_deg`, `lon_span_deg`, `lat_span_deg`). The newest
  frame is the layer's own full-size map. A slot with no source image is ABSENT, never filled
  with another hour's picture.

A channel absent from `layers` was not published this run (source too old, failed its limb
guard with nothing to carry, or unavailable). The app offers only published channels.

## `ar/regions.json` — `sol.ar/3` (sunspot regions)

`regions[]` is today's NOAA SRS list in `ar_index` order: `number`, `location`, `lat_deg`
(|lat| <= 60), `lon_deg`, `carr_lon_deg` [0, 360), `n_spots`, `area_uh`, `extent_deg`,
`zurich`, `mag_type`, `is_complex`, `seed_count`. Also `count`, `srs_epoch_date`, `source`,
`status`. `history[]` has one entry per day with its own `regions` (same fields, NO
`seed_count`) and `region_count`/spot totals (footgun 30).

## `events/events.json` — `sol.events/1` (flares and CMEs)

`window_hours` (must equal the PFSS window), `status`, `source`, `fetched_iso` (when DONKI
was actually fetched; older than `generated_iso` when a cache served), `counts`
(`flares`, `cmes`, `x_class`, `fast_cmes`), `disclaimer` (DONKI's research-grade wording,
which must reach guest-facing copy), and `events[]`. Each event: `kind` (`flare`/`cme`), `id`,
times as `*_iso`/`*_unix`, `ar_number` (NOAA numbering; DONKI's is 10000 higher, footgun
23), `ar_index` (into `ar/regions.json`, -1 when no current region matches), flare `class`
and `source_*` location, CME `speed_kms`, `half_angle_deg` and `dir_ecl` (a unit vector in
ecliptic J2000, used with no rotation).

## `ephem/spacecraft.json` — `sol.ephem/1`

`epochs_unix[]`, `now_index`, `now_iso`, `step_hours`, `span_days`, `frame`, `units` (AU),
`bodies` (Parker Solar Probe, Solar Orbiter, Earth: positions aligned with `epochs_unix`),
`at_earth` (spacecraft that are at Earth heliocentrically, e.g. PUNCH, Proba-3).

## `stats/summary.json` — `sol.stats/1`

Server-side digests of NOAA SWPC files too big for a phone: `sunspotNumber`, `f107`,
`latestFlare`, `flares24h`, `flaresWindow`, `biggestFlare30d`, `activeRegionCount`,
`windWindow` (`points` strictly increasing and never later than `generated_iso`, footgun 52),
`carrington`, `sources`.
