// Polling intervals (ms)
export const POLL_INTERVAL_LIST = 4000;
export const POLL_INTERVAL_DETAIL = 3000;

// Search debounce (ms)
export const DEBOUNCE_SEARCH = 400;

// Pagination page sizes
export const PER_PAGE_RECORDINGS = 20;
export const PER_PAGE_PRESETS = 24;
export const PER_PAGE_TEMPLATES = 20;
export const PER_PAGE_LARGE = 100;

// Toast / feedback message durations (ms)
export const TOAST_SHORT = 3000;
export const TOAST_LONG = 5000;

// Recording statuses that trigger active polling
export const ACTIVE_POLL_STATUSES = new Set(["DOWNLOADING", "PROCESSING", "UPLOADING"]);
