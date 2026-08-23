// =====================================================================
// WWT solar-system stage — entering 3D mode and framing the Sun
// =====================================================================
// Everything in here is load-bearing and was verified against the engine
// source; the comments say why, because the failure modes are all "looks
// almost right" (see CLAUDE.md footguns 1, 2, 11, 14).
//
// Frame: with `target = SolarSystemObjects.custom` and `viewTarget = (0,0,0)`,
// WWT's solar-system world frame is heliocentric ecliptic J2000 in AU with the
// Sun at the ORIGIN and +Z at the ecliptic pole. That is exactly the frame our
// PFSS quaternions and Horizons positions are expressed in, so the three.js
// overlay needs no transform at all.

import { EngineSetting, WWTControl } from "@wwtelescope/engine";

import {
  R_SUN_AU,
  Vec3,
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
 * in WORLD coordinates, which for this app are heliocentric ecliptic J2000 with
 * +Z at the ecliptic pole (see solarFrames.heeqToWorld).
 *
 * The consequence worth writing down, because the old `HOME_LAT_DEG = 7` was
 * built on the opposite assumption: lat is NOT height above the ecliptic. It is
 * the angle toward +Y, which LIES IN the ecliptic plane. So lat = lng = 0 puts
 * the camera on +Z — straight over the ecliptic north pole, looking down the
 * Sun's rotation axis, with the Earth-facing hemisphere edge-on. That is why
 * the SDO texture never appeared face-on at entry.
 */

/**
 * Where lat runs out. The poles of this lat/lng sphere are +/-Y, i.e. ecliptic
 * longitude 90 and 270 — ordinary viewpoints, but lng stops having any effect
 * there, so dragging sideways goes dead. Stop just short: 89.5 keeps the guard
 * while leaving the Earth-facing framing reachable all year (it needs |lat| up
 * to 90, and is off by at most 0.5 deg on the few days Earth sits within half a
 * degree of ecliptic longitude 90 or 270).
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

/** Zoom that frames HOME_RADII solar radii on the short screen axis. */
export function zoomHome(): number {
  return (9 / 4) * HOME_RADII * R_SUN_AU * FIT_FACTOR * aspectPad();
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
 * Inverting the camera formula in the header for a target direction u:
 * Earth's heliocentric ecliptic latitude is under 0.0003 deg, so u lies in the
 * ecliptic plane, u = (cos L, sin L, 0) for L = Earth's heliocentric ecliptic
 * longitude. Then `cos(lat) cos(lng) = u_z = 0` forces cos(lng) = 0, and the
 * two branches lng = -90 and lng = +90 give lat = L and lat = 180 - L. Picking
 * whichever branch lands |lat| <= 90 keeps us inside the clamp all year.
 *
 * Roll: lookUp sweeps the great circle perpendicular to u as `rotation` turns,
 * spanned by e1 and e2 from the header, so writing the wanted up vector U in
 * that basis gives rotation directly. U is the Sun's rotation axis with its
 * component along the view direction removed — i.e. true solar north projected
 * onto the screen, which is what "north up" means for a picture of the Sun (and
 * what SDO's own north-up convention means).
 */
function earthFacingCamera(): { latDeg: number; lngDeg: number; rotationRad: number } {
  const jd = julianDateNow();
  // Earth as seen from the Sun is 180 deg from the Sun as seen from Earth.
  const lonDeg = wrap180(sunEclipticLongitudeDeg(jd) + 180);

  const useNear = Math.abs(lonDeg) <= 90;
  const latDeg = clampLat(useNear ? lonDeg : wrap180(180 - lonDeg));
  const lngDeg = useNear ? -90 : 90;

  const lat = (latDeg * Math.PI) / 180;
  const lng = (lngDeg * Math.PI) / 180;
  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const sinLng = Math.sin(lng);
  const cosLng = Math.cos(lng);

  // The camera's own axes in world coordinates (header).
  const u: [number, number, number] = [-cosLat * sinLng, sinLat, cosLat * cosLng];
  const e1: [number, number, number] = [cosLng, 0, sinLng];
  const e2: [number, number, number] = [sinLat * sinLng, cosLat, -sinLat * cosLng];

  // Solar north, with the along-view component removed.
  const pole = sunPoleEcliptic(jd);
  const along = pole[0] * u[0] + pole[1] * u[1] + pole[2] * u[2];
  const up: [number, number, number] = [
    pole[0] - along * u[0],
    pole[1] - along * u[1],
    pole[2] - along * u[2],
  ];
  const upLen = Math.hypot(up[0], up[1], up[2]) || 1;

  const onE1 = (up[0] * e1[0] + up[1] * e1[1] + up[2] * e1[2]) / upLen;
  const onE2 = (up[0] * e2[0] + up[1] * e2[1] + up[2] * e2[2]) / upLen;
  // lookUp = sin(-rotation) e1 + cos(-rotation) e2, so -rotation = atan2(onE1, onE2).
  return { latDeg, lngDeg, rotationRad: -Math.atan2(onE1, onE2) };
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
 * derived from the engine's own move(): that rotates about WWT's +/-Y pole
 * (`lng -= x`, `lat += y`) and this rotates about the SUN's axis, so the two
 * conventions do not carry over — and they do not even agree with each other.
 * Both were settled by hand at the screen: azimuth needed +1, elevation -1,
 * because the elevation axis is cross(solar_axis, u), whose direction flips
 * with which side of the Sun the camera is on. If either ever feels inverted,
 * it is a one-character fix here.
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
 * Orbit the camera by a drag, in pixels.
 *
 * This REPLACES the engine's own solar-system move(), and the reason is the
 * header's formula: WWT's lat/lng sphere has its poles at +/-Y, which in this
 * app's world frame is an arbitrary pair of points in the ecliptic plane
 * (ecliptic longitude 90 and 270). Near them `lng` stops doing anything, so
 * dragging sideways went dead, and clampCameraLat's guard against that
 * degeneracy read as an invisible wall in a direction with no relationship to
 * anything the guest can see.
 *
 * So we orbit in the frame a guest actually expects — the SUN's. Horizontal
 * drag turns about the solar rotation axis (a full circle, never degenerate);
 * vertical drag tilts toward the poles and stops just short of them, exactly
 * as spinning a globe does. The only singular points are now the Sun's own
 * poles, which is where a person expects a globe's controls to converge.
 *
 * Roll is recomputed every step so solar north stays up, which is also what
 * keeps the horizon from tumbling as the guest wanders.
 */
export function orbitByPixels(dxPx: number, dyPx: number): void {
  const rc = renderContext();
  if (!rc) { return; }

  const cam = rc.targetCamera.copy();
  const axis = norm3(sunPoleEcliptic(julianDateNow()) as Vec3);
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

  // Solar north with the along-view part removed: projected north, i.e. what
  // "up" means for a picture of the Sun.
  const along = axis[0] * u[0] + axis[1] * u[1] + axis[2] * u[2];
  const up = norm3([
    axis[0] - along * u[0],
    axis[1] - along * u[1],
    axis[2] - along * u[2],
  ]);

  cam.lat = latDeg;
  cam.lng = lngDeg;
  cam.rotation = rollFor(latDeg, lngDeg, up);
  cam.angle = 0;
  pinToSunCenter(cam);
  // Both cameras: the engine eases viewCamera toward targetCamera, and a drag
  // should track the finger rather than lag it.
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
 * This used to clamp WWT's `lat`, which sounds right and is not: that latitude
 * is measured from +/-Y, an arbitrary pair of points in the ecliptic plane, so
 * the clamp stopped the guest at an invisible wall unrelated to anything on
 * screen — and it is the reason free exploration felt stuck. orbitByPixels now
 * bounds the angle to the SOLAR axis instead, where a globe's controls are
 * expected to converge.
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
  const axis = norm3(sunPoleEcliptic(julianDateNow()) as Vec3);

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
