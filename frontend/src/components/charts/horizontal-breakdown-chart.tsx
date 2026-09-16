"use client";

export interface BreakdownRow {
  label: string;
  value: number;
}

export function HorizontalBreakdownChart({ data }: { data: BreakdownRow[] }) {
  const max = Math.max(1, ...data.map((row) => row.value));

  return (
    <ul className="space-y-3">
      {data.map((row, index) => {
        const pct = Math.min(100, Math.round((row.value / max) * 100));
        return (
          <li key={`${row.label}-${index}`}>
            <div className="flex items-baseline justify-between gap-3">
              <p className="min-w-0 text-sm font-medium leading-snug text-pretty break-words text-foreground">
                {row.label}
              </p>
              <span className="shrink-0 tabular-nums text-sm text-muted-foreground">
                {row.value.toLocaleString()}
              </span>
            </div>
            <div
              className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted"
              role="meter"
              aria-valuemin={0}
              aria-valuemax={max}
              aria-valuenow={row.value}
              aria-label={row.label}
            >
              <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
