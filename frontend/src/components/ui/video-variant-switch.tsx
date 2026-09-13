"use client";

import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "processed" as const, label: "Edited" },
  { value: "original" as const, label: "Original" },
];

/** Quiet version switch under the title — not a filter-sized segmented control. */
export function VideoVariantSwitch({
  value,
  onChange,
  className,
}: {
  value: "processed" | "original";
  onChange: (value: "processed" | "original") => void;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Video version"
      className={cn("flex flex-wrap items-center gap-x-2 text-sm", className)}
    >
      {OPTIONS.map((opt, i) => {
        const selected = value === opt.value;
        return (
          <span key={opt.value} className="flex items-center gap-x-2">
            {i > 0 && (
              <span aria-hidden="true" className="text-border">
                ·
              </span>
            )}
            <button
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(opt.value)}
              className={cn(
                "pressable rounded-sm py-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                selected
                  ? "font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {opt.label}
            </button>
          </span>
        );
      })}
    </div>
  );
}
