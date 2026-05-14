"use client";

import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";

export interface FilterMultiSelectOption<V extends string | number = number> {
  value: V;
  label: string;
}

interface FilterMultiSelectProps<V extends string | number = number> {
  label: string;
  emptySummary: string;
  selectedIds: V[];
  options: FilterMultiSelectOption<V>[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onToggle: (id: V) => void;
}

export function FilterMultiSelect<V extends string | number = number>({
  label,
  emptySummary,
  selectedIds,
  options,
  open,
  onOpenChange,
  onToggle,
}: FilterMultiSelectProps<V>) {
  const n = selectedIds.length;
  const selectedSet = new Set(selectedIds);

  return (
    <div className="relative">
      <span className={FILTER_LABEL}>{label}</span>
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className={cn(
          FILTER_CONTROL,
          "flex min-h-[2.5rem] w-full items-center justify-between gap-2 text-left font-medium",
          n > 0 ? "border-[#224C87] bg-[#224C87]/10 text-[#224C87]" : "text-gray-700"
        )}
      >
        <span className="truncate">{n === 0 ? emptySummary : `${n} selected`}</span>
        <ChevronDown size={16} className="shrink-0 opacity-60" />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-[50] mt-1.5 max-h-[min(22rem,70vh)] w-[min(100vw-2rem,17rem)] overflow-auto rounded-2xl border border-[#D9D9D9] bg-white p-2 shadow-xl">
          {options.length === 0 ? (
            <p className="px-3 py-4 text-center text-xs text-gray-400">No options available</p>
          ) : (
            options.map((opt) => (
              <label
                key={String(opt.value)}
                className="flex cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2 text-sm hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  checked={selectedSet.has(opt.value)}
                  onChange={() => onToggle(opt.value)}
                  className="rounded accent-[#224C87]"
                />
                <span className="truncate">{opt.label}</span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  );
}
