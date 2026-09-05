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
export const ACTIVE_POLL_STATUSES = new Set([
  "DOWNLOADING",
  "PROCESSING",
  "UPLOADING",
  "PENDING_CONVERSION",
]);

// Returns true if a recording needs active polling (on_air is the canonical signal;
// status-based check is a fallback for recordings created before the on_air migration).
export function needsActivePoll(recording: { on_air?: boolean; status: string }): boolean {
  return recording.on_air === true || ACTIVE_POLL_STATUSES.has(recording.status);
}
