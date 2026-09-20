const compactFormatter = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumSignificantDigits: 3,
});

/** Keep small values exact; abbreviate large dashboard metrics to fit narrow columns. */
export function formatCompactNumber(value: number): string {
  return Math.abs(value) >= 10_000 ? compactFormatter.format(value) : String(value);
}
