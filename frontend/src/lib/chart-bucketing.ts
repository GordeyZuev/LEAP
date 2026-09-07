import type { DailyChartPoint } from "@/components/charts/daily-bar-chart";
import type { DailyStackedRow } from "@/components/charts/daily-stacked-bar-chart";
import { rangeSpanDays, toIsoDate } from "@/lib/analytics-date-range";

const CHART_DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

export function formatChartDate(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return CHART_DATE.format(date);
}

export type ChartGranularity = "day" | "week" | "month";

/** Daily bars up to 45d; weekly to 120d; monthly beyond that. */
export function chooseChartGranularity(dayCount: number): ChartGranularity {
  if (dayCount <= 45) return "day";
  if (dayCount <= 120) return "week";
  return "month";
}

export function granularityPeriodLabel(granularity: ChartGranularity): string {
  if (granularity === "day") return "day";
  if (granularity === "week") return "week";
  return "month";
}

export function dayCountFromSeries(data: { date: string }[]): number {
  if (data.length === 0) return 0;
  if (data.length === 1) return 1;
  return rangeSpanDays(data[0].date, data[data.length - 1].date);
}

function weekStartIso(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  const weekday = d.getUTCDay();
  const toMonday = weekday === 0 ? -6 : 1 - weekday;
  d.setUTCDate(d.getUTCDate() + toMonday);
  return toIsoDate(d);
}

function monthStartIso(iso: string): string {
  return `${iso.slice(0, 7)}-01`;
}

function bucketKey(iso: string, granularity: ChartGranularity): string {
  if (granularity === "week") return weekStartIso(iso);
  if (granularity === "month") return monthStartIso(iso);
  return iso;
}

export function formatBucketDate(isoDate: string, granularity: ChartGranularity): string {
  if (granularity === "day") return formatChartDate(isoDate);
  if (granularity === "week") return `w/c ${formatChartDate(isoDate)}`;
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" }).format(date);
}

export function bucketDailyPoints(
  data: DailyChartPoint[],
  granularity: ChartGranularity,
): DailyChartPoint[] {
  if (granularity === "day" || data.length === 0) return data;

  const buckets = new Map<string, number>();
  for (const point of data) {
    const key = bucketKey(point.date, granularity);
    buckets.set(key, (buckets.get(key) ?? 0) + point.value);
  }

  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, value]) => ({ date, value }));
}

export function bucketStackedRows(
  data: DailyStackedRow[],
  seriesKeys: string[],
  granularity: ChartGranularity,
): DailyStackedRow[] {
  if (granularity === "day" || data.length === 0) return data;

  const buckets = new Map<string, DailyStackedRow>();

  for (const row of data) {
    const key = bucketKey(row.date, granularity);
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = { date: key };
      for (const seriesKey of seriesKeys) bucket[seriesKey] = 0;
      buckets.set(key, bucket);
    }
    for (const seriesKey of seriesKeys) {
      bucket[seriesKey] = Number(bucket[seriesKey] ?? 0) + Number(row[seriesKey] ?? 0);
    }
  }

  return [...buckets.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function prepareDailyChartSeries(data: DailyChartPoint[]): {
  data: DailyChartPoint[];
  granularity: ChartGranularity;
  periodLabel: string;
} {
  const granularity = chooseChartGranularity(dayCountFromSeries(data));
  return {
    data: bucketDailyPoints(data, granularity),
    granularity,
    periodLabel: granularityPeriodLabel(granularity),
  };
}

export function prepareStackedChartSeries(
  data: DailyStackedRow[],
  seriesKeys: string[],
): {
  data: DailyStackedRow[];
  granularity: ChartGranularity;
  periodLabel: string;
} {
  const granularity = chooseChartGranularity(dayCountFromSeries(data));
  return {
    data: bucketStackedRows(data, seriesKeys, granularity),
    granularity,
    periodLabel: granularityPeriodLabel(granularity),
  };
}
