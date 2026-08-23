// =====================================================================
// SDO product catalog + URL builders
// =====================================================================
// Pure data and string building — NO I/O happens in this file. Every URL
// pattern here was verified live against sdo.gsfc.nasa.gov (see the checks
// noted per builder); the flags in the product table exist because the host
// publishes different variants per product and a wrong guess is a 404 in a
// guest's face.
//
// Reminder (CLAUDE.md footgun 6): this host has NO CORS. These URLs may only
// ever be handed to <img>/<video> src, never to fetch(), and never with a
// `crossorigin` attribute.

/** Product codes as they appear in SDO filenames. */
export type ProductId =
  | "HMIIC"
  | "0304"
  | "0171"
  | "0193"
  | "0211"
  | "HMIB"
  | "0094"
  | "211193171";

/** Still resolutions the app offers the guest (the host also has 170/256/512/3072). */
export type DiskRes = 1024 | 2048 | 4096;

export interface Product {
  id: ProductId;
  /** Friendly name shown on the channel chip. */
  label: string;
  /** One-sentence, all-audiences description. Data, not markup. */
  blurb: string;
  /** Small line under the chip label; null for products with no single temperature. */
  tempLabel: string | null;
  /** A `<id>pfss` still variant is published (magnetic field lines baked in). */
  hasPfss: boolean;
  /** `latest_1024_<id>.mp4` (rolling 48 h) exists. */
  hasLatestMovie: boolean;
  /** `dailymov/.../<yyyymmdd>_1024_<id>.mp4` exists. */
  hasDailyMovie: boolean;
  /** Shown in the main chip row (the rest hide behind "More"). */
  primary: boolean;
  /**
   * Approximate size of the rolling 48 h movie, MB — shown to the guest BEFORE
   * any bytes load. MEASURED with HEAD requests (2026-08), rounded up so the
   * label never under-promises. Day-to-day drift is a few percent; the ratios
   * between channels are stable (0094 really is ~100 MB — it is 1-minute
   * cadence over two days).
   */
  approxMovieMb: number | null;
  /** Same, for the 24 h daily movie. Measured; varies < 10 % day to day. */
  approxDailyMovieMb: number | null;
  /**
   * Display scale that makes the solar disk the SAME on-screen diameter across
   * channels, so guests can flip between them and compare features directly.
   *
   * The GSFC images preserve each instrument's native plate scale: AIA is
   * ~0.6009 arcsec/px, HMI ~0.5044 arcsec/px, so the HMI disk is ~19% larger
   * in the frame. We normalize HMI DOWN to AIA's framing (0.5044/0.6009 =
   * 0.8395) rather than blowing AIA up, which would crop its off-limb corona.
   * The ratio is instrument geometry — it does not drift with Earth's distance
   * (that affects both instruments identically).
   */
  diskScale: number;
  /**
   * Display scale for the `...pfss` variant, when GSFC frames it differently
   * from the plain still. Absent means "same as diskScale".
   *
   * This is not a subtlety we could reason our way to — it had to be measured.
   * GSFC renders the PFSS overlay onto a COMMON frame, so `HMIBpfss` is already
   * resampled to AIA's plate scale while plain `HMIB` is at HMI's. Measured
   * limb diameter as a fraction of the frame (sub-pixel, steepest radial
   * gradient, identical across 1024/2048/4096):
   *
   *     latest_*_HMIB.jpg      0.9184     latest_*_0171.jpg      0.7824
   *     latest_*_HMIBpfss.jpg  0.7676     latest_*_0171pfss.jpg  0.7893
   *
   * So the overlay magnetogram needs NO correction — applying diskScale to it
   * rendered the Magnetic Map ~18 % undersized, which is the one channel whose
   * blurb invites guests to turn the overlay on. Cross-checked by compositing
   * `0171pfss` and `HMIBpfss` into separate colour channels: at scale 1.0 the
   * limbs AND GSFC's own active-region number labels coincide exactly.
   */
  diskScalePfss?: number;
}

/**
 * HMI-to-AIA disk normalization. This is the instruments' plate-scale ratio,
 * 0.5044 / 0.6009 arcsec/px — and the browse stills really are at native plate
 * scale: AIA 4500 (white light, so the same photospheric limb HMI sees)
 * measures 0.7711 of the frame against HMI's 0.9168, a ratio of 0.8411, within
 * 0.2 % of this constant.
 *
 * Deliberately NOT tuned to match the EUV channels' apparent limb, which
 * measures ~1.5 % larger (0171 sits at 0.7824). That ring is emission from
 * above the photosphere — real solar physics, not a framing error — so
 * cancelling it out would be lying about the Sun to make two circles agree.
 */
const HMI_DISK_SCALE = 0.8395;

/**
 * The eight channels the app offers, in chip order. Temperatures are the
 * canonical SDO/AIA characteristic temperatures, rounded for humans.
 */
export const PRODUCTS: readonly Product[] = [
  {
    id: "HMIIC",
    diskScale: HMI_DISK_SCALE,
    label: "Visible Sun",
    tempLabel: "~10,000 °F",
    blurb: "What your eyes would see (never look directly!). The dark freckles are sunspots — cooler patches where the magnetic field is strongest.",
    hasPfss: false,
    hasLatestMovie: false,
    hasDailyMovie: true,
    primary: true,
    approxMovieMb: null,
    approxDailyMovieMb: 8,
  },
  {
    id: "0304",
    diskScale: 1,
    label: "Chromosphere",
    tempLabel: "~90,000 °F",
    blurb: "The thin layer above the surface. Watch the edge for prominences — arcs of glowing gas bigger than Earth.",
    hasPfss: true,
    hasLatestMovie: true,
    hasDailyMovie: true,
    primary: true,
    approxMovieMb: 52,
    approxDailyMovieMb: 21,
  },
  {
    id: "0171",
    diskScale: 1,
    label: "Coronal Loops",
    tempLabel: "~1 million °F",
    blurb: "Magnetic loops glowing in ultraviolet — the Sun's atmosphere traced by its own magnetic field.",
    hasPfss: true,
    hasLatestMovie: true,
    hasDailyMovie: true,
    primary: true,
    approxMovieMb: 32,
    approxDailyMovieMb: 13,
  },
  {
    id: "0193",
    diskScale: 1,
    label: "Hot Corona",
    tempLabel: "~2 million °F",
    blurb: "The darker patches are coronal holes — open doors where the solar wind escapes into space.",
    hasPfss: true,
    hasLatestMovie: true,
    hasDailyMovie: true,
    primary: true,
    approxMovieMb: 16,
    approxDailyMovieMb: 6,
  },
  {
    id: "0211",
    diskScale: 1,
    label: "Active Regions",
    tempLabel: "~3.6 million °F",
    blurb: "Brightest where the magnetic field is most tangled — these are the places solar flares come from.",
    hasPfss: true,
    hasLatestMovie: true,
    hasDailyMovie: true,
    primary: true,
    approxMovieMb: 17,
    approxDailyMovieMb: 7,
  },
  {
    id: "HMIB",
    diskScale: HMI_DISK_SCALE,
    // GSFC already reframes the pfss magnetogram to AIA's plate scale.
    diskScalePfss: 1,
    label: "Magnetic Map",
    tempLabel: null,
    blurb: "White is magnetic field pointing at you, black is pointing away. These are the roots of the loops in the 3D view.",
    hasPfss: true,
    hasLatestMovie: false,
    hasDailyMovie: true,
    primary: true,
    approxMovieMb: null,
    approxDailyMovieMb: 18,
  },
  {
    id: "0094",
    diskScale: 1,
    label: "Flare Watch",
    tempLabel: "~11 million °F",
    blurb: "Only the hottest plasma shows up here — mostly during solar flares.",
    hasPfss: true,
    hasLatestMovie: true,
    hasDailyMovie: true,
    primary: false,
    approxMovieMb: 100,
    approxDailyMovieMb: 41,
  },
  {
    id: "211193171",
    diskScale: 1,
    label: "Three-Color Sun",
    tempLabel: null,
    blurb: "Three coronal temperatures blended into one psychedelic portrait.",
    hasPfss: true,
    hasLatestMovie: false,
    hasDailyMovie: false,
    primary: false,
    approxMovieMb: null,
    approxDailyMovieMb: null,
  },
];

export const PRIMARY_PRODUCTS: readonly Product[] = PRODUCTS.filter((p) => p.primary);
export const EXTRA_PRODUCTS: readonly Product[] = PRODUCTS.filter((p) => !p.primary);

/** Product lookup. Built at runtime so the source keeps clean camelCase keys. */
const BY_ID = new Map<string, Product>(PRODUCTS.map((p) => [p.id, p]));

/** The default channel — coronal loops read as "the Sun" to most people. */
export const DEFAULT_CHANNEL: ProductId = "0171";

/** Resolutions offered in the UI, in cycling order. */
export const DISK_RESOLUTIONS: readonly DiskRes[] = [1024, 2048, 4096];

/**
 * Resolution step-down ladder used when a load fails: try smaller until
 * something lands. 512 is below the UI's floor but is a fine last resort.
 */
export const RES_LADDER: readonly number[] = [4096, 2048, 1024, 512];

/** Resolutions at which pfss variants are published (NOT 3072). */
export const PFSS_RESOLUTIONS: readonly number[] = [512, 1024, 2048, 4096];

/** Resolution of the poster frame / prefetch warm-up image. */
const POSTER_RES = 512;

const LATEST_BASE = "https://sdo.gsfc.nasa.gov/assets/img/latest";
const DAILY_MOVIE_BASE = "https://sdo.gsfc.nasa.gov/assets/img/dailymov";

export function product(id: ProductId): Product {
  const p = BY_ID.get(id);
  // Unreachable for well-typed callers; deep links validate first.
  return p ?? BY_ID.get(DEFAULT_CHANNEL) as Product;
}

export function isProductId(value: string | null | undefined): value is ProductId {
  return value != null && BY_ID.has(value);
}

export function isDiskRes(value: number | null | undefined): value is DiskRes {
  return value != null && (DISK_RESOLUTIONS as readonly number[]).includes(value);
}

/** Human label for a resolution chip. */
export function resLabel(res: number): string {
  if (res >= 4096) { return "4K"; }
  if (res >= 2048) { return "2K"; }
  return "HD";
}

/**
 * Full-disk still.
 *
 * Verified: `latest_2048_0171.jpg` 200, `latest_2048_0171pfss.jpg` 200 (NO
 * underscore before "pfss" — the underscore form 404s), and
 * `latest_2048_HMIICpfss.jpg` 404 (hence `hasPfss`).
 *
 * `bust` appends `?t=` — used by the 15-minute auto-refresh and the one retry
 * after a load error, never on the first load (it would defeat the CDN cache).
 */
/**
 * Is the `...pfss` variant what we will actually request? The overlay only
 * exists for some channels and only at some resolutions, so asking for it does
 * not mean getting it — and `diskScaleFor` has to agree with `stillUrl`
 * exactly, or the disk is scaled for an image we did not load.
 */
export function usesPfssVariant(id: ProductId, res: number, pfss: boolean): boolean {
  return pfss && product(id).hasPfss && PFSS_RESOLUTIONS.includes(res);
}

/**
 * Display scale for the still `stillUrl(id, res, pfss)` returns — see
 * Product.diskScale and Product.diskScalePfss.
 */
export function diskScaleFor(id: ProductId, res: number, pfss: boolean): number {
  const item = product(id);
  return usesPfssVariant(id, res, pfss) ? item.diskScalePfss ?? item.diskScale : item.diskScale;
}

export function stillUrl(id: ProductId, res: number, pfss = false, bust?: number): string {
  const usePfss = usesPfssVariant(id, res, pfss);
  const suffix = usePfss ? "pfss" : "";
  const query = bust === undefined ? "" : `?t=${bust}`;
  return `${LATEST_BASE}/latest_${res}_${id}${suffix}.jpg${query}`;
}

/** 512 px still — the <video> poster and the chip prefetch warm-up. */
export function posterUrl(id: ProductId): string {
  return stillUrl(id, POSTER_RES, false);
}

/**
 * Rolling 48-hour movie. 1024 only, and only where `hasLatestMovie` is set:
 * verified `latest_1024_0171.mp4` 200 but `latest_1024_HMIB.mp4` and
 * `latest_1024_211193171.mp4` 404. These files are BIG (0171 ≈ 33 MB) —
 * never preload, always show the size first.
 */
export function latestMovieUrl(id: ProductId): string {
  return `${LATEST_BASE}/latest_1024_${id}.mp4`;
}

/**
 * Fallback size label for a daily movie with no measurement in the table.
 * Per-channel measured values live in `approxDailyMovieMb` and should be
 * preferred — they range from 6 MB (0193) to 41 MB (0094), so one constant
 * cannot be honest for all of them.
 */
export const DAILY_MOVIE_MB = 12;

/**
 * Daily 24-hour movie for a given UTC date. Published a few hours after the
 * day closes, so callers pass YESTERDAY UTC and fall back one more day when
 * the <video> element reports an error.
 *
 * Verified for 0171 / HMIB / HMIIC; 404 for 211193171 (hence `hasDailyMovie`).
 */
export function dailyMovieUrl(id: ProductId, date: Date): string {
  const yyyy = String(date.getUTCFullYear());
  const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(date.getUTCDate()).padStart(2, "0");
  return `${DAILY_MOVIE_BASE}/${yyyy}/${mm}/${dd}/${yyyy}${mm}${dd}_1024_${id}.mp4`;
}

/** UTC midnight-based date `daysAgo` days back — the daily-movie date helper. */
export function utcDaysAgo(daysAgo: number): Date {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - daysAgo);
  return d;
}

/** True when the channel has any movie at all (gates the movie-mode toggle). */
export function hasAnyMovie(id: ProductId): boolean {
  const p = product(id);
  return p.hasLatestMovie || p.hasDailyMovie;
}
