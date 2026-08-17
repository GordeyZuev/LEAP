"use client";

import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// Moved to components/ui so the recording surfaces share one card shell.
// Re-exported here so existing settings imports keep working.
export { SectionCard } from "@/components/ui/section-card";

export function Collapsible({
  label,
  open,
  onToggle,
  changed = 0,
  children,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
  /** Unsaved edits inside this section, so collapsing never hides them. */
  changed?: number;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-background">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-secondary-foreground transition-colors hover:text-foreground"
      >
        <span className="flex items-center gap-2">
          {label}
          {changed > 0 && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-primary">
              {changed} unsaved
            </span>
          )}
        </span>
        <ChevronDown
          size={16}
          className={cn("shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open && <div className="space-y-4 border-t border-border px-4 pb-4 pt-4">{children}</div>}
    </div>
  );
}

export function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border py-2.5 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}
