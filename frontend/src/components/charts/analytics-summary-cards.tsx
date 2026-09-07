"use client";

import { cn } from "@/lib/utils";

export interface SummaryCardItem {
  label: string;
  value: string;
  hint?: string;
}

export function AnalyticsSummaryCards({
  items,
  className,
}: {
  items: SummaryCardItem[];
  className?: string;
}) {
  const gridClass =
    items.length === 1
      ? "grid-cols-1"
      : items.length === 2
        ? "grid-cols-2"
        : items.length === 3
          ? "grid-cols-1 sm:grid-cols-3"
          : items.length === 4
            ? "grid-cols-2 lg:grid-cols-4"
            : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5";

  return (
    <div className={cn("grid gap-3", gridClass, className)}>
      {items.map((item) => (
        <div key={item.label} className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
          {item.hint && <p className="text-[10px] text-muted-foreground/80">{item.hint}</p>}
          <p className="mt-2 text-xl font-semibold tabular-nums text-foreground">{item.value}</p>
        </div>
      ))}
    </div>
  );
}
