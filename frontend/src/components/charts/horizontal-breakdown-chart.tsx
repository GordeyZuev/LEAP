"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_TICK_STYLE, integerYTicks } from "@/components/charts/chart-axis";

export interface BreakdownRow {
  label: string;
  value: number;
}

function BreakdownTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload?: BreakdownRow }[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-foreground">{row.label}</p>
      <p className="mt-0.5 tabular-nums text-muted-foreground">
        Count: <span className="font-semibold text-foreground">{row.value}</span>
      </p>
    </div>
  );
}

export function HorizontalBreakdownChart({
  data,
  height = Math.max(120, data.length * 36),
}: {
  data: BreakdownRow[];
  height?: number;
}) {
  const labelWidth = Math.min(160, Math.max(96, ...data.map((d) => d.label.length * 7)));
  const xTicks = integerYTicks(Math.max(0, ...data.map((row) => row.value)));
  const xMax = xTicks[xTicks.length - 1] ?? 1;

  return (
    <div className="w-full min-w-0" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 28, left: 4, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border/60" />
        <XAxis
          type="number"
          allowDecimals={false}
          tick={CHART_TICK_STYLE}
          interval={0}
          ticks={xTicks}
          domain={[0, xMax]}
          tickMargin={8}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={labelWidth}
          tick={CHART_TICK_STYLE}
          axisLine={false}
          tickLine={false}
          interval={0}
        />
        <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.35 }} content={<BreakdownTooltip />} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={20}>
          {data.map((_, i) => (
            <Cell key={i} fill="var(--primary)" fillOpacity={0.85 - i * 0.05} />
          ))}
        </Bar>
      </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
