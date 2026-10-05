// T37: the kiosk QR must never encode an address a guest's phone cannot open.
import { describe, expect, it } from "vitest";

import { isReachableFromPhone, takeHomeUrl } from "../../src/kiosk/takeHome";

describe("isReachableFromPhone", () => {
  it.each([
    ["https://astrodavid10.github.io/sol-solar-viewer/", true],
    ["http://example.org/x", true],
    ["http://localhost:8080/", false],
    ["http://127.0.0.1:8080/", false],
    ["http://192.168.1.121:8080/", false],
    ["http://10.0.0.5/", false],
    ["http://172.20.1.1/", false],
    ["http://172.32.1.1/", true],
    ["http://169.254.1.1/", false],
    ["http://kiosk.local/", false],
    ["http://[::1]:8080/", false],
    ["file:///C:/sol/index.html", false],
    ["not a url", false],
  ])("%s -> %s", (url, ok) => {
    expect(isReachableFromPhone(url)).toBe(ok);
  });
});

describe("takeHomeUrl", () => {
  it("adds the channel to the configured base", () => {
    expect(takeHomeUrl("https://astrodavid10.github.io/sol-solar-viewer/", "HMIB"))
      .toBe("https://astrodavid10.github.io/sol-solar-viewer/?texch=HMIB");
  });
});
