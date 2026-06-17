"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";

export interface FilterSelectOption<V extends string | number = string> {
  value: V;
  label: string;
}

interface FilterSelectProps<V extends string | number = string> {
  value: V;
  options: FilterSelectOption<V>[];
  onChange: (value: V) => void;
  className?: string;
  disabled?: boolean;
}

export function FilterSelect<V extends string | number = string>({
  value,
  options,
  onChange,
  className,
  disabled = false,
}: FilterSelectProps<V>) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  // Dropdown is portalled to <body> with fixed positioning so it never gets
  // clipped by a scrollable parent (modals, overflow containers).
  const [coords, setCoords] = useState<{ top: number; left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    setCoords({ top: r.bottom + 6, left: r.left, width: r.width });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = panelRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    el?.scrollIntoView({ block: "nearest" });
  }, [open, coords]);

  useEffect(() => {
    if (!open) return;
    function close() { setOpen(false); }
    function onMouseDown(e: MouseEvent) {
      if (triggerRef.current && !triggerRef.current.contains(e.target as Node)) {
        // Clicks inside the portalled panel are handled by the option buttons
        // (which close on select); any other click closes the menu.
        const panel = document.getElementById("filter-select-panel");
        if (!panel || !panel.contains(e.target as Node)) close();
      }
    }
    document.addEventListener("mousedown", onMouseDown);
    // Reposition is non-trivial across nested scrollers — closing on scroll is
    // the simplest correct behavior.
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  const selected = options.find((o) => o.value === value);

  return (
    <div className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          FILTER_CONTROL,
          "flex w-full items-center justify-between gap-2 text-left font-medium text-gray-700",
          disabled && "cursor-not-allowed opacity-50"
        )}
      >
        <span className="truncate">{selected?.label ?? "—"}</span>
        <ChevronDown
          size={16}
          className={cn("shrink-0 opacity-60 transition-transform duration-150", open && "rotate-180")}
        />
      </button>

      {open && coords && createPortal(
        <div
          ref={panelRef}
          style={{ position: "fixed", top: coords.top, left: coords.left, width: Math.max(coords.width, 176) }}
          className="z-[100] max-h-72 overflow-auto rounded-2xl border border-[#D9D9D9] bg-white p-2 shadow-xl"
        >
          {options.map((opt) => (
            <button
              key={String(opt.value)}
              type="button"
              data-active={opt.value === value ? "true" : undefined}
              onClick={() => { onChange(opt.value); setOpen(false); }}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm",
                opt.value === value
                  ? "bg-[#EBF0F8] text-[#224C87] font-medium"
                  : "text-gray-700 hover:bg-gray-50"
              )}
            >
              <span className="flex-1 truncate text-left">{opt.label}</span>
              {opt.value === value && <Check size={14} className="shrink-0" />}
            </button>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}
