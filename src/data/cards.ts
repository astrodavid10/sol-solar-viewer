// =====================================================================
// The guest-facing card and timeline-mark copy, as pure functions
// =====================================================================
// Moved out of SolarView3D.vue (plan 4.1, seam 1). Everything here is
// "given this body / region / event, what does the card say", so it carries
// no GL, no engine, and no component state, and the copy a guest reads is
// unit-testable (tests/app/cards.test.ts) instead of living inside a
// 3,000-line component.

import {
  SolarEvent,
  describeCmeAim,
  describeCmeSpeed,
  describeFlareClass,
  earthArrivalUnix,
  eventTitle,
  thinEvents,
} from "./events";
import { SOLAR_SYSTEM_BODIES, describeOrbitPeriod, planetBlurb } from "./planets";
import { SolarRegion, describeRegionArea, describeRegionMagnetism } from "./regions";
import { AU_KM, R_SUN_KM } from "./solarFrames";
import { bodyBlurb, describeDistance } from "./spacecraft";
import { thinFlareEvents } from "./useSolarStats";

export interface CardInfo {
  name: string;
  detail: string;
  compare: string;
  blurb: string;
  /** Optional final line, set apart in warning color. */
  warn?: string;
}

/**
 * Every event card carries this line. DONKI's own terms call it "prototyping
 * quality... research context", and that has to reach the guest.
 */
export const EVENT_DISCLAIMER = "Research data from NASA CCMC — not an official forecast.";

/** Timeline-mark ids for DONKI events are this prefix + the DONKI id. */
export const EVENT_PREFIX = "evt:";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Aug 22, 20:09 UTC" — flares are quoted in UTC everywhere in this app. */
export function flareStamp(unix: number): string {
  const d = new Date(unix * 1000);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${hh}:${mm} UTC`;
}

/** "45 R☉ · 0.21 AU" */
export function formatDistance(rSun: number): string {
  const au = (rSun * R_SUN_KM) / AU_KM;
  return `${Math.round(rSun)} R☉ · ${au.toFixed(2)} AU`;
}

/** A spacecraft or Earth, at `rSun` solar radii from the Sun. */
export function bodyCard(body: { id: string; name: string }, rSun: number): CardInfo {
  return {
    name: body.name,
    detail: formatDistance(rSun),
    compare: describeDistance(rSun),
    blurb: bodyBlurb(body.id),
  };
}

/** A planet chip, by its SOLAR_SYSTEM_BODIES name. */
export function planetCard(name: string, rSun: number): CardInfo | null {
  const body = SOLAR_SYSTEM_BODIES.find((b) => b.name === name);
  if (!body) { return null; }
  return {
    name: body.name,
    detail: formatDistance(rSun),
    compare: describeOrbitPeriod(body),
    blurb: planetBlurb(body.name),
  };
}

export function eventCard(event: SolarEvent): CardInfo {
  const when = flareStamp(event.unix);
  const region = event.arNumber ? `sunspot region ${event.arNumber}` : "";

  if (event.kind === "flare") {
    const where = region
      ? `From ${region}${event.sourceLocation ? ` (${event.sourceLocation})` : ""}.`
      : "";
    const linked = event.linked.length
      ? " It also threw off a cloud of gas — the blue circle on the timeline."
      : "";
    return {
      name: eventTitle(event),
      detail: when,
      compare: where,
      blurb: `${describeFlareClass(event.cls ?? "")}${linked}`.trim(),
      warn: EVENT_DISCLAIMER,
    };
  }

  const arrival = earthArrivalUnix(event);
  const parts = [describeCmeAim(event)];
  if (arrival) { parts.push(`Expected at Earth ${flareStamp(arrival)}.`); }
  if (region) { parts.push(`It came from ${region}.`); }
  return {
    name: eventTitle(event),
    detail: describeCmeSpeed(event.speedKms ?? 0),
    compare: when,
    blurb: parts.join(" "),
    warn: EVENT_DISCLAIMER,
  };
}

export function regionCard(region: SolarRegion): CardInfo {
  const spots = region.nSpots === 1 ? "1 sunspot" : `${region.nSpots} sunspots`;
  const seeds = region.seedCount === 1
    ? "One of the field lines in this view is rooted here."
    : `${region.seedCount} of the field lines in this view are rooted here.`;
  return {
    name: `Active Region ${region.number}`,
    detail: `${describeRegionArea(region.areaUh)} · ${spots}`,
    compare: `This is ${describeRegionMagnetism(region.magType)}.`,
    blurb: region.seedCount > 0 ? seeds : "",
    warn: region.isComplex
      ? "⚠ Watch this one — regions like this produce most big flares."
      : "",
  };
}

export interface FlareMark {
  unix: number;
  label: string;
  cls: string;
  kind?: string;
  id?: string;
}

type FlareHistoryEvents = Parameters<typeof thinFlareEvents>[0];

/**
 * Flare and CME diamonds for the scrubber track.
 *
 * DONKI wins where both feeds have the same flare: it is the richer record
 * (it knows WHERE the flare was and what CME went with it), and a mark that
 * opens a card beats one that only scrubs. NOAA's history is the fallback
 * because it is near-real-time (median DONKI lag 1.9 h for flares, 7.5 h for
 * CMEs), so it covers the newest events DONKI has not published yet.
 */
export function flareMarks(
  donki: SolarEvent[],
  history: FlareHistoryEvents | undefined,
  maxEventMarks: number,
  maxFlareMarks: number,
): FlareMark[] {
  const claimed = new Set<number>();
  for (const event of donki) {
    if (event.kind === "flare") { claimed.add(Math.round(event.unix / 60)); }
  }

  const marks: FlareMark[] = [];
  for (const event of thinEvents(donki, maxEventMarks)) {
    marks.push({
      unix: event.unix,
      label: `${eventTitle(event)} · ${flareStamp(event.unix)}`,
      cls: event.cls ?? "",
      kind: event.kind,
      id: `${EVENT_PREFIX}${event.id}`,
    });
  }

  if (history && history.length) {
    for (const event of thinFlareEvents(history, maxFlareMarks)) {
      if (claimed.has(Math.round(event.peakUnix / 60))) { continue; }
      marks.push({
        unix: event.peakUnix,
        label: `${event.cls ? `${event.cls} flare` : "Flare"} · ${flareStamp(event.peakUnix)}`,
        cls: event.cls,
      });
    }
  }
  return marks.sort((a, b) => a.unix - b.unix);
}
