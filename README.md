# Sol — the Sun Right Now

A mobile-first solar data explorer for planetarium guests ("Data to Dome, Dome to Phone").
Scan a QR code during or after a show and take the Sun home with you.

One screen: the Sun as a sphere you can turn, with 72 hours of its recent history under a
scrubber.

- **The Sun itself** — a real SDO image of the photosphere, reprojected onto the sphere in
  Carrington coordinates. Five channels to switch between: three AIA wavelengths, the visible
  Sun, and the magnetic map. The hemisphere Earth cannot see is dimmed, because it is a
  stylized fill rather than an observation.
- **Its magnetic field** — PFSS field lines computed from GONG magnetograms by our own
  pipeline (the same model and colors as the dome show), morphing across 19 frames spanning
  the last 72 hours.
- **What is flying through it** — Parker Solar Probe, Solar Orbiter and STEREO-A where they
  really are, from JPL Horizons.
- **What is happening right now** — flare class, solar wind speed, the Kp/aurora outlook and
  the day's sunspot count from NOAA SWPC, plus flares and CMEs from NASA CCMC's DONKI
  catalog marked on the timeline.

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
