"use client";

import { X } from "lucide-react";

export interface FilterChipItem {
  key: string;
  label: string;
  onRemove: () => void;
}

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="animate-toast-in inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/5 py-1 pl-3 pr-1.5 text-xs font-medium text-primary">
      <span className="max-w-[14rem] truncate">{label}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${label}`}
        className="rounded-full p-0.5 text-primary/70 transition-colors hover:bg-primary/15 hover:text-primary"
      >
        <X size={12} />
      </button>
    </span>
  );
}

/** Removable chips for active filters. Returns null when there are none. */
export function FilterChips({ chips }: { chips: FilterChipItem[] }) {
  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((c) => (
        <Chip key={c.key} label={c.label} onRemove={c.onRemove} />
      ))}
    </div>
  );
}
