"use client";

import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { TABLE_HEAD_CELL } from "@/lib/table-classes";

export interface SortState {
  sortBy?: string;
  sortOrder?: "asc" | "desc";
  /** Same field flips direction; a new field starts at the caller's default. */
  onSort?: (field: string) => void;
}

interface SortableThProps extends SortState {
  label: string;
  /** API sort field. Omit for columns the API cannot sort by. */
  field?: string;
  className?: string;
  /**
   * Pins the header while rows scroll under it. Requires the wrapping card to
   * stop being a scroll container at wide sizes — `TABLE_CARD` does that. Turn
   * off only for a table whose wrapper clips overflow.
   */
  sticky?: boolean;
}

/**
 * Table header cell that doubles as a sort control when the column maps to an
 * API sort field. Renders plain text otherwise, so a column can never claim to
 * be sortable when the backend would ignore it.
 */
export function SortableTh({
  label,
  field,
  className,
  sortBy,
  sortOrder,
  onSort,
  sticky = true,
}: SortableThProps) {
  const sortable = !!field && !!onSort;
  const active = sortable && sortBy === field;
  const Arrow = active ? (sortOrder === "asc" ? ArrowUp : ArrowDown) : ChevronsUpDown;

  return (
    <th
      className={cn(
        TABLE_HEAD_CELL,
        "whitespace-nowrap text-left",
        // A sticky cell needs its own opaque background: rows pass underneath.
        sticky && "sticky top-0 z-10 bg-muted first:rounded-tl-2xl last:rounded-tr-2xl",
        className,
      )}
      aria-sort={active ? (sortOrder === "asc" ? "ascending" : "descending") : undefined}
    >
      {sortable ? (
        <button
          type="button"
          onClick={() => onSort(field)}
          className={cn(
            // Tailwind preflight resets `text-transform` on buttons, so the
            // uppercase inherited from the cell has to be restated here.
            "group flex items-center gap-1 rounded uppercase tracking-wide transition-colors hover:text-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
            active && "text-primary",
          )}
        >
          {label}
          <Arrow
            size={11}
            className={cn(
              "shrink-0 transition-opacity",
              active ? "opacity-100" : "opacity-0 group-hover:opacity-60",
            )}
          />
        </button>
      ) : (
        label
      )}
    </th>
  );
}
