/** Room so the top Y tick stays on the grid and the last date is not clipped. */
export const CHART_MARGIN = { top: 12, right: 28, left: 4, bottom: 8 };

export const CHART_TICK_STYLE = {
  fontSize: 10,
  fill: "var(--muted-foreground)",
};

export const CHART_X_PADDING = { left: 10, right: 18 };

/**
 * Integer Y ticks from 0, without Recharts rounding 5 → 8 (empty headroom that
 * then clips or hides the top label).
 */
export function integerYTicks(maxValue: number, maxTickCount = 6): number[] {
  if (!Number.isFinite(maxValue) || maxValue <= 0) return [0, 1];
  const max = Math.max(1, Math.ceil(maxValue));
  if (max <= maxTickCount - 1) {
    return Array.from({ length: max + 1 }, (_, i) => i);
  }
  const rawStep = max / (maxTickCount - 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const niceResidual = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  const step = niceResidual * magnitude;
  const niceMax = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= niceMax + step / 2; value += step) {
    ticks.push(Number(value.toFixed(10)));
  }
  return ticks;
}

export function yAxisWidth(ticks: number[]): number {
  const digits = Math.max(1, ...ticks.map((tick) => String(Math.round(tick)).length));
  return Math.max(40, 14 + digits * 8);
}

export function xAxisMinTickGap(granularity: "day" | "week" | "month"): number {
  if (granularity === "week") return 88;
  if (granularity === "month") return 64;
  return 56;
}

export function maxStackedValue(
  rows: Array<Record<string, string | number>>,
  seriesKeys: string[],
): number {
  if (rows.length === 0) return 0;
  return Math.max(
    0,
    ...rows.map((row) => seriesKeys.reduce((sum, key) => sum + Number(row[key] ?? 0), 0)),
  );
}
