"use client";

import { X } from "lucide-react";

export interface FilterChipItem {
  key: string;
  label: string;
  onRemove: () => void;
}

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[#224C87]/20 bg-[#224C87]/5 py-1 pl-3 pr-1.5 text-xs font-medium text-[#224C87]">
      <span className="max-w-[14rem] truncate">{label}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${label}`}
        className="rounded-full p-0.5 text-[#224C87]/70 transition-colors hover:bg-[#224C87]/15 hover:text-[#224C87]"
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
