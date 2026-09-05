import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Pull a human-readable message out of an Axios error from the API. Handles a
 * plain string `detail` and FastAPI's `detail: [{ msg }]` validation shape;
 * falls back to `fallback` for anything else.
 */
export function httpStatus(err: unknown): number | undefined {
  return (err as { response?: { status?: number } } | null)?.response?.status;
}

export function extractApiError(err: unknown, fallback = "Request failed"): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object" && "msg" in detail[0]) {
    return String((detail[0] as { msg: unknown }).msg);
  }
  return fallback;
}

// Date formatting — single canonical surface so the whole app shows
// consistent date/time strings. en-GB picks the "5 May 2026" form which works
// well next to both English and Russian UI chrome.

const DATE_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const DATE_TIME_SHORT_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return DATE_FORMATTER.format(date);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return DATE_TIME_FORMATTER.format(date);
}

export function formatDateTimeShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return DATE_TIME_SHORT_FORMATTER.format(date);
}

/**
 * Media duration as `H:MM:SS`.
 *
 * Hours are always shown, even when zero: a column mixing `48:00` and `2:22:00`
 * reads as "48 hours" at a glance. Returns null for missing/zero so each call
 * site can pick its own placeholder.
 */
export function formatDuration(seconds: number | null | undefined): string | null {
  if (!seconds || seconds < 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/**
 * Duration for a badge overlaid on a thumbnail, in the shape video players use:
 * `5:12`, and `1:24:03` only once there is an hour to show.
 *
 * The column-aligned `formatDuration` above always keeps the hour, which is
 * right in a table and wrong on a badge, where `0:05:12` just reads as noise.
 */
export function formatDurationCompact(seconds: number | null | undefined): string | null {
  if (!seconds || seconds < 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/**
 * Drops a leading machine timestamp from an auto-generated recording name.
 *
 * Ingested names look like `2026-05-14_181145_ИИ_Алгоритмы…`; the prefix repeats
 * the date already shown next to the title and pushes the meaningful part into
 * the ellipsis. Returns the input unchanged when there is no such prefix, and
 * never returns an empty string.
 */
export function stripLeadingTimestamp(name: string): string {
  const stripped = name.replace(/^\d{4}-\d{2}-\d{2}[_ -]?(?:\d{6}|\d{2}[:_-]\d{2}(?:[:_-]\d{2})?)?[_ -]*/, "");
  return stripped.trim() || name;
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * Scroll `el` into view inside `container`, and nowhere else.
 *
 * `Element.scrollIntoView` adjusts every scrollable ancestor up to the
 * document. Using it to follow playback therefore yanks the whole page back to
 * the list whenever the reader has scrolled somewhere else — several times a
 * minute, for as long as the video runs. This touches only the container's own
 * `scrollTop`, and does nothing when the element is already visible.
 */
export function scrollIntoViewWithin(container: HTMLElement | null, el: HTMLElement | null): void {
  if (!container || !el) return;
  const c = container.getBoundingClientRect();
  const e = el.getBoundingClientRect();
  if (e.top < c.top) container.scrollTop -= c.top - e.top;
  else if (e.bottom > c.bottom) container.scrollTop += e.bottom - c.bottom;
}
