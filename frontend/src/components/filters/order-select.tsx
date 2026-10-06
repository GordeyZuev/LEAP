"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";
import { FILTER_LABEL } from "@/lib/filter-field-classes";
import { FilterSelect, type FilterSelectOption } from "./filter-select";

export function isSavedSort<S extends string>(saved: readonly S[], value: string): value is S {
  return (saved as readonly string[]).includes(value);
}

/**
 * Rules the server can keep, plus Custom order (keep the current sequence, no rule).
 * Views, counts and durations drift on their own, so they stay a view-only Sort by.
 */
export function ownerOrderOptions<V extends string>(
  options: readonly FilterSelectOption<V>[],
  saved: readonly string[],
): FilterSelectOption<V>[] {
  return options
    .filter((o) => o.value === "order" || isSavedSort(saved, o.value))
    .map((o) => (o.value === "order" ? { ...o, label: "Custom order" } : o));
}

/** Writes saved membership order. Public catalogs use view-only Sort by. */
export function OrderSelect<V extends string>({
  label = "Order",
  value,
  options,
  onChange,
  disabled,
  compact = false,
  hideLabel = false,
  className,
}: {
  label?: string;
  value: V;
  options: FilterSelectOption<V>[];
  onChange: (value: V) => void;
  disabled?: boolean;
  compact?: boolean;
  hideLabel?: boolean;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn("min-w-0", className)}>
      {hideLabel ? null : (
        <label htmlFor={id} className={FILTER_LABEL}>
          {label}
        </label>
      )}
      <FilterSelect
        id={id}
        value={value}
        options={options}
        onChange={onChange}
        disabled={disabled}
        compact={compact}
        ariaLabel={hideLabel ? label : undefined}
        filled={value !== "order"}
      />
    </div>
  );
}
