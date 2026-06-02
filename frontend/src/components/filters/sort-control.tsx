"use client";

import { cn } from "@/lib/utils";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { FilterSelect, type FilterSelectOption } from "./filter-select";

interface SortControlProps {
  value: string;
  order: "asc" | "desc";
  options: FilterSelectOption[];
  onChange: (field: string) => void;
  onToggleOrder: () => void;
  label?: string;
}

/** Sort field dropdown + asc/desc toggle — shared by every list page. */
export function SortControl({
  value,
  order,
  options,
  onChange,
  onToggleOrder,
  label = "Sort by",
}: SortControlProps) {
  return (
    <div className="min-w-0">
      <span className={FILTER_LABEL}>{label}</span>
      <div className="flex gap-1.5">
        <FilterSelect
          value={value}
          options={options}
          onChange={(v) => onChange(v as string)}
          className="flex-1 min-w-0"
        />
        <button
          type="button"
          title={order === "desc" ? "Descending" : "Ascending"}
          aria-label={order === "desc" ? "Sort descending" : "Sort ascending"}
          onClick={onToggleOrder}
          className={cn(FILTER_CONTROL, "w-11 shrink-0 px-0 text-center font-mono")}
        >
          {order === "desc" ? "↓" : "↑"}
        </button>
      </div>
    </div>
  );
}
