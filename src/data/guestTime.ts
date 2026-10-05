// =====================================================================
// One time convention for guests: local time, with the zone where it fits
// =====================================================================
// Guests used to see three conventions on one screen: local clock times on
// the stat chips, "16:00 UT" on scrubbed chips, and "Oct 5, 08:00 UTC" on the
// scrubber and the event cards (2026-10-04 audit). A lobby guest reads local
// time. Event cards keep UTC as a second line, because that is how the
// sources (DONKI, NOAA) publish an event and how anyone looking it up will
// find it.
//
// Entry-chunk safe, no dependencies.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Oct 5, 3:00 AM CDT": date, local clock time and zone. */
export function guestStamp(unix: number): string {
  const d = new Date(unix * 1000);
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${time}`;
}

/** "3:00 AM": local clock time only, for tight spaces like a stat chip. */
export function guestClock(unix: number): string {
  return new Date(unix * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/** "Oct 5, 08:00 UTC": for event cards' second line. */
export function utcStamp(unix: number): string {
  const d = new Date(unix * 1000);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${hh}:${mm} UTC`;
}
