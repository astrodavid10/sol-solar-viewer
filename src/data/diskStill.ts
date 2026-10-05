// =====================================================================
// Today's Sun as a flat picture, for when the 3D view is loading or failed
// =====================================================================
// The pipeline publishes `texture/texture.json` -> `disk_still`: the newest
// SDO 0171 still at 1024 px, same origin (docs/CONTRACT.md, T33). The loading
// cover and both failure cards show it, so a guest whose 3D view cannot load
// still sees today's Sun instead of a black panel.
//
// No bundled stand-in: the only image shipped with the app (preview.jpg) is a
// screenshot of the app for link previews, and captioning it as a picture of
// the Sun would be false. Without today's still the cards show text only.
//
// Entry-chunk safe: no engine, no three.js, just one small fetch.

export interface DiskStill {
  url: string;
  /** Observation time, for the caption; null if the manifest omits it. */
  obsUnix: number | null;
}

let pending: Promise<DiskStill | null> | null = null;

/** Fetched once per page; never rejects. Null when there is no still. */
export function fetchDiskStill(): Promise<DiskStill | null> {
  if (pending) { return pending; }
  pending = (async () => {
    try {
      const base = new URL("data/texture/", document.baseURI);
      const response = await fetch(new URL("texture.json", base).href);
      if (!response.ok) { return null; }
      /* eslint-disable @typescript-eslint/naming-convention -- pipeline JSON keys */
      const doc = await response.json() as {
        generated_unix?: number;
        disk_still?: { url?: string; obs_iso?: string };
      };
      /* eslint-enable @typescript-eslint/naming-convention */
      const name = doc.disk_still?.url;
      if (typeof name !== "string" || name === "") { return null; }
      const url = new URL(name, base);
      if (doc.generated_unix) { url.searchParams.set("v", String(doc.generated_unix)); }
      const obs = Date.parse(String(doc.disk_still?.obs_iso)) / 1000;
      return { url: url.href, obsUnix: Number.isFinite(obs) ? obs : null };
    } catch {
      return null;
    }
  })();
  return pending;
}

/** "SDO took this picture of the Sun at 3:40 PM CDT." */
export function diskStillCaption(still: DiskStill | null): string {
  if (!still) { return ""; }
  if (still.obsUnix === null) { return "SDO took this picture of the Sun today."; }
  const time = new Date(still.obsUnix * 1000).toLocaleTimeString([], {
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  });
  return `SDO took this picture of the Sun at ${time}.`;
}
