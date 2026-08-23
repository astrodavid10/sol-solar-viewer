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
// positions. Three rules, in order:
//
//   1. Chips that do not overlap horizontally are independent. Two labels on
//      opposite limbs share a y and must not be pushed apart for it.
//   2. Every chip clears the stride against every ALREADY-PLACED chip it
//      overlaps horizontally — not merely against its predecessor in y.
//   3. Each independent group is then shifted back onto its own original mean,
//      so it spreads about where it was instead of drifting downward.
//
// Rule 2 is stronger than it looks, and it is why this file was rewritten. The
// original version closed a "run" whenever a chip cleared the PREVIOUS one,
// which meant chip A and chip C could land in different runs because B
// separated them in y — and then still overlap each other. Fuzzed over 20,000
// random layouts, that left an overlap in **3.67% of realistic phone layouts,
// and 33.95% when the chips cluster near disk center**. Clustering near disk
// center is not the unusual case: active regions live in the activity belts,
// which is exactly where they bunch up. So the common case was the broken one.
// (HANDOFF §8.0 had already flagged two regions near disk centre as "the
// collision case §8.4 did not anticipate" — this is that case, measured.)
//
// The pairwise sweep is O(n^2), which is free here: n is the number of VISIBLE
// chips — at most four spacecraft plus one per numbered active region, so under
// a dozen and under 150 comparisons.
//
// ALLOCATES NOTHING. That used not to matter, because this file's docstring
// claimed it "runs at the 20 Hz DOM cadence, not per frame" — which stopped
// being true when the projection throttle grew a `moved` short-circuit so
// labels would stop lagging the features they name. It now runs on every
// rendered frame while the camera is in motion, which is precisely when a
// `filter()` plus a `slice().sort()` plus a fresh slice and two closures per run
// becomes garbage-collector pressure during a drag. Reused module-scope buffers
// instead.
//
// No three.js and no WWT imports (CLAUDE.md footgun 12) — this is pure screen
// arithmetic, and `scripts/check_label_layout.mjs` tests it with plain numbers.

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

// Reused across calls. `order` holds references to the caller's boxes; the
// parallel arrays are indexed the same way.
const order: LabelBox[] = [];
/** Pre-sweep y, so a group can be re-centered on where it actually was. */
const originalY: number[] = [];
/** Union-find parent per chip, over the x-overlap graph. */
const parent: number[] = [];
/** Group id per chip (its union-find root). */
const groupOf: number[] = [];
const groupSumBefore: number[] = [];
const groupSumAfter: number[] = [];
const groupCount: number[] = [];

/**
 * Push overlapping chips apart vertically, in place.
 *
 * Guarantees, all three checked by `scripts/check_label_layout.mjs`:
 *   - no two visible chips within `spreadX` horizontally are closer than
 *     `strideY` vertically;
 *   - `x` is never touched and the caller's array order never changes, because
 *     that order IS the chip identity — the template renders `chips[i]`, so a
 *     reorder would relabel every marker;
 *   - each independent group keeps its original mean y, so nothing drifts.
 */
export function deCollideLabels(boxes: LabelBox[], options: DeCollideOptions): void {
  let n = 0;
  for (const box of boxes) {
    if (box.visible) {
      order[n] = box;
      n++;
    }
  }
  if (n < 2) { return; }
  if (order.length > n) { order.length = n; }

  // Sort the buffer of REFERENCES, never the caller's array (see the identity
  // guarantee above).
  order.sort((a, b) => a.y - b.y);

  // --- group by horizontal overlap, before anything moves ------------------
  // Union-find over the x-overlap graph. Because a group only ever contains
  // chips reachable through x-overlap, two chips in DIFFERENT groups provably
  // do not overlap in x -- which is what makes the rigid per-group shift at the
  // end safe: it can never create a new collision.
  //
  // This started as a cheaper scan that cached the current chip's group id and
  // relabelled on a merge. It was WRONG in a way only the fuzz found: a merge
  // can relabel the outer chip itself, so the cached id goes stale and later
  // neighbours join a group that no longer exists. That left 38 overlapping
  // pairs in 20,000 layouts -- rare enough to look like it worked.
  for (let i = 0; i < n; i++) {
    originalY[i] = order[i].y;
    parent[i] = i;
  }
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (Math.abs(order[j].x - order[i].x) >= options.spreadX) { continue; }
      let ra = i;
      while (parent[ra] !== ra) { ra = parent[ra]; }
      let rb = j;
      while (parent[rb] !== rb) { rb = parent[rb]; }
      if (ra !== rb) { parent[ra > rb ? ra : rb] = ra < rb ? ra : rb; }
    }
  }
  for (let i = 0; i < n; i++) {
    let r = i;
    while (parent[r] !== r) { r = parent[r]; }
    groupOf[i] = r;
  }

  // --- rule 2: clear the stride against every overlapping placed chip ------
  // Walking in y order means every chip that could constrain `i` already holds
  // its final pre-shift position, so one pass is enough.
  for (let i = 1; i < n; i++) {
    let wanted = order[i].y;
    for (let j = 0; j < i; j++) {
      if (Math.abs(order[i].x - order[j].x) >= options.spreadX) { continue; }
      const clear = order[j].y + options.strideY;
      if (clear > wanted) { wanted = clear; }
    }
    order[i].y = wanted;
  }

  // --- rule 3: put each group back on its own mean -------------------------
  // Group ids are union-find roots, i.e. indices in [0, n) -- not a dense
  // 0..groups-1 range -- so clear all n slots rather than a group count.
  for (let i = 0; i < n; i++) {
    groupSumBefore[i] = 0;
    groupSumAfter[i] = 0;
    groupCount[i] = 0;
  }
  for (let i = 0; i < n; i++) {
    const g = groupOf[i];
    groupSumBefore[g] += originalY[i];
    groupSumAfter[g] += order[i].y;
    groupCount[g] += 1;
  }
  for (let i = 0; i < n; i++) {
    const g = groupOf[i];
    if (groupCount[g] > 1) {
      order[i].y += (groupSumBefore[g] - groupSumAfter[g]) / groupCount[g];
    }
  }
}
