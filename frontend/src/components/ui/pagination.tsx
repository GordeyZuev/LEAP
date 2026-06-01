"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface PaginationProps {
  page: number;
  totalPages: number;
  total: number;
  perPage: number;
  onPageChange: (page: number) => void;
  itemLabel?: string;
  className?: string;
}

const BTN_BASE =
  "inline-flex h-9 w-9 items-center justify-center rounded-xl border border-[#D9D9D9] bg-white text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-white disabled:hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#224C87]/30";

export function Pagination({
  page,
  totalPages,
  total,
  perPage,
  onPageChange,
  itemLabel = "item",
  className,
}: PaginationProps) {
  const [inputValue, setInputValue] = useState(String(page));
  const [prevPage, setPrevPage] = useState(page);
  const inputRef = useRef<HTMLInputElement>(null);

  // Re-sync input when the page prop changes externally (URL nav, reset, etc.).
  if (page !== prevPage) {
    setPrevPage(page);
    setInputValue(String(page));
  }

  if (total === 0) return null;

  // Clamp for display so an out-of-range page (e.g. after deletes) still renders
  // a sane "Showing X–Y of N" range. Prev/Next targets are also clamped so the
  // user can recover with a single click instead of stepping through nothing.
  const effPage = Math.min(Math.max(1, page), Math.max(1, totalPages));
  const from = (effPage - 1) * perPage + 1;
  const to = Math.min(effPage * perPage, total);
  const hasPrev = effPage > 1;
  const hasNext = effPage < totalPages;
  const pluralLabel = total !== 1 ? `${itemLabel}s` : itemLabel;

  function commitInput() {
    const raw = inputValue.trim();
    const parsed = parseInt(raw, 10);
    if (Number.isNaN(parsed) || parsed < 1) {
      setInputValue(String(page));
      return;
    }
    const clamped = Math.min(Math.max(1, parsed), totalPages);
    if (clamped !== page) {
      onPageChange(clamped);
    } else {
      setInputValue(String(page));
    }
  }

  return (
    <div
      className={cn(
        "mt-6 flex flex-wrap items-center justify-between gap-3 text-sm text-gray-600",
        className,
      )}
    >
      <p className="tabular-nums">
        Showing{" "}
        <span className="font-semibold text-gray-900">
          {from.toLocaleString()}–{to.toLocaleString()}
        </span>{" "}
        of <span className="font-semibold text-gray-900">{total.toLocaleString()}</span> {pluralLabel}
      </p>

      <div className="flex items-center gap-1.5">
        <button
          type="button"
          aria-label="First page"
          title="First page"
          disabled={!hasPrev}
          onClick={() => onPageChange(1)}
          className={BTN_BASE}
        >
          <ChevronsLeft size={16} />
        </button>
        <button
          type="button"
          aria-label="Previous page"
          title="Previous page"
          disabled={!hasPrev}
          onClick={() => onPageChange(effPage - 1)}
          className={BTN_BASE}
        >
          <ChevronLeft size={16} />
        </button>

        <div className="mx-1 flex items-center gap-2 tabular-nums">
          <span className="text-gray-500">Page</span>
          <input
            ref={inputRef}
            type="text"
            inputMode="numeric"
            value={inputValue}
            aria-label="Go to page"
            onChange={(e) => setInputValue(e.target.value.replace(/[^\d]/g, ""))}
            onBlur={commitInput}
            onFocus={(e) => e.currentTarget.select()}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commitInput();
                inputRef.current?.blur();
              } else if (e.key === "Escape") {
                e.preventDefault();
                setInputValue(String(page));
                inputRef.current?.blur();
              }
            }}
            className="h-9 w-14 rounded-xl border border-[#D9D9D9] bg-white px-2 text-center font-semibold text-gray-900 outline-none transition-colors focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/20"
          />
          <span className="text-gray-500">of</span>
          <span className="font-semibold text-gray-900">{totalPages.toLocaleString()}</span>
        </div>

        <button
          type="button"
          aria-label="Next page"
          title="Next page"
          disabled={!hasNext}
          onClick={() => onPageChange(effPage + 1)}
          className={BTN_BASE}
        >
          <ChevronRight size={16} />
        </button>
        <button
          type="button"
          aria-label="Last page"
          title="Last page"
          disabled={!hasNext}
          onClick={() => onPageChange(totalPages)}
          className={BTN_BASE}
        >
          <ChevronsRight size={16} />
        </button>
      </div>
    </div>
  );
}
