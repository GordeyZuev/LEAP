"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";

export interface SummaryCardItem {
  label: string;
  value: string;
  /** Exact value when the visible metric is abbreviated. */
  valueTitle?: string;
  hint?: string;
  href?: string;
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
      {items.map((item) => {
        const shell = "flex min-w-0 flex-col rounded-xl border border-border bg-card px-4 py-3";
        const content = (
          <>
            <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
            {item.hint && <p className="text-[10px] text-muted-foreground/80">{item.hint}</p>}
            <p title={item.valueTitle} className="mt-auto pt-2 text-xl font-semibold tabular-nums text-foreground">
              <span aria-hidden={item.valueTitle ? true : undefined}>{item.value}</span>
              {item.valueTitle && <span className="sr-only">{item.valueTitle}</span>}
            </p>
          </>
        );
        return item.href ? (
          <Link key={item.label} href={item.href}
            className={cn(shell, "pressable transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30")}>
            {content}
          </Link>
        ) : <div key={item.label} className={shell}>{content}</div>;
      })}
    </div>
  );
}
