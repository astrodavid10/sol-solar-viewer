# Third-party components

Sol itself is MIT licensed (see `LICENSE.txt`). It redistributes the components
below, each under its own terms.

---

## three-wwt (vendored source)

`src/three/three-wwt/` — MIT. Vendored from
[cosmicds/three-wwt](https://github.com/cosmicds/three-wwt) at commit
`80b95028d2b1e9ba7dbc117c314b25f535e80847`, with local modifications documented
in each file's header. The upstream license text is kept verbatim alongside the
source at `src/three/three-wwt/LICENSE`.

Vendored rather than taken from npm because `@cosmicds/three-wwt@0.0.3` bundles
a duplicate copy of the WWT engine (1.7 MB) and ships a broken CJS entry point.

## Roboto / Roboto Condensed

`src/assets/Roboto.ttf`, `src/assets/RobotoCondensed.ttf`,
`src/assets/RobotoCondensed-Italic.ttf` — Apache License 2.0. Copyright Google
Inc. The fonts self-declare this in their `name` tables; the license text is at
<https://www.apache.org/licenses/LICENSE-2.0>.

## Highway Gothic Narrow

`src/assets/HighwayGothicNarrow.ttf` — **terms unverified.**

The font's `name` table records `copyright: "2009"` and
`trademark: "Ash Pikachu Font"`, but carries **no license record (nameID 13) and
no license URL (nameID 14)**. Highway Gothic derives from the US FHWA Standard
Alphabets, which are themselves a US government work, but that says nothing
about the terms of this particular digitization.

**This is not specific to Sol.** The file here is byte-identical
(SHA-256 `7b98172d…`) to the one in `exo-sonification`, and the same font ships
in at least seven projects in this family — including `minids`, which is already
published publicly under MIT. Sol therefore introduces no exposure that does not
already exist, and the question of terms is an organization-wide one to settle
once rather than a Sol blocker.

If it is ever settled the other way, [Overpass](https://overpassfont.org/) is an
open FHWA-derived face under the SIL Open Font License and is a drop-in
replacement.

## WorldWide Telescope engine

`@wwtelescope/engine`, `@wwtelescope/engine-pinia` and related packages are
consumed from npm, not vendored, and carry their own licenses (MIT). The app
also fetches the WWT imageset catalog from `worldwidetelescope.org` at
runtime; `public/hips-surveys.wtml` is an excerpt of that catalog.

## Data sources

Not redistributed as code, but fetched or digested at build/run time. All are
public, US-government or publicly-funded scientific products:

- **NASA SDO** imagery (`sdo.gsfc.nasa.gov`) — hotlinked stills and movies.
- **NOAA SWPC** (`services.swpc.noaa.gov`) — space-weather products.
- **NSO GONG** (`gong2.nso.edu`) — magnetograms feeding the PFSS model.
- **NASA CCMC DONKI** (`kauai.ccmc.gsfc.nasa.gov`) — flare and CME catalog.
  CCMC asks that DONKI be described as research-grade rather than an official
  forecast; the app carries that wording on every event card.
- **JPL Horizons** — spacecraft ephemerides, via `astroquery`.
- **ROB/SILSO** sunspot numbers, relayed by NOAA SWPC.

## Institutional marks

Two marks of the INTUITIVE Planetarium at the U.S. Space & Rocket Center ship in
the bundle and are used as a credit:

- `src/assets/ip-ussrc.png` — the USSRC lock-up.
- `src/assets/ip-wordmark-white.svg` — the planetarium ICON. The filename says
  "wordmark", but the artwork is square (`viewBox="0 0 160 160"`) and its ids are
  `Logos_Icon_1` / `White_Icon_1`; per the brand kit that is the icon, not the
  wordmark.

Their use here is authorized by the planetarium's director, who is the author of
this proof of concept. The marks themselves are not covered by this repository's
MIT grant — the MIT terms apply to the software, not to the institution's
trademarks. The brand kit also requires that the planetarium wordmark never
appear without the USSRC logo, which is why `InfoModal`'s credit row pairs
them.
