// =====================================================================
// WWT solar-system stage — entering 3D mode and framing the Sun
// =====================================================================
// Everything in here is load-bearing and was verified against the engine
// source; the comments say why, because the failure modes are all "looks
// almost right" (see CLAUDE.md footguns 1, 2, 11, 14).
//
// FRAME — and this file is the one place in the app that works in WWT's own
// coordinates rather than ours, so read this before touching anything below.
//
// With `target = SolarSystemObjects.custom` and `viewTarget = (0,0,0)`, WWT's
// solar-system world frame has the Sun at the ORIGIN, AU units, and is
// heliocentric ecliptic J2000 WITH Y AND Z SWAPPED:
//
//     (x, y, z)_wwt = (X, Z, Y)_ecliptic     — +Y is the ecliptic pole.
//
// That is NOT the frame our PFSS quaternions, Horizons positions and solar
// axis are expressed in (see data/solarFrames.eclipticToWwtWorld and CLAUDE.md
// footgun 47). Everywhere else in the app the difference is handled once, on
// the three camera (three/worldFrame.ts). Here it cannot be: this file writes
// WWT's `lat`/`lng`/`rotation` directly, so any physics vector that meets the
// camera formulas below has to be pushed through `eclipticToWwtWorld` FIRST.
// Currently that is exactly one quantity — the Sun's rotation axis, in
// `solarAxis()` — plus Earth's direction in `earthFacingCamera()`.

import { EngineSetting, WWTControl } from "@wwtelescope/engine";

import {
  R_SUN_AU,
  Vec3,
  eclipticToWwtWorld,
  julianDateNow,
  sunEclipticLongitudeDeg,
  sunPoleEcliptic,
} from "../data/solarFrames";

/** SolarSystemObjects.custom — keeps OUR viewTarget instead of a planet's. */
const SS_CUSTOM = 20;

/**
 * WWT's solar-system camera, decoded from the engine (setupMatricesSolarSystem,
 * Matrix3d._rotationX/_rotationY/transform/_multiply). At our zooms
 * `cameraDistance > 0.0008` forces `angle` to 0, so the camera reduces to
 *
 *     viewAdjust = rotX(-lat) . rotY(-lng)            (row-vector, v * M)
 *     cameraPosition = d * ( -cos(lat) sin(lng), sin(lat), cos(lat) cos(lng) )
 *     lookUp         = sin(-rotation) * e1 + cos(-rotation) * e2
 *       e1 = ( cos(lng), 0, sin(lng) )
 *       e2 = ( sin(lat) sin(lng), cos(lat), -sin(lat) cos(lng) )
 *
 * in WWT's WORLD coordinates, i.e. ecliptic J2000 with Y and Z swapped (file
 * header). All three formulas were re-checked against the engine on
 * 2026-08-24 by running Matrix3d._rotationX/_rotationY/transform directly:
 * they reproduce to 0.00e+00 and are exactly right. What was wrong for four
 * sessions was only the INTERPRETATION of which axis is which.
 *
 * Read in the correct frame they say something much simpler than the old
 * comment here claimed: since +Y IS the ecliptic pole, `lat` is ECLIPTIC
 * LATITUDE and `lng` is ecliptic longitude, offset by 90 deg
 * (lng = L - 90 puts the camera at ecliptic longitude L). lat = lng = 0 is a
 * point ON the ecliptic at longitude 90, not "straight over the ecliptic
 * pole". The Earth-facing framing therefore wants lat = 0 — Earth's
 * heliocentric ecliptic latitude is under 0.0003 deg — and never goes near
 * the clamp below.
 */

/**
 * Where lat runs out. The poles of this lat/lng sphere are +/-Y, which IS the
 * ecliptic pole: an ordinary place to look from, but `lng` stops having any
 * effect there, so dragging sideways would go dead. 89.5 keeps that guard
 * while costing nothing — the framings this app computes sit at lat 0 (Earth)
 * and the free-orbit path bounds itself against the SOLAR axis instead
 * (MAX_SOLAR_LAT_DEG), which is 7.25 deg from this one.
 */
const MAX_LAT_DEG = 89.5;

/** Framing: camera distance = 2.8 R_sun × the vertical-fit factor × aspect pad. */
const HOME_RADII = 2.8;

/** 1/tan(22.5°): WWT's FOV is a fixed π/4 VERTICAL (footgun 11). */
const FIT_FACTOR = 2.414;

/** d = 1.43 R_sun — close enough to fly among the arcades, not inside the Sun. */
export const MIN_ZOOM = 0.015;

/** d = 1.11 AU — far enough to see Earth's orbit, not the outer system. */
export const MAX_ZOOM = 2.5;

/** Settings applied on entry. Order does not matter among these; that they all
 *  get applied does. */
const STAGE_SETTINGS: EngineSetting[] = [
  // Nothing but the Sun: at our zooms a star field is just noise, and the
  // Milky Way pass costs a full-screen textured quad every frame.
  ["solarSystemStars", false],
  ["solarSystemCosmos", false],
  ["solarSystemMilkyWay", false],
  ["solarSystemMinorPlanets", false],
  // Orbits are the guest-facing noise knob (layers.orbits); off by default.
  ["solarSystemOrbits", false],
  ["solarSystemLighting", true],
  // This pass draws the Sun sphere ITSELF. Turning it off leaves field lines
  // arcing off nothing. Other planets are sub-pixel at our zooms.
  ["solarSystemPlanets", true],
  ["actualPlanetScale", true],
  // Must stay 1, or footpoints float off the sphere (footgun 2).
  ["solarSystemScale", 1],
  ["showCrosshairs", false],
  ["showConstellationFigures", false],
  // "Boundries" is the engine's own typo — intentional.
  ["showConstellationBoundries", false],
  ["galacticMode", false],
  ["showEcliptic", false],
  ["showGrid", false],
];

export interface SunStageHost {
  applySetting: (setting: EngineSetting) => void;
  setBackgroundImageByName: (name: string) => void;
  setForegroundImageByName: (name: string) => void;
  setClockSync: (synced: boolean) => void;
  setTime: (time: Date) => void;
}

// The engine's .d.ts comments out CameraParameters.viewTarget and does not
// expose the solar-system mode getter, both of which ship in the bundle. This
// is the minimum shape we touch.
interface MutableCamera {
  lat: number;
  lng: number;
  zoom: number;
  rotation: number;
  angle: number;
  target: number;
  targetReferenceFrame: string;
  viewTarget: { x: number; y: number; z: number };
  copy: () => MutableCamera;
}

interface MutableRenderContext {
  viewCamera: MutableCamera;
  targetCamera: MutableCamera;
}

function renderContext(): MutableRenderContext | null {
  const control = WWTControl.singleton;
  if (!control?.renderContext) { return null; }
  return control.renderContext as unknown as MutableRenderContext;
}

// ---------------------------------------------------------------------
// Framing maths
// ---------------------------------------------------------------------

/**
 * Aspect compensation, copied from exo-sonification's `tfAspectPad()`
 * (src/exo-sonification.vue L654). WWT's solar-system projection is
 * `perspectiveFovLH(π/4, width/height, …)` with the FOV fixed VERTICALLY, so
 * the horizontal field narrows as the viewport gets taller than it is wide. A
 * feature of radius R fits vertically at distance 2.414·R and horizontally at
 * 2.414·R·(h/w) — without this factor a portrait phone frames ~2.2x too tight.
 */
export function aspectPad(): number {
  const w = window.innerWidth;
  const h = window.innerHeight;
  if (!(w > 0) || !(h > 0)) { return 1; }
  return Math.max(1, h / w);
}

/**
 * Zoom that frames `radii` solar radii on the SHORT screen axis.
 *
 * Extracted from `zoomHome` when the eruption replay needed to frame something
 * ten times bigger than the Sun: a CME reaches 21.5 R_sun, so the one place
 * that knows how many R_sun a zoom shows had to be callable with a number other
 * than HOME_RADII. Clamped, because the answer for a big enough radius is
 * outside the engine's own zoom range.
 */
export function zoomForRadii(radii: number): number {
  return clampZoom((9 / 4) * radii * R_SUN_AU * FIT_FACTOR * aspectPad());
}

/** Zoom that frames HOME_RADII solar radii on the short screen axis. */
export function zoomHome(): number {
  return zoomForRadii(HOME_RADII);
}

/** The engine's solar-system zoom↔distance relation (footgun 14). */
export function cameraDistanceAu(zoom: number): number {
  return (4 * zoom) / 9 + 1e-6;
}

function clampZoom(zoom: number): number {
  return Math.min(Math.max(zoom, MIN_ZOOM), MAX_ZOOM);
}

/** Camera distance from the Sun right now, in AU. */
export function currentDistanceAu(): number {
  const rc = renderContext();
  if (!rc) { return cameraDistanceAu(zoomHome()); }
  return cameraDistanceAu(rc.viewCamera.zoom);
}

/** Camera state, for the `?debug=1` console handle. */
export function cameraInfo(): { latDeg: number; lngDeg: number; zoom: number; rotation: number } {
  const rc = renderContext();
  if (!rc) { return { latDeg: 0, lngDeg: 0, zoom: 0, rotation: 0 }; }
  const cam = rc.viewCamera;
  return { latDeg: cam.lat, lngDeg: cam.lng, zoom: cam.zoom, rotation: cam.rotation };
}

export function solarSystemModeActive(): boolean {
  const control = WWTControl.singleton as unknown as {
    // eslint-disable-next-line @typescript-eslint/naming-convention -- engine API name
    get_solarSystemMode?: () => boolean;
  } | null;
  return !!control?.get_solarSystemMode?.();
}

// ---------------------------------------------------------------------
// Camera
// ---------------------------------------------------------------------

/**
 * Pin the world origin to the Sun's CENTER.
 *
 * NEVER `setTrackedObject(0)` instead: `getPlanetTargetPoint` adds a
 * lat/lng-dependent SURFACE offset, so the origin slides by ~1 R_sun as the
 * guest orbits and the whole three.js overlay detaches from the sphere
 * (CLAUDE.md footgun 1). `target = custom` keeps our viewTarget verbatim.
 */
function pinToSunCenter(camera: MutableCamera): void {
  camera.target = SS_CUSTOM;
  camera.targetReferenceFrame = "";
  camera.viewTarget.x = 0;
  camera.viewTarget.y = 0;
  camera.viewTarget.z = 0;
}

/**
 * The framing a guest should land on: standing where Earth stands, so the Sun
 * shows the same hemisphere SDO photographs, with solar north up.
 *
 * THIS IS WHERE THE 90 DEG TILT CAME FROM. The old version read Earth's
 * heliocentric ecliptic longitude L, then solved the camera formula as if the
 * world frame were plain ecliptic J2000 — which forced cos(lng) = 0 and put
 * `lat` = L, i.e. it flew the camera up to |ecliptic latitude| = L, as much as
 * 90 deg out of the ecliptic plane, and framed the Sun from there. With +Y
 * correctly identified as the ecliptic pole the answer is the trivial one:
 * Earth is IN the ecliptic (heliocentric latitude under 0.0003 deg), so
 *
 *     lat = 0,   lng = L - 90
 *
 * and there is no branch and no clamp interaction. Written below as
 * `latLngFor(eclipticToWwtWorld(u))` rather than as those two closed forms, so
 * there is ONE inverse of the camera formula in this file instead of two that
 * can drift apart — and so it stays correct if Earth's latitude ever matters.
 *
 * Roll: lookUp sweeps the great circle perpendicular to u as `rotation` turns,
 * spanned by e1 and e2 from the header, so writing the wanted up vector U in
 * that basis gives rotation directly. U is the Sun's rotation axis with its
 * component along the view direction removed — i.e. true solar north projected
 * onto the screen, which is what "north up" means for a picture of the Sun (and
 * what SDO's own north-up convention means). That is `rollFor` + `northUpRoll`
 * below, which `orbitByPixels` also uses, so entry framing and free orbit
 * cannot disagree about which way is up.
 */
function earthFacingCamera(): { latDeg: number; lngDeg: number; rotationRad: number } {
  const jd = julianDateNow();
  // Earth as seen from the Sun is 180 deg from the Sun as seen from Earth.
  const lonRad = (wrap180(sunEclipticLongitudeDeg(jd) + 180) * Math.PI) / 180;

  // Earth's direction, ecliptic J2000 -> WWT world, then inverted through the
  // camera formula. eclipticToWwtWorld is what makes this Earth's direction
  // rather than a point 90 deg away from it.
  const u = norm3(eclipticToWwtWorld([Math.cos(lonRad), Math.sin(lonRad), 0]));
  const { latDeg, lngDeg } = latLngFor(u);

  // northUpRollBase, NOT northUpRoll: this is the framing homeCamera resets TO,
  // and homeCamera clears the guest's twist immediately afterwards. Adding
  // userRollRad here would bake the twist into the rotation a line before it
  // was zeroed, so "recenter" would land at whatever roll the guest had left.
  return { latDeg: clampLat(latDeg), lngDeg, rotationRad: northUpRollBase(u, latDeg, lngDeg) };
}

/** Fold an angle in degrees into (-180, 180]. */
function wrap180(deg: number): number {
  const x = ((deg % 360) + 360) % 360;
  return x > 180 ? x - 360 : x;
}

function clampLat(deg: number): number {
  return Math.min(Math.max(deg, -MAX_LAT_DEG), MAX_LAT_DEG);
}

// ---------------------------------------------------------------------
// Free orbit
// ---------------------------------------------------------------------

/**
 * Stop this far from the Sun's pole. Not a wall the guest can feel — at 88 deg
 * the remaining 2 deg is a couple of pixels of drag — but the elevation axis
 * below is cross(axis, u), which is undefined when u IS the axis.
 */
const MAX_SOLAR_LAT_DEG = 88;

/** Degrees of orbit per pixel of drag. The engine's own solar-system move()
 *  works out to ~0.378 deg/px, which spins the Sun ~147 deg on one phone
 *  swipe; this is that scaled for touch, matching the old SOLAR_MOVE_SCALE. */
const ORBIT_DEG_PER_PX = 0.113;

/**
 * Drag direction. "Grab the globe and it follows your finger": drag right and
 * the face you are looking at travels right, which means the CAMERA orbits the
 * other way.
 *
 * These are constants rather than inline signs because the sense cannot be
 * derived on paper. `rotateAbout` is a right-handed Rodrigues rotation applied
 * in WWT's world frame, which is LEFT-handed with respect to physical space
 * (worldFrame.ts) — so it turns the Sun the opposite way from what the algebra
 * reads like — and the elevation axis is cross(solar_axis, u), whose direction
 * flips with which side of the Sun the camera is on. Both were originally
 * settled by hand at the screen: azimuth +1, elevation -1.
 *
 * RE-CONFIRMED on 2026-08-24, because correcting `solarAxis()` to WWT world
 * coordinates moved the axis ~90 deg and the old settling did not carry over.
 * Not by feel this time: a Node harness replayed orbitByPixels and projected a
 * point painted ON the Sun through the engine's own lookAtLH/perspectiveFovLH,
 * at the entry framing. Drag right 150 px moves it +0.112 in NDC x (right);
 * drag down 110 px moves it -0.092 in NDC y (down). Both follow the finger, so
 * both signs stand. If either ever feels inverted, it is a one-character fix
 * here.
 */
const AZIMUTH_SIGN = 1;
const ELEVATION_SIGN = -1;

function rotateAbout(v: Vec3, axis: Vec3, angleRad: number): Vec3 {
  // Rodrigues. Cheaper and clearer here than building a quaternion for one use.
  const c = Math.cos(angleRad);
  const s = Math.sin(angleRad);
  const d = axis[0] * v[0] + axis[1] * v[1] + axis[2] * v[2];
  return [
    v[0] * c + (axis[1] * v[2] - axis[2] * v[1]) * s + axis[0] * d * (1 - c),
    v[1] * c + (axis[2] * v[0] - axis[0] * v[2]) * s + axis[1] * d * (1 - c),
    v[2] * c + (axis[0] * v[1] - axis[1] * v[0]) * s + axis[2] * d * (1 - c),
  ];
}

function norm3(v: Vec3): Vec3 {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

function cross3(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

/** Camera direction (unit, world) for WWT's lat/lng — the header's formula. */
function directionFor(latDeg: number, lngDeg: number): Vec3 {
  const lat = (latDeg * Math.PI) / 180;
  const lng = (lngDeg * Math.PI) / 180;
  return [-Math.cos(lat) * Math.sin(lng), Math.sin(lat), Math.cos(lat) * Math.cos(lng)];
}

/**
 * Inverse of directionFor. General, unlike the special case earthFacingCamera
 * solves: cos(lat) is never negative over [-90, 90], so the atan2 recovers lng
 * for any direction that is not exactly +/-Y.
 */
function latLngFor(u: Vec3): { latDeg: number; lngDeg: number } {
  return {
    latDeg: (Math.asin(Math.min(1, Math.max(-1, u[1]))) * 180) / Math.PI,
    lngDeg: (Math.atan2(-u[0], u[2]) * 180) / Math.PI,
  };
}

/**
 * The Sun's rotation axis in WWT WORLD coordinates, cached for a minute.
 *
 * The `eclipticToWwtWorld` is the whole point: `sunPoleEcliptic` is a physics
 * vector in our frame, and every consumer of this function (`orbitByPixels`,
 * `northUpRoll`, `clampCameraLat`) feeds it straight into `directionFor` /
 * `cross3` against WWT camera directions. Mixing the two frames here is what
 * made the free-orbit axis and the north-up roll point 90 deg away from the
 * Sun's actual pole.
 *
 * The axis moves by about 0.00001 degrees a minute (it is fixed in inertial
 * space; only the Earth-based frame it is expressed in drifts), so recomputing
 * it per call was pure waste — and it WAS per call: `orbitByPixels` runs once
 * per pointer event, which a high-report-rate touchscreen fires several times
 * per rendered frame, and `clampCameraLat` runs every frame for both cameras.
 */
let axisCache: Vec3 | null = null;
let axisCacheAtMs = 0;
const AXIS_CACHE_MS = 60_000;

function solarAxis(): Vec3 {
  const now = performance.now();
  if (!axisCache || now - axisCacheAtMs > AXIS_CACHE_MS) {
    axisCache = norm3(eclipticToWwtWorld(sunPoleEcliptic(julianDateNow())));
    axisCacheAtMs = now;
  }
  return axisCache;
}

/** The `rotation` that puts a world-space up vector on screen-up at lat/lng. */
function rollFor(latDeg: number, lngDeg: number, up: Vec3): number {
  const lat = (latDeg * Math.PI) / 180;
  const lng = (lngDeg * Math.PI) / 180;
  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const sinLng = Math.sin(lng);
  const cosLng = Math.cos(lng);
  const e1: Vec3 = [cosLng, 0, sinLng];
  const e2: Vec3 = [sinLat * sinLng, cosLat, -sinLat * cosLng];
  const onE1 = up[0] * e1[0] + up[1] * e1[1] + up[2] * e1[2];
  const onE2 = up[0] * e2[0] + up[1] * e2[1] + up[2] * e2[2];
  return -Math.atan2(onE1, onE2);
}

/**
 * The `rotation` that puts projected solar north on screen-up from a given
 * viewing direction, with NO guest twist added.
 *
 * Split out from `northUpRoll` for `earthFacingCamera`, which computes the
 * framing that "recenter" resets to and must not carry a roll that is about to
 * be zeroed.
 */
function northUpRollBase(u: Vec3, latDeg: number, lngDeg: number): number {
  const axis = solarAxis();
  // Solar north with the along-view part removed: projected north, i.e. what
  // "up" means for a picture of the Sun.
  const along = axis[0] * u[0] + axis[1] * u[1] + axis[2] * u[2];
  const up = norm3([
    axis[0] - along * u[0],
    axis[1] - along * u[1],
    axis[2] - along * u[2],
  ]);
  return rollFor(latDeg, lngDeg, up);
}

/**
 * The `rotation` that puts projected solar north on screen-up from a given
 * viewing direction, PLUS whatever the guest has twisted to.
 *
 * Extracted so `orbitByPixels` and `addUserRoll` cannot disagree about the
 * framing: a twist that computed "up" differently from a pan would make the
 * horizon jump the moment you did one after the other.
 */
function northUpRoll(u: Vec3, latDeg: number, lngDeg: number): number {
  return northUpRollBase(u, latDeg, lngDeg) + userRollRad;
}

/**
 * The guest's own roll, in radians, on top of the solar-north-up framing.
 *
 * Two-finger twist writes this. It has to be SEPARATE state rather than just
 * `targetCamera.rotation`, because `orbitByPixels` recomputes `rotation` from
 * scratch on every drag step to keep solar north up — so a roll written
 * directly into the camera survives exactly until the guest's next pan. The
 * framing and the guest's twist are two different things and both have to be
 * remembered.
 */
let userRollRad = 0;

/** Add to the guest's roll (two-finger twist). */
export function addUserRoll(deltaRad: number): void {
  if (!Number.isFinite(deltaRad)) { return; }
  userRollRad += deltaRad;
  // Keep it bounded so a guest who spins the same way for a minute does not
  // accumulate a number that loses precision.
  const twoPi = Math.PI * 2;
  userRollRad = ((userRollRad % twoPi) + twoPi) % twoPi;

  // AND APPLY IT. This used to only accumulate, on the assumption that
  // `orbitByPixels` would pick the new value up -- which it does, and that was
  // the bug: during a pinch the pan accumulator is 0, so orbitByPixels never
  // runs and the twist sat invisible until the guest's next drag, which then
  // snapped the whole accumulated angle in at once. Measured in a browser: a
  // 40 deg twist moved nothing on screen, then a 4 px pan jumped -34.2 deg --
  // exactly the twist minus the 5.7 deg deadzone.
  //
  // Rotation only, deliberately: lat/lng/zoom belong to the pan and pinch paths
  // and must not be rewritten from here.
  const rc = renderContext();
  if (!rc) { return; }
  for (const cam of [rc.targetCamera, rc.viewCamera]) {
    const u = norm3(directionFor(cam.lat, cam.lng));
    cam.rotation = northUpRoll(u, cam.lat, cam.lng);
    cam.angle = 0;
  }
}

/** The guest's roll, for callers that need to reproduce the framing. */
export function userRoll(): number {
  return userRollRad;
}

/** Back to solar-north-up. Recenter does this; nothing else should. */
export function resetUserRoll(): void {
  userRollRad = 0;
}

/**
 * Multiply the zoom, as a pinch does.
 *
 * Writes `targetCamera` only, so the engine's own easing (footgun 14) turns a
 * pinch into smooth motion for free. `viewCamera` is deliberately NOT written:
 * that is what makes a pinch feel like it has weight instead of snapping.
 */
export function zoomBy(factor: number): void {
  const rc = renderContext();
  if (!rc || !Number.isFinite(factor) || factor <= 0) { return; }
  rc.targetCamera.zoom = clampZoom(rc.targetCamera.zoom * factor);
}

/** Absolute zoom, for a pinch that tracks a baseline rather than accumulating. */
export function zoomTo(zoom: number): void {
  const rc = renderContext();
  if (!rc || !Number.isFinite(zoom)) { return; }
  rc.targetCamera.zoom = clampZoom(zoom);
}

/** Current target zoom, so a gesture can take a baseline at its start. */
export function currentZoom(): number {
  const rc = renderContext();
  return rc ? rc.targetCamera.zoom : MIN_ZOOM;
}

/**
 * Orbit the camera by a drag, in pixels.
 *
 * This REPLACES the engine's own solar-system move(), and the reason is the
 * header's formula: WWT's lat/lng sphere has its poles at +/-Y, i.e. at the
 * ECLIPTIC pole. Near there `lng` stops doing anything, so dragging sideways
 * goes dead — and the Sun's own axis is only 7.25 deg away, so a guest looking
 * over the Sun's pole is right in that dead zone.
 *
 * So we orbit in the frame a guest actually expects — the SUN's. Horizontal
 * drag turns about the solar rotation axis (a full circle, never degenerate);
 * vertical drag tilts toward the poles and stops just short of them, exactly
 * as spinning a globe does. The singular points are then the Sun's own poles,
 * which is where a person expects a globe's controls to converge, and the
 * result is re-expressed as lat/lng only at the end.
 *
 * Roll is recomputed every step so solar north stays up, which is also what
 * keeps the horizon from tumbling as the guest wanders.
 */
export function orbitByPixels(dxPx: number, dyPx: number): void {
  const rc = renderContext();
  if (!rc) { return; }

  const cam = rc.targetCamera.copy();
  const axis = solarAxis();
  let u = directionFor(cam.lat, cam.lng);

  // Azimuth about the solar axis — see AZIMUTH_SIGN.
  u = rotateAbout(u, axis, (AZIMUTH_SIGN * dxPx * ORBIT_DEG_PER_PX * Math.PI) / 180);

  // Elevation about the horizontal axis perpendicular to both. Clamp on the
  // ANGLE to the SOLAR pole, not on WWT's lat, which measures from elsewhere.
  const right = cross3(axis, u);
  const rightLen = Math.hypot(right[0], right[1], right[2]);
  if (rightLen > 1e-6) {
    const next = rotateAbout(
      u, norm3(right), (ELEVATION_SIGN * dyPx * ORBIT_DEG_PER_PX * Math.PI) / 180);
    const cosPolar = next[0] * axis[0] + next[1] * axis[1] + next[2] * axis[2];
    const solarLat = 90 - (Math.acos(Math.min(1, Math.max(-1, cosPolar))) * 180) / Math.PI;
    if (Math.abs(solarLat) <= MAX_SOLAR_LAT_DEG) { u = next; }
  }

  u = norm3(u);
  const { latDeg, lngDeg } = latLngFor(u);

  cam.lat = latDeg;
  cam.lng = lngDeg;
  // Solar north up, PLUS whatever the guest has twisted to. Adding the two is
  // what lets a twist survive the next pan instead of being recomputed away.
  cam.rotation = northUpRoll(u, latDeg, lngDeg);
  cam.angle = 0;
  pinToSunCenter(cam);
  // Both lat/lng cameras: the engine eases viewCamera toward targetCamera, and
  // a drag should track the finger rather than lag it.
  //
  // But NOT zoom. Copying targetCamera wholesale used to drag viewCamera.zoom
  // along with it, so a pinch followed immediately by a pan snapped to the
  // pinch's target instead of easing into it — a visible jump attributable to
  // the pinch, which is one of the things that made zoom feel unreliable.
  const keepViewZoom = rc.viewCamera.zoom;
  rc.targetCamera = cam;
  const view = cam.copy();
  view.zoom = keepViewZoom;
  pinToSunCenter(view);
  rc.viewCamera = view;
}

/**
 * Put the camera exactly here, both cameras, no easing. `?debug=1` only.
 *
 * Exists because the ONE check that would have caught the 90 deg world-frame
 * bug four sessions earlier — comparing our geometry against WWT's own
 * rendered planet orbits — needs a viewpoint 30x further out than the guest
 * ever goes, and getting there by wheel events means waiting on the engine's
 * per-frame easing, which does not run at all in a background tab. Writing
 * both cameras makes the next single rendered frame correct, so a screenshot
 * is enough.
 *
 * Not reachable without `?debug=1` (SolarView3D gates the handle), and it goes
 * through `pinToSunCenter` like every other camera writer here, so it cannot
 * reintroduce footgun 1.
 */
export function debugSetCamera(
  opts: { latDeg?: number; lngDeg?: number; zoom?: number; distanceAu?: number },
): void {
  const rc = renderContext();
  if (!rc) { return; }
  const cam = rc.targetCamera.copy();
  if (Number.isFinite(opts.latDeg)) { cam.lat = clampLat(opts.latDeg as number); }
  if (Number.isFinite(opts.lngDeg)) { cam.lng = opts.lngDeg as number; }
  if (Number.isFinite(opts.distanceAu)) {
    // Inverse of cameraDistanceAu (footgun 14).
    cam.zoom = clampZoom((((opts.distanceAu as number) - 1e-6) * 9) / 4);
  }
  if (Number.isFinite(opts.zoom)) { cam.zoom = clampZoom(opts.zoom as number); }
  const u = norm3(directionFor(cam.lat, cam.lng));
  cam.rotation = northUpRoll(u, cam.lat, cam.lng);
  cam.angle = 0;
  pinToSunCenter(cam);
  rc.targetCamera = cam;
  const view = cam.copy();
  pinToSunCenter(view);
  rc.viewCamera = view;
}

/**
 * Frame the Sun.
 *
 * `instant` (initial entry) writes BOTH cameras so there is no slew from
 * wherever WWT started. Later resets write only `targetCamera`: the engine eases
 * `viewCamera` toward it every frame, which is a free smooth animation and the
 * reason this app needs none of exo's slew machinery (footgun 14).
 */
export function homeCamera(instant = false): void {
  const rc = renderContext();
  if (!rc) { return; }

  const framing = earthFacingCamera();
  const target = rc.targetCamera.copy();
  pinToSunCenter(target);
  target.lat = framing.latDeg;
  target.lng = framing.lngDeg;
  // Recenter is the one place that clears the guest's twist: it means "put it
  // back the way it started", and leaving a roll behind would make the button
  // look broken.
  userRollRad = 0;
  target.rotation = framing.rotationRad;
  target.angle = 0;
  target.zoom = clampZoom(zoomHome());
  rc.targetCamera = target;

  // Harmless when already set, and it guarantees the origin stays pinned even
  // if something else in the engine reset the target between frames.
  pinToSunCenter(rc.viewCamera);

  if (instant) {
    const view = target.copy();
    pinToSunCenter(view);
    rc.viewCamera = view;
  }
}

/**
 * Keep the camera off the Sun's rotation axis.
 *
 * This used to clamp WWT's `lat`, which is ECLIPTIC latitude — close to what
 * we want (the two poles are 7.25 deg apart) but not it, so the clamp stopped
 * the guest a little short on one side of the Sun and a little late on the
 * other, at a wall that moved with the seasons. orbitByPixels now bounds the
 * angle to the SOLAR axis instead, where a globe's controls are expected to
 * converge.
 *
 * What survives is a per-frame backstop: WWT accumulates camera state in
 * several places (momentum, pinch, its own easing), and any of them can land
 * the camera exactly on the axis, where the elevation cross-product is
 * undefined. Nudging off the pole here catches all of them in one place —
 * which was the original reason this ran every frame.
 */
export function clampCameraLat(maxSolarLatDeg = MAX_SOLAR_LAT_DEG): void {
  const rc = renderContext();
  if (!rc) { return; }
  const axis = solarAxis();

  for (const cam of [rc.targetCamera, rc.viewCamera]) {
    const u = directionFor(cam.lat, cam.lng);
    const cosPolar = u[0] * axis[0] + u[1] * axis[1] + u[2] * axis[2];
    const solarLat = 90 - (Math.acos(Math.min(1, Math.max(-1, cosPolar))) * 180) / Math.PI;
    if (Math.abs(solarLat) <= maxSolarLatDeg) { continue; }

    // Tilt back toward the equator along the shortest path.
    const right = cross3(axis, u);
    if (Math.hypot(right[0], right[1], right[2]) < 1e-6) { continue; }
    const excess = (Math.abs(solarLat) - maxSolarLatDeg) * Math.sign(solarLat);
    const fixed = rotateAbout(u, norm3(right), (excess * Math.PI) / 180);
    const ll = latLngFor(norm3(fixed));
    cam.lat = ll.latDeg;
    cam.lng = ll.lngDeg;
  }
}

let lastPad = 0;

/**
 * Re-fit after a resize or a device rotation. Rather than snapping back to the
 * home zoom (which would throw away a guest's pinch), scale the current zoom by
 * the change in aspect pad — the same feature stays framed.
 */
export function refitFraming(): void {
  const pad = aspectPad();
  const rc = renderContext();
  if (rc && lastPad > 0 && Math.abs(pad - lastPad) > 1e-6) {
    const ratio = pad / lastPad;
    rc.targetCamera.zoom = clampZoom(rc.targetCamera.zoom * ratio);
    rc.viewCamera.zoom = clampZoom(rc.viewCamera.zoom * ratio);
  }
  lastPad = pad;
}

// ---------------------------------------------------------------------
// Entry
// ---------------------------------------------------------------------

/**
 * Enter solar-system mode and frame the Sun. Call AFTER `waitForReady()`; the
 * order below matters — the imageset names switch the renderer into 3D, and the
 * settings/zoom clamps must be in place before the first frame is drawn or the
 * guest sees a flash of the galactic sky.
 */
export function initSunStage(host: SunStageHost): void {
  host.setClockSync(false);
  host.setTime(new Date());

  // This pair IS the 3D mode switch (there is no setMode API).
  host.setBackgroundImageByName("Solar System");
  host.setForegroundImageByName("Solar System");

  STAGE_SETTINGS.forEach((setting) => host.applySetting(setting));

  const control = WWTControl.singleton;
  if (control) {
    control.setSolarSystemMinZoom(MIN_ZOOM);
    control.setSolarSystemMaxZoom(MAX_ZOOM);
  }

  lastPad = aspectPad();
  homeCamera(true);
}
