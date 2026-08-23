/**
 * Sol — GONG relay (Cloudflare Worker)
 *
 * WHY THIS EXISTS
 * ---------------
 * `gong2.nso.edu` drops connections from GitHub Actions runners entirely:
 * connect TIMEOUTS on every request, every run, while the identical request
 * from a workstation answers HTTP 200 in 0.35 s. See CLAUDE.md footgun 33.
 *
 * There is no free upstream alternative — this was researched, not assumed.
 * Every hostname that serves the mrzqs product (gong.nso.edu, nispdata,
 * magmap, and anonymous FTP) resolves to the SAME address, 146.5.21.69, so
 * they all sit behind one firewall; sunpy's VSO `GONGClient` is a wrapper
 * around that same host; JSOC carries no GONG series at all; Helioviewer has
 * GONG H-alpha, which is a different physical observable; and NCEI's archive
 * is not publicly downloadable. What is left is relaying the request from a
 * network NSO does not block.
 *
 * Cloudflare's edge is a categorically different address space from the
 * Azure ranges GitHub's hosted runners live in, so a block aimed at those
 * ranges should not apply here. That is inference, not proof — `probe-sources`
 * in CI is what turns it into evidence.
 *
 * DEPLOY
 * ------
 *   npm install -g wrangler
 *   wrangler login
 *   wrangler deploy                      # uses wrangler.toml beside this file
 *   wrangler secret put RELAY_TOKEN      # paste a long random string
 *
 * Then add two repository secrets (Settings -> Secrets and variables ->
 * Actions):
 *   SOL_GONG_PROXY_BASE   https://<your-worker>.workers.dev/oQR/zqs
 *   SOL_GONG_PROXY_TOKEN  the same random string
 *
 * The pipeline picks these up with no code change (pipeline/config.py's
 * GONG_PROXY_BASE / GONG_PROXY_TOKEN), and rewrites URLs at REQUEST TIME only
 * — cache keys and published provenance keep citing gong2.nso.edu, because
 * NSO is the actual source of the data.
 *
 * BEING A GOOD CITIZEN
 * --------------------
 * Two deliberate restrictions, because a service that already firewalls a
 * cloud provider does not need an open proxy pointed at it:
 *   1. Requests must carry the shared secret.
 *   2. Paths must match the two shapes the pipeline actually asks for. This
 *      cannot be used to mirror the rest of NSO.
 * Responses are edge-cached, so a re-run or a retry costs NSO nothing.
 */

const ORIGIN = "https://gong2.nso.edu/oQR/zqs";

// The only two shapes the pipeline requests: a day directory listing, and one
// magnetogram inside it. Anchored, so nothing else gets through.
const DIR_RE = /^\/oQR\/zqs\/\d{6}\/mrzqs\d{6}\/$/;
const FILE_RE = /^\/oQR\/zqs\/\d{6}\/mrzqs\d{6}\/mrzqs\d{6}t\d{4}c\d+_\d+\.fits\.gz$/;

// A directory listing is a few KB and a magnetogram ~240 KB (measured).
const MAX_BYTES = 8 * 1024 * 1024;

// Listings change as GONG publishes; the FITS files never change once written.
const TTL_DIR = 600; // 10 min
const TTL_FILE = 86400; // 1 day

function deny(status, message) {
  return new Response(message + "\n", {
    status,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return deny(405, "only GET and HEAD");
    }

    // Fail closed. An unconfigured worker must not become an open relay.
    if (!env.RELAY_TOKEN) {
      return deny(503, "relay is not configured (RELAY_TOKEN unset)");
    }
    if (request.headers.get("X-Sol-Relay-Token") !== env.RELAY_TOKEN) {
      return deny(403, "bad or missing X-Sol-Relay-Token");
    }

    const url = new URL(request.url);
    const isDir = DIR_RE.test(url.pathname);
    const isFile = FILE_RE.test(url.pathname);
    if (!isDir && !isFile) {
      return deny(404, "path is not a GONG mrzqs listing or magnetogram");
    }

    const target = ORIGIN + url.pathname.slice("/oQR/zqs".length);
    let upstream;
    try {
      upstream = await fetch(target, {
        method: request.method,
        headers: {
          // Pass our own identity through, so an NSO operator looking at their
          // logs sees the pipeline rather than an anonymous proxy.
          "User-Agent":
            request.headers.get("User-Agent") ||
            "sol-pipeline (+https://github.com/astrodavid10/sol-solar-viewer)",
          Accept: "*/*",
        },
        cf: {
          cacheTtl: isFile ? TTL_FILE : TTL_DIR,
          cacheEverything: true,
        },
      });
    } catch (err) {
      // Say what actually happened. The whole reason this worker exists is a
      // failure that was invisible for four CI runs (footgun 32's lesson).
      return deny(502, "upstream fetch failed: " + (err && err.message));
    }

    if (!upstream.ok) {
      return deny(
        upstream.status,
        "upstream returned HTTP " + upstream.status + " " + upstream.statusText
      );
    }

    const declared = Number(upstream.headers.get("content-length") || 0);
    if (declared > MAX_BYTES) {
      return deny(413, "upstream body is " + declared + " bytes");
    }

    const headers = new Headers();
    for (const k of ["content-type", "content-length", "last-modified", "etag"]) {
      const v = upstream.headers.get(k);
      if (v) headers.set(k, v);
    }
    headers.set("cache-control", "public, max-age=" + (isFile ? TTL_FILE : TTL_DIR));
    headers.set("x-sol-relay-origin", target);

    return new Response(upstream.body, { status: 200, headers });
  },
};
