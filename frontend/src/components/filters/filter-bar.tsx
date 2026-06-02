"use client";

import { type ReactNode } from "react";
import { FILTER_CARD } from "@/lib/filter-field-classes";

interface FilterBarProps {
  /** Search field (left, grows). */
  search?: ReactNode;
  /** Filter controls — each is wrapped with uniform sizing and wraps responsively. */
  controls?: ReactNode[];
  /** Sort control (right of the controls). */
  sort?: ReactNode;
  /** When provided, renders a "Clear all" action at the end of the row. */
  onClearAll?: () => void;
  /** Optional collapsible advanced section, below the main row. */
  advanced?: ReactNode;
  /** Optional active-filter chips, below everything. */
  chips?: ReactNode;
}

/**
 * Shared toolbar shell for every list page: one card holding search + filter
 * controls + sort + "Clear all" on a single wrapping row (no detached Apply
 * row), with optional advanced and chips slots underneath.
 */
export function FilterBar({ search, controls = [], sort, onClearAll, advanced, chips }: FilterBarProps) {
  const hasRow = Boolean(search || controls.length > 0 || sort || onClearAll);
  return (
    <div className={FILTER_CARD}>
      {hasRow && (
        <div className="flex flex-wrap items-end gap-3">
          {search && <div className="min-w-[15rem] flex-[2]">{search}</div>}
          {controls.map((c, i) => (
            <div key={i} className="min-w-[11rem] flex-1">{c}</div>
          ))}
          {sort && <div className="min-w-[13rem] flex-1">{sort}</div>}
          {onClearAll && (
            <button
              type="button"
              onClick={onClearAll}
              className="ml-auto inline-flex min-h-[2.875rem] items-center text-xs font-medium text-gray-400 transition-colors hover:text-gray-600"
            >
              Clear all
            </button>
          )}
        </div>
      )}
      {advanced && <div className="border-t border-gray-100 pt-4">{advanced}</div>}
      {chips}
    </div>
  );
}
