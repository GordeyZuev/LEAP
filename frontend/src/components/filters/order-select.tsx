"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";
import { FILTER_LABEL } from "@/lib/filter-field-classes";
import { FilterSelect, type FilterSelectOption } from "./filter-select";

export function ownerOrderOptions<V extends string>(
  options: readonly FilterSelectOption<V>[],
): FilterSelectOption<V>[] {
  return options.map((o) => (o.value === "order" ? { ...o, label: "Current order" } : o));
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
