const compactFormatter = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumSignificantDigits: 3,
});

/** Keep small values exact; abbreviate large dashboard metrics to fit narrow columns. */
export function formatCompactNumber(value: number): string {
  return Math.abs(value) >= 10_000 ? compactFormatter.format(value) : String(value);
}

export function formatViewCount(count: number): string {
  return `${formatCompactNumber(count)} ${count === 1 ? "view" : "views"}`;
}

export function formatExactViewCount(count: number): string {
  return `${count.toLocaleString("en")} ${count === 1 ? "view" : "views"}`;
}
