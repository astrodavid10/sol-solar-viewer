# Sol — the Sun Right Now

A mobile-first solar data explorer for planetarium guests ("Data to Dome, Dome to Phone").
Scan a QR code during or after a show and take the Sun home with you:

- **Sun Now** — live full-disk imagery from NASA SDO in eight wavelengths, with pinch-zoom
  up to 4K and 48-hour movie loops, streamed straight from the GSFC archive.
- **3D** — the Sun in WorldWide Telescope's solar-system mode, wrapped in its actual magnetic
  field: PFSS field lines computed from GONG magnetograms (the same model and colors as the
  dome show), animated over the last 48 hours, with Parker Solar Probe and Solar Orbiter
  shown where they really are.
- **Live conditions** — current flare activity, solar wind speed, and geomagnetic (aurora)
  status from NOAA SWPC.

## Stack

Vue 3 + Vuetify (CosmicDS data-story stack) around the
[WWT WebGL engine](https://github.com/WorldWideTelescope/wwt-webgl-engine)
(`@wwtelescope/engine-pinia`), with a vendored copy of
[cosmicds/three-wwt](https://github.com/cosmicds/three-wwt) syncing a three.js overlay for the
field lines and spacecraft. A Python pipeline (`pipeline/`) runs in GitHub Actions every 4 hours:
GONG magnetogram → PFSS (sunkit-magex) → compact quantized binary frames published to GitHub
Pages alongside the app.

## Development

```bash
yarn install
yarn serve        # dev server; test on a phone via your LAN IP
yarn lint && yarn typecheck && yarn build
```

Data for the dev server (conda env `sdo`):

```powershell
conda run -n sdo python -m pipeline all --out public\data -v
```

See `CLAUDE.md` for architecture notes and a list of hard-won footguns (WWT camera semantics,
CORS constraints, binary data contract) — read it before changing anything 3D or pipeline-facing.

## Credits

Imagery: NASA/SDO (AIA, HMI) and the AIA, EVE, and HMI science teams. Space weather data:
NOAA SWPC. Magnetograms: GONG/NSO. Spacecraft ephemerides: JPL Horizons / ROB SWHV.
Engine: WorldWide Telescope. Built on the CosmicDS data-story framework.
