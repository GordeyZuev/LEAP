/** Shared date-range helpers for product analytics (UTC calendar days, ISO strings). */

export const MAX_ANALYTICS_RANGE_DAYS = 366;

export type DateRangePreset = "7d" | "28d" | "90d" | "month" | "alltime" | "custom";

export interface AnalyticsDateRange {
  from: string;
  to: string;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function toIsoDate(d: Date): string {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

export function todayIso(): string {
  return toIsoDate(new Date());
}

export function addDaysIso(iso: string, delta: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return toIsoDate(d);
}

export function rangeSpanDays(from: string, to: string): number {
  const start = new Date(`${from}T00:00:00Z`).getTime();
  const end = new Date(`${to}T00:00:00Z`).getTime();
  return Math.floor((end - start) / 86_400_000) + 1;
}

export function allTimeRange(accountCreatedAt?: string): AnalyticsDateRange {
  const to = todayIso();
  let from = accountCreatedAt
    ? toIsoDate(new Date(accountCreatedAt))
    : addDaysIso(to, -(MAX_ANALYTICS_RANGE_DAYS - 1));
  if (from > to) from = to;
  if (rangeSpanDays(from, to) > MAX_ANALYTICS_RANGE_DAYS) {
    from = addDaysIso(to, -(MAX_ANALYTICS_RANGE_DAYS - 1));
  }
  return { from, to };
}

export function presetRange(
  preset: Exclude<DateRangePreset, "custom">,
  accountCreatedAt?: string,
): AnalyticsDateRange {
  const to = todayIso();
  if (preset === "alltime") return allTimeRange(accountCreatedAt);
  if (preset === "month") {
    const now = new Date();
    const from = `${now.getUTCFullYear()}-${pad(now.getUTCMonth() + 1)}-01`;
    return { from, to };
  }
  const days = preset === "7d" ? 7 : preset === "90d" ? 90 : 28;
  return { from: addDaysIso(to, -(days - 1)), to };
}

export function defaultAnalyticsRange(): AnalyticsDateRange {
  return presetRange("28d");
}

export function validateRange(from: string, to: string): string | null {
  if (!from || !to) return "Select both start and end dates.";
  if (from > to) return "Start date must be on or before end date.";
  if (rangeSpanDays(from, to) > MAX_ANALYTICS_RANGE_DAYS) {
    return `Date range must not exceed ${MAX_ANALYTICS_RANGE_DAYS} days.`;
  }
  return null;
}
