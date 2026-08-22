"use client";

import { type ReactNode } from "react";
import { FILTER_TOOLBAR, FILTER_BAR_CONTROL } from "@/lib/filter-field-classes";

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
 * Shared toolbar shell for every list page: search + filter controls + sort on
 * one wrapping row (no detached Apply row), with optional advanced and chips
 * underneath. Sits flat on the page — the list table is the primary card.
 */
export function FilterBar({ search, controls = [], sort, onClearAll, advanced, chips }: FilterBarProps) {
  const hasRow = Boolean(search || controls.length > 0 || sort || onClearAll);
  return (
    <div className={FILTER_TOOLBAR}>
      {hasRow && (
        <div className="flex flex-wrap items-end gap-x-4 gap-y-4">
          {search && <div className="min-w-[15rem] flex-[2] basis-[12rem]">{search}</div>}
          {controls.map((c, i) => (
            <div key={i} className={FILTER_BAR_CONTROL}>
              {c}
            </div>
          ))}
          {(sort || onClearAll) && (
            <div className="ml-auto flex min-w-0 flex-wrap items-end gap-3">
              {sort && <div className="min-w-[13rem]">{sort}</div>}
              {onClearAll && (
                <button
                  type="button"
                  onClick={onClearAll}
                  className="inline-flex min-h-[2.875rem] items-center text-xs font-medium text-muted-foreground transition-colors hover:text-secondary-foreground"
                >
                  Clear all
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {advanced && <div className="border-t border-border pt-4">{advanced}</div>}
      {chips}
    </div>
  );
}
