// The guest-facing card copy (src/data/cards.ts, plan 4.1 seam 1). These pin
// the behaviour that moved out of SolarView3D.vue so later copy changes
// (T12, plan 4.4) are deliberate rather than accidental.
import { describe, expect, it } from "vitest";

import {
  EVENT_DISCLAIMER,
  EVENT_PREFIX,
  eventCard,
  flareMarks,
  flareStamp,
  formatDistance,
  regionCard,
} from "../../src/data/cards";
import type { SolarEvent } from "../../src/data/events";
import type { SolarRegion } from "../../src/data/regions";

const REGION: SolarRegion = {
  number: 4545, latDeg: 20, carrLonDeg: 222, areaUh: 20, magType: "Beta",
  isComplex: false, nSpots: 5, seedCount: 45,
};

const FLARE: SolarEvent = {
  id: "2026-10-04T10:00:00-FLR-001", kind: "flare", unix: Date.UTC(2026, 9, 4, 10, 0) / 1000,
  arNumber: 4545, arIndex: 0, donkiLink: "", linked: [], cls: "M1.2", sourceLocation: "N20E33",
};

describe("cards", () => {
  it("stamps flares in the guest's local time with the zone (TZ pinned to UTC here)", () => {
    expect(flareStamp(Date.UTC(2026, 7, 22, 20, 9) / 1000)).toBe("Aug 22, 8:09 PM UTC");
  });

  it("gives event cards local time first, then UTC as the sources publish it", () => {
    expect(eventCard(FLARE).detail).toBe("Oct 4, 10:00 AM UTC · 10:00 UTC");
  });

  it("formats a distance in solar radii and AU", () => {
    expect(formatDistance(215)).toBe("215 R☉ · 1.00 AU");
  });

  it("describes a region without the complexity warning unless it is complex", () => {
    const card = regionCard(REGION);
    expect(card.name).toBe("Active Region 4545");
    expect(card.detail).toContain("5 sunspots");
    expect(card.blurb).toBe("45 of the field lines in this view are rooted here.");
    expect(card.warn).toBe("");
    expect(regionCard({ ...REGION, isComplex: true }).warn).toContain("Watch this one");
    expect(regionCard({ ...REGION, nSpots: 1, seedCount: 0 }).detail).toContain("1 sunspot");
  });

  it("puts the DONKI disclaimer on every event card", () => {
    const card = eventCard(FLARE);
    expect(card.warn).toBe(EVENT_DISCLAIMER);
    expect(card.compare).toBe("From sunspot region 4545 (N20E33).");
  });

  it("lets a DONKI flare claim the NOAA flare at the same minute", () => {
    const history = [
      { peakUnix: FLARE.unix, cls: "M1.2" },
      { peakUnix: FLARE.unix + 7200, cls: "C3.0" },
    ] as unknown as Parameters<typeof flareMarks>[1];
    const marks = flareMarks([FLARE], history, 12, 10);
    expect(marks).toHaveLength(2);
    expect(marks[0].id).toBe(`${EVENT_PREFIX}${FLARE.id}`);   // DONKI's, with a card
    expect(marks[1].label.startsWith("C3.0 flare")).toBe(true);
  });
});
