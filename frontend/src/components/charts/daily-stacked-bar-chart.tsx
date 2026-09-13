"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  CHART_MARGIN,
  CHART_TICK_STYLE,
  CHART_X_PADDING,
  integerYTicks,
  maxStackedValue,
  xAxisMinTickGap,
  yAxisWidth,
} from "@/components/charts/chart-axis";
import { formatBucketDate, prepareStackedChartSeries } from "@/lib/chart-bucketing";

const SERIES_OPACITY = [1, 0.78, 0.58, 0.42, 0.32, 0.24];

export interface DailyStackedRow {
  date: string;
  [platform: string]: string | number;
}

function StackedTooltip({
  active,
  payload,
  label,
  tickFormatter,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number; color?: string }[];
  label?: string;
  tickFormatter: (iso: string) => string;
}) {
  if (!active || !payload?.length || !label) return null;
  const rows = payload.filter((p) => (p.value ?? 0) > 0);
  if (rows.length === 0) return null;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
      <p className="mb-1.5 font-medium text-foreground">{tickFormatter(String(label))}</p>
      <ul className="space-y-0.5">
        {rows.map((row) => (
          <li key={row.name} className="flex items-center justify-between gap-4 tabular-nums">
            <span className="text-muted-foreground">{row.name}</span>
            <span className="font-semibold text-foreground">{row.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DailyStackedBarChart({
  data,
  seriesKeys,
  height = 192,
}: {
  data: DailyStackedRow[];
  seriesKeys: string[];
  height?: number;
}) {
  const { data: chartData, granularity } = prepareStackedChartSeries(data, seriesKeys);
  const tickFormatter = (iso: string) => formatBucketDate(iso, granularity);
  const yTicks = integerYTicks(maxStackedValue(chartData, seriesKeys));
  const yMax = yTicks[yTicks.length - 1] ?? 1;

  return (
    <div className="w-full min-w-0" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <BarChart data={chartData} margin={{ ...CHART_MARGIN, bottom: 12 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
        <XAxis
          dataKey="date"
          tickFormatter={tickFormatter}
          tick={CHART_TICK_STYLE}
          axisLine={false}
          tickLine={false}
          minTickGap={xAxisMinTickGap(granularity)}
          tickMargin={8}
          interval="preserveStartEnd"
          padding={CHART_X_PADDING}
        />
        <YAxis
          tick={CHART_TICK_STYLE}
          axisLine={false}
          tickLine={false}
          width={yAxisWidth(yTicks)}
          tickMargin={8}
          allowDecimals={false}
          interval={0}
          ticks={yTicks}
          domain={[0, yMax]}
        />
        <Tooltip
          cursor={{ fill: "var(--muted)", opacity: 0.35 }}
          content={<StackedTooltip tickFormatter={tickFormatter} />}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {seriesKeys.map((key, i) => (
          <Bar
            key={key}
            dataKey={key}
            stackId="a"
            fill="var(--primary)"
            fillOpacity={SERIES_OPACITY[i % SERIES_OPACITY.length]}
            radius={i === seriesKeys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
            maxBarSize={chartData.length > 24 ? 20 : 32}
          />
        ))}
      </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
