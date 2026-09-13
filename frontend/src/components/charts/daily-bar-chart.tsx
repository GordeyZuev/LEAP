"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
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
  xAxisMinTickGap,
  yAxisWidth,
} from "@/components/charts/chart-axis";
import {
  formatBucketDate,
  prepareDailyChartSeries,
  type ChartGranularity,
} from "@/lib/chart-bucketing";

export { formatChartDate } from "@/lib/chart-bucketing";

export interface DailyChartPoint {
  date: string;
  value: number;
}

function ChartTooltipBucketed({
  active,
  payload,
  label,
  valueLabel,
  granularity,
}: {
  active?: boolean;
  payload?: { value?: number }[];
  label?: string;
  valueLabel: string;
  granularity: ChartGranularity;
}) {
  if (!active || !payload?.length || !label) return null;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-foreground">{formatBucketDate(String(label), granularity)}</p>
      <p className="mt-0.5 tabular-nums text-muted-foreground">
        {valueLabel}: <span className="font-semibold text-foreground">{payload[0]?.value ?? 0}</span>
      </p>
    </div>
  );
}

export function DailyBarChart({
  data,
  valueLabel,
  color = "var(--primary)",
  height = 192,
}: {
  data: DailyChartPoint[];
  valueLabel: string;
  color?: string;
  height?: number;
}) {
  const { data: chartData, granularity } = prepareDailyChartSeries(data);
  const yTicks = integerYTicks(Math.max(0, ...chartData.map((point) => point.value)));
  const yMax = yTicks[yTicks.length - 1] ?? 1;

  return (
    <div className="w-full min-w-0" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={chartData} margin={CHART_MARGIN}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
          <XAxis
            dataKey="date"
            tickFormatter={(iso) => formatBucketDate(iso, granularity)}
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
            content={<ChartTooltipBucketed valueLabel={valueLabel} granularity={granularity} />}
          />
          <Bar
            dataKey="value"
            fill={color}
            radius={[4, 4, 0, 0]}
            maxBarSize={chartData.length > 24 ? 20 : 32}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
