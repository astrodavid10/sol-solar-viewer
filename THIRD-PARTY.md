# Third-party components

Sol itself is MIT licensed (see `LICENSE.txt`). It redistributes the components
below, each under its own terms.

---

## three-wwt (vendored source)

`src/three/three-wwt/` — MIT. Vendored from
[cosmicds/three-wwt](https://github.com/cosmicds/three-wwt) at commit
`80b95028d2b1e9ba7dbc117c314b25f535e80847`, with local modifications documented
in each file's header. The upstream licence text is kept verbatim alongside the
source at `src/three/three-wwt/LICENSE`.

Vendored rather than taken from npm because `@cosmicds/three-wwt@0.0.3` bundles
a duplicate copy of the WWT engine (1.7 MB) and ships a broken CJS entry point.

## Roboto / Roboto Condensed

`src/assets/Roboto.ttf`, `src/assets/RobotoCondensed.ttf`,
`src/assets/RobotoCondensed-Italic.ttf` — Apache License 2.0. Copyright Google
Inc. The fonts self-declare this in their `name` tables; the licence text is at
<https://www.apache.org/licenses/LICENSE-2.0>.

## Highway Gothic Narrow

`src/assets/HighwayGothicNarrow.ttf` — **terms unverified.**

The font's `name` table records `copyright: "2009"` and
`trademark: "Ash Pikachu Font"`, but carries **no licence record (nameID 13) and
no licence URL (nameID 14)**. Highway Gothic derives from the US FHWA Standard
Alphabets, which are themselves a US government work, but that says nothing
about the terms of this particular digitisation.

This file is redistributed here and served from the published site. Before this
repository is relied on by anyone else, either confirm the terms with the
digitiser or replace it — [Overpass](https://overpassfont.org/) is an open
FHWA-derived face under the SIL Open Font License and is a drop-in candidate.

## WorldWide Telescope engine

`@wwtelescope/engine`, `@wwtelescope/engine-pinia` and related packages are
consumed from npm, not vendored, and carry their own licences (MIT). The app
also fetches the WWT imageset catalogue from `worldwidetelescope.org` at
runtime; `public/hips-surveys.wtml` is an excerpt of that catalogue.

## Data sources

Not redistributed as code, but fetched or digested at build/run time. All are
public, US-government or publicly-funded scientific products:

- **NASA SDO** imagery (`sdo.gsfc.nasa.gov`) — hotlinked stills and movies.
- **NOAA SWPC** (`services.swpc.noaa.gov`) — space-weather products.
- **NSO GONG** (`gong2.nso.edu`) — magnetograms feeding the PFSS model.
- **NASA CCMC DONKI** (`kauai.ccmc.gsfc.nasa.gov`) — flare and CME catalogue.
  CCMC asks that DONKI be described as research-grade rather than an official
  forecast; the app carries that wording on every event card.
- **JPL Horizons** — spacecraft ephemerides, via `astroquery`.
- **ROB/SILSO** sunspot numbers, relayed by NOAA SWPC.

## Institutional mark

`src/assets/ip-ussrc.png` is the mark of the INTUITIVE Planetarium at the U.S.
Space & Rocket Center, used as a credit. It is not covered by this
repository's MIT grant, and its presence does not imply the institution
endorses this software.
