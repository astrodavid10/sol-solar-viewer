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

## Overpass

`src/assets/Overpass-SemiBold.ttf` — SIL Open Font License 1.1 (the font is dual
licensed OFL 1.1 / LGPL 2.1). Copyright 2016 Red Hat, Inc. The license text is
redistributed with it at `src/assets/Overpass-LICENSE.md`, and the font
self-declares both the license (name record 13) and its URL (record 14) in its
own `name` table. Taken from
[RedHatOfficial/Overpass](https://github.com/RedHatOfficial/Overpass) v3.0.5.

This is the app's only bundled face, used for the app title and the info-modal
heading. One weight, `font-display: swap` — it is decoration on a short string
and must never hold up the first paint.

**It replaced Highway Gothic Narrow**, which shipped here until this repository
was made public. That file recorded `copyright: "2009"` and
`trademark: "Ash Pikachu Font"` but carried **no license record and no license
URL**, and publishing the repository would have redistributed it on unknown
terms. Overpass descends from the same US FHWA Standard Alphabets, so the change
is within the same lineage rather than a new look.

`Roboto.ttf`, `RobotoCondensed.ttf` and `RobotoCondensed-Italic.ttf` were also
removed. They had **no `@font-face` rule**, so the browser never loaded them —
naming "Roboto" in a CSS stack only ever resolved to a system copy where one
existed. They were 500 KB of dead weight in every clone.

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
