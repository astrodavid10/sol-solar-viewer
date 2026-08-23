// =====================================================================
// Label de-collision — keep projected chips off each other
// =====================================================================
// Projecting a world position to the screen is exact, and that is the problem:
// two active regions 12° apart on the Sun land 12 px apart on a phone, and the
// chips naming them are 75 px wide and 44 px tall. Measured on the live site
// (2026-08-23, three viewports from 360x640 to 820x700), all three surface
// chips — AR 4513, AR 4515 and the sub-Earth ⊕ — overlapped each other at
// EVERY size. Not a near miss: mutually unreadable.
//
// This module does the one thing that fixes it without moving the markers: it
// nudges the CHIPS apart vertically while the markers stay on their true
// positions. Two rules, in order:
//
//   1. Chips that do not overlap horizontally are independent. Two labels on
//      opposite limbs share a y and must not be pushed apart for it.
//   2. Within a horizontally-overlapping run, stack at a fixed stride and then
//      re-center the run on its own original mean, so the group spreads about
//      where it was instead of drifting downward.
//
// No three.js and no WWT imports (CLAUDE.md footgun 12) — this is pure screen
// arithmetic and can be unit-tested with plain numbers.

export interface LabelBox {
  /** CSS px, the chip's anchor point. Mutated in place. */
  x: number;
  y: number;
  visible: boolean;
}

export interface DeCollideOptions {
  /** Minimum vertical distance between two chip anchors, CSS px. */
  strideY: number;
  /**
   * Chips further apart than this horizontally are treated as independent.
   * Roughly the chip width: two chips whose boxes cannot touch do not collide.
   */
  spreadX: number;
}

/**
 * Push overlapping chips apart vertically, in place.
 *
 * O(n log n) on the number of VISIBLE chips, which is at most a handful here
 * (four spacecraft plus one chip per numbered active region — a busy Sun has
 * fewer than a dozen). Runs at the 20 Hz DOM cadence, not per frame.
 */
export function deCollideLabels(boxes: LabelBox[], options: DeCollideOptions): void {
  const visible = boxes.filter((box) => box.visible);
  if (visible.length < 2) { return; }

  // Sort by y, remembering nothing else: the caller's array order is the chip
  // identity and must not change.
  const order = visible.slice().sort((a, b) => a.y - b.y);

  // Walk down the stack, opening a new independent run whenever a chip clears
  // the previous one horizontally.
  let runStart = 0;
  const closeRun = (endExclusive: number): void => {
    const run = order.slice(runStart, endExclusive);
    if (run.length < 2) { return; }
    // Rule 2: re-center. Summing BEFORE the push would use the already-moved
    // values, so the mean is taken from what the caller projected.
    const meanBefore = run.reduce((sum, box) => sum + box.y, 0) / run.length;
    for (let i = 1; i < run.length; i++) {
      const wanted = run[i - 1].y + options.strideY;
      if (run[i].y < wanted) { run[i].y = wanted; }
    }
    const meanAfter = run.reduce((sum, box) => sum + box.y, 0) / run.length;
    const shift = meanBefore - meanAfter;
    run.forEach((box) => { box.y += shift; });
  };

  for (let i = 1; i < order.length; i++) {
    const previous = order[i - 1];
    const current = order[i];
    const apart = Math.abs(current.x - previous.x) >= options.spreadX
      || current.y - previous.y >= options.strideY;
    if (apart) {
      closeRun(i);
      runStart = i;
    }
  }
  closeRun(order.length);
}
