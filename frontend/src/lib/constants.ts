// Polling intervals (ms)
export const POLL_INTERVAL_LIST = 4000;
export const POLL_INTERVAL_DETAIL = 3000;

// Search debounce (ms)
export const DEBOUNCE_SEARCH = 400;

// Pagination page sizes
export const PER_PAGE_RECORDINGS = 20;
/** Page sizes offered on /recordings. Capped at 100 by the API (per_page le=100). */
export const PER_PAGE_RECORDINGS_OPTIONS = [20, 50, 100];
export const PER_PAGE_PRESETS = 24;
export const PER_PAGE_PLAYLISTS = 24;
export const PER_PAGE_CHANNELS = 24;
/** Product cap: playlists/user, items/playlist, videos or playlists per channel. */
export const LEAP_CATALOG_CAP = 200;
/** Recordings picker: API `per_page` ceiling. Search finds the rest. */
export const PER_PAGE_RECORDINGS_PICKER = 100;

/** Channel art: full file below lg (no crop); 6:1 cover strip on large screens. */
export const CHANNEL_BANNER_FRAME = "w-full overflow-hidden bg-muted lg:aspect-[6/1]";
export const CHANNEL_BANNER_IMG = "block h-auto w-full lg:h-full lg:object-cover";
export const PER_PAGE_TEMPLATES = 20;
export const PER_PAGE_TEMPLATES_OPTIONS = [20, 50, 100];
export const PER_PAGE_SOURCES = 24;
export const PER_PAGE_CREDENTIALS = 20;
export const PER_PAGE_AUTOMATION = 20;
export const PER_PAGE_LARGE = 100;

// Toast / feedback message durations (ms)
export const TOAST_SHORT = 3000;
export const TOAST_LONG = 5000;

// Recording statuses that trigger active polling
export const ACTIVE_POLL_STATUSES = new Set<string>([
  "DOWNLOADING",
  "PROCESSING",
  "UPLOADING",
  "PENDING_SOURCE",
  "PENDING_CONVERSION",
]);

/** Statuses an automation job can target (real ProcessingStatus values, not stage names). */
export const AUTOMATION_STATUS_FILTER_OPTIONS = [
  {
    value: "PENDING_SOURCE",
    hint: "File is still assembling on the source (Zoom or MTS Link)",
  },
  {
    value: "PENDING_CONVERSION",
    hint: "MTS Link is rendering MP4. Needed so the job retries until the file is ready",
  },
  {
    value: "INITIALIZED",
    hint: "Ready to download",
  },
  {
    value: "DOWNLOADED",
    hint: "Already downloaded; processing can start",
  },
  {
    value: "READY",
    hint: "Already finished; select only if you want to run again",
  },
] as const;

export const DEFAULT_AUTOMATION_STATUS_FILTER = [
  "INITIALIZED",
  "PENDING_CONVERSION",
  "PENDING_SOURCE",
] as const;

// Returns true if a recording needs active polling (on_air is the canonical signal;
// status-based check is a fallback for recordings created before the on_air migration).
export function needsActivePoll(recording: { on_air?: boolean; status: string }): boolean {
  return recording.on_air === true || ACTIVE_POLL_STATUSES.has(recording.status);
}
