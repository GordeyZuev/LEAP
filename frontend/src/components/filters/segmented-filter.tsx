"use client";

import { SegmentedField, type SegmentedOption } from "@/components/ui/segmented-field";

export type { SegmentedOption };

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
  labelHidden?: boolean;
}

/**
 * Inline segmented toggle group for filter toolbars (e.g. All / Active /
 * Inactive). Applies instantly.
 *
 * Kept as its own name because the filter toolbars read better with it, but the
 * markup and the radio-group semantics live in one place — see SegmentedField.
 */
export function SegmentedFilter<V extends string | number>(props: SegmentedFilterProps<V>) {
  return <SegmentedField {...props} />;
}
