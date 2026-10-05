// deCollideLabels' invariants, run against the REAL module. These were
// scripts/check_label_layout.mjs, which tested a hand-transliterated copy of
// the algorithm because the module is TypeScript; with vitest it imports the
// shipped code, so the copy (and the risk of it drifting) is gone.
import { describe, expect, it } from "vitest";

import { LabelBox, deCollideLabels } from "../../src/three/labelLayout";

// The values SolarView3D actually passes.
const OPTS = { strideY: 46, spreadX: 75 };
const EPS = 1e-9;

type Box = LabelBox & { id?: number };

describe("deCollideLabels", () => {
  it("separates the real measured case (three chips ~12 px apart) to the stride, centred on its mean", () => {
    const boxes: Box[] = [
      { x: 180, y: 300, visible: true },
      { x: 186, y: 312, visible: true },
      { x: 190, y: 324, visible: true },
    ];
    deCollideLabels(boxes, OPTS);
    const ys = boxes.map((b) => b.y).sort((p, q) => p - q);
    expect(ys[1] - ys[0]).toBeGreaterThanOrEqual(OPTS.strideY - EPS);
    expect(ys[2] - ys[1]).toBeGreaterThanOrEqual(OPTS.strideY - EPS);
    expect((ys[0] + ys[1] + ys[2]) / 3).toBeCloseTo(312, 9);   // no downward drift
  });

  it("leaves chips that are far apart horizontally alone", () => {
    const boxes: Box[] = [
      { x: 40, y: 200, visible: true },
      { x: 400, y: 200, visible: true },
    ];
    deCollideLabels(boxes, OPTS);
    expect(boxes.map((b) => b.y)).toEqual([200, 200]);
  });

  it("neither moves nor counts invisible chips", () => {
    const boxes: Box[] = [
      { x: 100, y: 200, visible: true },
      { x: 100, y: 205, visible: false },
      { x: 100, y: 210, visible: true },
    ];
    deCollideLabels(boxes, OPTS);
    expect(boxes[1].y).toBe(205);
    expect(Math.abs(boxes[2].y - boxes[0].y)).toBeGreaterThanOrEqual(OPTS.strideY - EPS);
  });

  it("holds its invariants over 20,000 random clustered cases", () => {
    // Deterministic PRNG, so a failure is reproducible.
    let seed = 20260823;
    const rnd = (): number => {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed / 0x7fffffff;
    };
    let identityChanges = 0;
    let xMutations = 0;
    let strideViolations = 0;
    for (let t = 0; t < 20000; t++) {
      const count = 1 + Math.floor(rnd() * 12);
      const boxes: Box[] = [];
      for (let i = 0; i < count; i++) {
        boxes.push({ id: i, x: Math.round(rnd() * 400), y: Math.round(rnd() * 300), visible: rnd() > 0.15 });
      }
      const before = boxes.map((b) => ({ id: b.id, x: b.x }));
      deCollideLabels(boxes, OPTS);
      // The caller's array order IS the chip identity; only y may move.
      boxes.forEach((b, i) => {
        if (b.id !== before[i].id) { identityChanges++; }
        if (b.x !== before[i].x) { xMutations++; }
      });
      const vis = boxes.filter((b) => b.visible).sort((p, q) => p.y - q.y);
      for (let i = 1; i < vis.length; i++) {
        const overlapX = Math.abs(vis[i].x - vis[i - 1].x) < OPTS.spreadX;
        if (overlapX && vis[i].y - vis[i - 1].y < OPTS.strideY - 1e-6) { strideViolations++; }
      }
    }
    expect({ identityChanges, xMutations, strideViolations })
      .toEqual({ identityChanges: 0, xMutations: 0, strideViolations: 0 });
  });
});
