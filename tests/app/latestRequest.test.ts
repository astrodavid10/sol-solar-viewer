// T34: a slow load must never paint over the guest's newer choice.
import { describe, expect, it } from "vitest";

import { LatestRequest } from "../../src/three/latestRequest";

describe("LatestRequest", () => {
  it("lets only the newest ticket paint", () => {
    const req = new LatestRequest();
    const slow = req.begin("sdo0171_hires.jpg");
    const fast = req.begin("sdoHMIB_hires.jpg");
    expect(req.isCurrent(slow)).toBe(false);   // the 0171 download lands late: dropped
    expect(req.isCurrent(fast)).toBe(true);
    expect(req.inFlight()).toBe("sdoHMIB_hires.jpg");
  });

  it("clear(ticket) only clears the request it belongs to", () => {
    const req = new LatestRequest();
    const old = req.begin("a");
    const now = req.begin("b");
    req.clear(old);                            // a stale completion must not wipe b
    expect(req.inFlight()).toBe("b");
    req.clear(now);
    expect(req.inFlight()).toBeNull();
  });

  it("a ticket for the same key is still superseded by a newer begin", () => {
    const req = new LatestRequest();
    const first = req.begin("x");
    req.begin("x");
    expect(req.isCurrent(first)).toBe(false);
  });
});
