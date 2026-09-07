"use client";

import { cn } from "@/lib/utils";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import type { AnalyticsDateRange, DateRangePreset } from "@/lib/analytics-date-range";

export const STANDARD_DATE_PRESETS: { id: Exclude<DateRangePreset, "custom" | "alltime">; label: string }[] = [
  { id: "7d", label: "7 days" },
  { id: "28d", label: "28 days" },
  { id: "90d", label: "90 days" },
  { id: "month", label: "This month" },
];

export const USAGE_DATE_PRESETS: { id: Exclude<DateRangePreset, "custom">; label: string }[] = [
  ...STANDARD_DATE_PRESETS,
  { id: "alltime", label: "All time" },
];

const DEFAULT_PRESETS = STANDARD_DATE_PRESETS;

export function DateRangeFilter({
  range,
  preset,
  onRangeChange,
  onPresetChange,
  validationError,
  className,
  compact = false,
  presets = DEFAULT_PRESETS,
}: {
  range: AnalyticsDateRange;
  preset: DateRangePreset;
  onRangeChange: (range: AnalyticsDateRange) => void;
  onPresetChange: (preset: Exclude<DateRangePreset, "custom">) => void;
  validationError?: string | null;
  className?: string;
  /** Dashboard lens layout: presets row + compact date inputs. */
  compact?: boolean;
  presets?: readonly { id: Exclude<DateRangePreset, "custom">; label: string }[];
}) {
  return (
    <div className={cn("space-y-3", className)}>
      <div
        className={cn(
          "inline-flex w-full max-w-full flex-wrap gap-1 rounded-lg border border-border bg-muted/30 p-1 sm:w-auto",
          compact && "sm:max-w-none",
        )}
        role="group"
        aria-label="Quick date ranges"
      >
        {presets.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onPresetChange(p.id)}
            className={cn(
              "min-h-8 flex-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors sm:flex-none sm:px-3",
              preset === p.id
                ? "bg-card text-foreground shadow-sm ring-1 ring-border"
                : "text-muted-foreground hover:bg-card/60 hover:text-foreground",
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end sm:gap-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-end gap-2 sm:max-w-md">
          <div className="min-w-0 flex-1 space-y-1.5">
            <span className={FILTER_LABEL}>From</span>
            <input
              type="date"
              aria-label="From date"
              value={range.from}
              onChange={(e) => onRangeChange({ ...range, from: e.target.value })}
              className={cn(FILTER_CONTROL, "w-full min-w-0")}
            />
          </div>
          <span className="hidden pb-2.5 text-muted-foreground sm:inline" aria-hidden="true">
            —
          </span>
          <div className="min-w-0 flex-1 space-y-1.5">
            <span className={FILTER_LABEL}>To</span>
            <input
              type="date"
              aria-label="To date"
              value={range.to}
              onChange={(e) => onRangeChange({ ...range, to: e.target.value })}
              className={cn(FILTER_CONTROL, "w-full min-w-0")}
            />
          </div>
        </div>
        {preset === "custom" && (
          <p className="pb-0.5 text-xs text-muted-foreground sm:ml-auto">Custom range</p>
        )}
      </div>

      {validationError && (
        <p className="text-xs text-red-600" role="alert">
          {validationError}
        </p>
      )}
    </div>
  );
}
