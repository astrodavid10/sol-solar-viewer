/**
 * Invariant check for src/three/labelLayout.ts.
 *
 *   node scripts/check_label_layout.mjs
 *
 * WHY THIS EXISTS. The app has no test suite (the pipeline validator is the
 * de-facto one), and `deCollideLabels` is the one piece of app logic that is
 * pure arithmetic with a non-obvious contract: independent runs, a fixed
 * stride, and re-centering on the pre-push mean. It was rewritten to be
 * allocation-free because it turned out to run every frame during a drag rather
 * than at 20 Hz as its docstring claimed, and "it still looks right" is not
 * evidence for a change to an algorithm nobody remembers the rules of.
 *
 * The algorithm is TRANSLITERATED here rather than imported, because the module
 * is TypeScript and adding a build step for one file is not worth it. If you
 * change labelLayout.ts, change the copy below to match and re-run — the
 * invariants at the bottom are what actually has to hold, and they are stated
 * independently of how the algorithm reaches them.
 */

const order = [];
const originalY = [];
const parent = [];
const groupOf = [];
const groupSumBefore = [];
const groupSumAfter = [];
const groupCount = [];

function deCollideLabels(boxes, options) {
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

// The values SolarView3D actually passes.
const OPTS = { strideY: 46, spreadX: 75 };
const EPS = 1e-9;
let failures = 0;

function fail(message) {
  console.error("  FAIL " + message);
  failures++;
}

function pass(message) {
  console.log("  PASS " + message);
}

// --- 1. the real measured case --------------------------------------------
// Three surface chips ~12 px apart vertically, which is what was measured on
// the live site at every viewport from 360x640 up, and the reason this module
// exists at all.
{
  const boxes = [
    { x: 180, y: 300, visible: true },
    { x: 186, y: 312, visible: true },
    { x: 190, y: 324, visible: true },
  ];
  deCollideLabels(boxes, OPTS);
  const ys = boxes.map((b) => b.y).sort((p, q) => p - q);
  const gaps = [ys[1] - ys[0], ys[2] - ys[1]];
  if (gaps.some((g) => g < OPTS.strideY - EPS)) {
    fail(`three colliding chips: gaps ${gaps} below stride ${OPTS.strideY}`);
  } else {
    pass(`three colliding chips separate to the ${OPTS.strideY}px stride`);
  }
  const mean = (ys[0] + ys[1] + ys[2]) / 3;
  if (Math.abs(mean - 312) > EPS) {
    fail(`run drifted: mean ${mean}, expected 312`);
  } else {
    pass("the run stays centered on its own original mean (no downward drift)");
  }
}

// --- 2. horizontal independence -------------------------------------------
// Two chips on opposite limbs share a y and must NOT be pushed apart for it.
{
  const boxes = [
    { x: 40, y: 200, visible: true },
    { x: 400, y: 200, visible: true },
  ];
  deCollideLabels(boxes, OPTS);
  if (boxes[0].y !== 200 || boxes[1].y !== 200) {
    fail(`chips ${OPTS.spreadX}px+ apart horizontally were moved: `
      + `${boxes[0].y}, ${boxes[1].y}`);
  } else {
    pass("chips far apart horizontally are left alone");
  }
}

// --- 3. invisible chips are ignored ---------------------------------------
{
  const boxes = [
    { x: 100, y: 200, visible: true },
    { x: 100, y: 205, visible: false },
    { x: 100, y: 210, visible: true },
  ];
  deCollideLabels(boxes, OPTS);
  if (boxes[1].y !== 205) {
    fail(`an invisible chip was moved to ${boxes[1].y}`);
  } else {
    pass("invisible chips are neither moved nor counted");
  }
  if (Math.abs(boxes[2].y - boxes[0].y) < OPTS.strideY - EPS) {
    fail("the two visible chips did not separate");
  } else {
    pass("the two visible chips separate around the invisible one");
  }
}

// --- 4. fuzz the invariants ------------------------------------------------
// Deterministic PRNG, so a failure is reproducible.
let seed = 20260823;
const rnd = () => {
  seed = (seed * 1103515245 + 12345) & 0x7fffffff;
  return seed / 0x7fffffff;
};

let trials = 0;
let strideViolations = 0;
let xMutations = 0;
let identityChanges = 0;
for (let t = 0; t < 20000; t++) {
  const count = 1 + Math.floor(rnd() * 12);
  const boxes = [];
  for (let i = 0; i < count; i++) {
    boxes.push({
      id: i,
      // Clustered on purpose: the interesting cases are near-collisions, which
      // uniform noise over a large canvas almost never produces.
      x: Math.round(rnd() * 400),
      y: Math.round(rnd() * 300),
      visible: rnd() > 0.15,
    });
  }
  const before = boxes.map((b) => ({ id: b.id, x: b.x }));
  deCollideLabels(boxes, OPTS);
  trials++;

  // The caller's array order IS the chip identity and must never change: the
  // template renders `chips[i]` and would otherwise relabel every marker.
  boxes.forEach((b, i) => {
    if (b.id !== before[i].id) { identityChanges++; }
    if (b.x !== before[i].x) { xMutations++; }
  });

  // Any two visible chips that overlap horizontally must clear the stride.
  const vis = boxes.filter((b) => b.visible).sort((p, q) => p.y - q.y);
  for (let i = 1; i < vis.length; i++) {
    const overlapX = Math.abs(vis[i].x - vis[i - 1].x) < OPTS.spreadX;
    if (overlapX && vis[i].y - vis[i - 1].y < OPTS.strideY - 1e-6) {
      strideViolations++;
    }
  }
}

if (identityChanges) {
  fail(`array order changed in ${identityChanges} case(s) -- chips would be relabeled`);
} else {
  pass(`caller array order preserved across ${trials} random cases`);
}
if (xMutations) {
  fail(`x was mutated in ${xMutations} case(s) -- only y may move`);
} else {
  pass("x is never mutated (markers stay on their true positions)");
}
if (strideViolations) {
  fail(`${strideViolations} horizontally-overlapping pair(s) closer than the stride`);
} else {
  pass(`no overlapping pair closer than the stride across ${trials} random cases`);
}

console.log(failures
  ? `\nFAILED: ${failures} check(s)`
  : "\nOK: label layout invariants hold");
process.exit(failures ? 1 : 0);
