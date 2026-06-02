"use client";

import { cn } from "@/lib/utils";
import {
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
} from "@/lib/filter-field-classes";

export interface SegmentedOption<V extends string | number> {
  value: V;
  label: string;
}

/** The common active/inactive tri-state used by most list pages. */
export type ActiveStatus = "all" | "active" | "inactive";
export const ACTIVE_STATUS_OPTIONS: SegmentedOption<ActiveStatus>[] = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
];

interface SegmentedFilterProps<V extends string | number> {
  label: string;
  value: V;
  options: SegmentedOption<V>[];
  onChange: (value: V) => void;
}

/** Inline segmented toggle group (e.g. All / Active / Inactive). Applies instantly. */
export function SegmentedFilter<V extends string | number>({
  label,
  value,
  options,
  onChange,
}: SegmentedFilterProps<V>) {
  return (
    <div>
      <span className={FILTER_LABEL}>{label}</span>
      <div className={FILTER_SEGMENT_WRAP}>
        {options.map((o) => (
          <button
            key={String(o.value)}
            type="button"
            className={cn(FILTER_SEGMENT_BTN, value === o.value ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
