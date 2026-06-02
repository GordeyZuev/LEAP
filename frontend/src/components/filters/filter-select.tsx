"use client";

import { useEffect, useRef, useState } from "react";
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
}

export function FilterSelect<V extends string | number = string>({
  value,
  options,
  onChange,
  className,
}: FilterSelectProps<V>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          FILTER_CONTROL,
          "flex w-full items-center justify-between gap-2 text-left font-medium text-gray-700"
        )}
      >
        <span className="truncate">{selected?.label ?? "—"}</span>
        <ChevronDown
          size={16}
          className={cn("shrink-0 opacity-60 transition-transform duration-150", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-[50] mt-1.5 w-[min(100vw-2rem,17rem)] overflow-auto rounded-2xl border border-[#D9D9D9] bg-white p-2 shadow-xl">
          {options.map((opt) => (
            <button
              key={String(opt.value)}
              type="button"
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
        </div>
      )}
    </div>
  );
}
