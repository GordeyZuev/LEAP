import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Collapse newlines/tabs/runs of spaces so titles match how the API stores display_name. */
export function collapseWhitespace(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/**
 * Pull a human-readable message out of an Axios error from the API.
 *
 * A specific `detail` (quota text, validation `msg`, auth lockout) wins.
 * Generic statuses — rate limit, upload too large, 5xx, offline, timeout —
 * become one short sentence. Anything else uses `fallback`.
 */
export function httpStatus(err: unknown): number | undefined {
  return axiosResponse(err)?.status;
}

const GENERIC_DETAIL = /^(rate limit exceeded|too many requests|internal server error)$/i;

export function extractApiError(err: unknown, fallback = "Request failed"): string {
  const response = axiosResponse(err);
  const specific = specificDetail(response?.data?.detail);
  if (specific) return specific;
  return statusMessage(err, response) ?? fallback;
}

interface AxiosLikeResponse {
  status?: number;
  data?: { detail?: unknown; retry_after?: unknown };
  headers?: {
    "retry-after"?: unknown;
    get?: (name: string) => unknown;
  };
}

function axiosResponse(err: unknown): AxiosLikeResponse | undefined {
  if (!err || typeof err !== "object" || !("response" in err)) return undefined;
  const response = (err as { response?: AxiosLikeResponse }).response;
  return response && typeof response === "object" ? response : undefined;
}

function specificDetail(detail: unknown): string | undefined {
  if (typeof detail === "string") {
    const text = detail.trim();
    if (!text || text.length > 240 || GENERIC_DETAIL.test(text)) return undefined;
    return text;
  }
  if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object" && detail[0] !== null && "msg" in detail[0]) {
    const text = String(detail[0].msg).trim();
    return text || undefined;
  }
  return undefined;
}

function statusMessage(err: unknown, response: AxiosLikeResponse | undefined): string | undefined {
  const transport = transportKind(err, response);
  if (transport === "timeout") return "The request timed out. Try again.";
  if (transport === "offline") return "Could not reach the server. Check your connection and try again.";
  const status = response?.status;
  if (status === 429) return rateLimitMessage(retryAfterSeconds(response));
  if (status === 413) return "This file is larger than the upload limit.";
  if (status != null && status >= 500) return "The server had a problem. Try again in a moment.";
  return undefined;
}

function transportKind(err: unknown, response: AxiosLikeResponse | undefined): "offline" | "timeout" | undefined {
  if (response || !err || typeof err !== "object") return undefined;
  const code = (err as { code?: string }).code;
  // A canceled request has no response too. It is not a dropped connection.
  if (code === "ERR_CANCELED") return undefined;
  if (code === "ECONNABORTED" || code === "ETIMEDOUT") return "timeout";
  if (code === "ERR_NETWORK") return "offline";
  return undefined;
}

function retryAfterSeconds(response: AxiosLikeResponse | undefined): number | undefined {
  return positiveSeconds(response?.data?.retry_after) ?? positiveSeconds(retryAfterHeader(response?.headers));
}

function retryAfterHeader(headers: AxiosLikeResponse["headers"]): unknown {
  if (!headers) return undefined;
  return headers.get?.("retry-after") ?? headers["retry-after"];
}

function positiveSeconds(value: unknown): number | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  const seconds = Number(raw);
  if (Number.isFinite(seconds) && seconds > 0) return seconds;
  return undefined;
}

function rateLimitMessage(seconds: number | undefined): string {
  if (seconds == null) return "Too many requests. Wait a moment and try again.";
  if (seconds <= 90) return "Too many requests. Try again in a minute.";
  if (seconds < 3600) return `Too many requests. Try again in ${Math.ceil(seconds / 60)} minutes.`;
  if (seconds <= 5400) return "Too many requests. Try again in an hour.";
  return `Too many requests. Try again in ${Math.ceil(seconds / 3600)} hours.`;
}

// Date formatting — single canonical surface so the whole app shows
// consistent date/time strings. en-GB picks the "5 May 2026" form which works
// well next to both English and Russian UI chrome. Europe/Moscow matches
// lecture `start_time` and keeps SSR (UTC hosts) in lockstep with the browser.

const DATE_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "Europe/Moscow",
});

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Moscow",
});

const DATE_TIME_SHORT_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Moscow",
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

/** Bring the watch player back into view after a companion-tab click. */
export function scrollPlayerIntoView(): void {
  if (typeof document === "undefined") return;
  const el = document.getElementById("leap-watch-player");
  if (!el) return;
  const top = el.getBoundingClientRect().top;
  if (top >= 0 && top < window.innerHeight * 0.45) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}
