export const COUNT_FORMATTER = new Intl.NumberFormat("en-GB");

const MONTH_YEAR_FORMATTER = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" });

export function fmtNum(n: number | null | undefined, decimals = 0): string {
  if (n == null) return "∞";
  return decimals > 0 ? n.toFixed(decimals) : String(n);
}

export function formatMonthYear(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : MONTH_YEAR_FORMATTER.format(d);
}

/**
 * Transcribed time, sized to the magnitude. Real accounts reach six figures of
 * seconds, where a raw minute count ("18101 min") is unreadable.
 */
export function formatTotalDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 100) return `${hours} h ${minutes % 60} min`;
  return `${COUNT_FORMATTER.format(hours)} h`;
}

/** Count leaf fields that differ, so a collapsed section can show its own tally. */
export function countChanges(a: unknown, b: unknown): number {
  if (Object.is(a, b)) return 0;
  if (Array.isArray(a) || Array.isArray(b)) return JSON.stringify(a) === JSON.stringify(b) ? 0 : 1;
  if (a && b && typeof a === "object" && typeof b === "object") {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    let n = 0;
    for (const k of keys) {
      n += countChanges((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]);
    }
    return n;
  }
  return 1;
}

export function pick<T extends object, K extends keyof T>(o: T, keys: readonly K[]): Pick<T, K> {
  return Object.fromEntries(keys.map((k) => [k, o[k]])) as Pick<T, K>;
}
