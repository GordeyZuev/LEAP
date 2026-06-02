"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  value: V[];
  options: FilterMultiSelectOption<V>[];
  /** Called once with the final selection when the dropdown closes (if changed). */
  onChange: (next: V[]) => void;
}

function sameSet<V>(a: V[], b: V[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  return b.every((x) => s.has(x));
}

/**
 * Multi-select that commits **on close**, not per checkbox — so instant-apply
 * pages fire a single request per edit session instead of one per toggle. While
 * open it tracks a local `pending` selection (seeded from `value`); closing it
 * (outside click or trigger) commits `pending` via `onChange` when it differs.
 */
export function FilterMultiSelect<V extends string | number = number>({
  label,
  emptySummary,
  value,
  options,
  onChange,
}: FilterMultiSelectProps<V>) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<V[]>(value);
  const ref = useRef<HTMLDivElement>(null);

  // Commit the pending selection (only if it actually changed).
  const commit = useCallback(
    (sel: V[]) => {
      if (!sameSet(sel, value)) onChange(sel);
    },
    [value, onChange],
  );

  function toggleOpen() {
    if (open) {
      setOpen(false);
      commit(pending);
    } else {
      setPending(value);
      setOpen(true);
    }
  }

  // Re-subscribe whenever `pending` changes so the handler always commits the
  // latest selection — avoids stale refs without reading refs during render.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        commit(pending);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open, pending, commit]);

  const display = open ? pending : value;
  const n = display.length;
  const selectedSet = new Set(pending);

  return (
    <div ref={ref} className="relative">
      <span className={FILTER_LABEL}>{label}</span>
      <button
        type="button"
        onClick={toggleOpen}
        className={cn(
          FILTER_CONTROL,
          "flex w-full items-center justify-between gap-2 text-left font-medium",
          n > 0 ? "border-[#224C87] bg-[#224C87]/10 text-[#224C87]" : "text-gray-700"
        )}
      >
        <span className="truncate">{n === 0 ? emptySummary : `${n} selected`}</span>
        <ChevronDown size={16} className={cn("shrink-0 opacity-60 transition-transform", open && "rotate-180")} />
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
                  onChange={() =>
                    setPending((cur) =>
                      cur.includes(opt.value) ? cur.filter((x) => x !== opt.value) : [...cur, opt.value]
                    )
                  }
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
