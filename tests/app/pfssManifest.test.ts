// The field-line manifest parser, on a fixture trimmed from a real published
// manifest (3 frames; the newest re-marked as a REUSED slot, the shape a GONG
// mirror outage produces -- T40's subject).
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { normalizeManifest } from "../../src/data/pfss";

const raw = JSON.parse(readFileSync(join(__dirname, "fixtures", "pfss-manifest-3frames.json"), "utf8"));

describe("normalizeManifest", () => {
  const m = normalizeManifest(raw);

  it("keeps every frame, oldest first, with its slot target time", () => {
    expect(m.frames.map((f) => f.index)).toEqual([0, 1, 2]);
    expect(m.frames.every((f) => typeof f.targetIso === "string" && f.targetIso.endsWith("Z"))).toBe(true);
  });

  it("parses reused slots, which share a magnetogram time but not a target time", () => {
    const [, prev, held] = m.frames;
    expect(held.reused).toBe(true);
    expect(prev.reused).toBe(false);
    expect(held.magUnix).toBe(prev.magUnix);
    expect(held.targetIso).not.toBe(prev.targetIso);
  });

  it("carries the window length the pipeline published", () => {
    expect(m.windowHours).toBe(72);
  });
});
