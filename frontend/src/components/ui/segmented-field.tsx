"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";
import {
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
} from "@/lib/filter-field-classes";

export interface SegmentedOption<V extends string | number = string> {
  value: V;
  label: string;
}

interface SegmentedFieldProps<V extends string | number> {
  label: string;
  value: V;
  options: SegmentedOption<V>[];
  onChange: (value: V) => void;
  /** Label is still required for the accessible name, just not painted. */
  labelHidden?: boolean;
  disabled?: boolean;
  className?: string;
}

/**
 * Single-choice segmented control (radio group).
 *
 * Use this everywhere a row of mutually exclusive options is needed — filter
 * toolbars (`SegmentedFilter`), modals, settings forms. Do not hand-roll
 * `FILTER_SEGMENT_*` buttons.
 */
export function SegmentedField<V extends string | number = string>({
  label,
  value,
  options,
  onChange,
  labelHidden = false,
  disabled = false,
  className,
}: SegmentedFieldProps<V>) {
  const labelId = useId();
  return (
    <div data-segmented-field className={cn("w-fit max-w-full", className)}>
      <span id={labelId} className={cn(FILTER_LABEL, "mb-1.5", labelHidden && "sr-only")}>
        {label}
      </span>
      <div
        role="radiogroup"
        aria-labelledby={labelId}
        className={cn(FILTER_SEGMENT_WRAP, disabled && "opacity-50")}
      >
        {options.map((opt) => (
          <button
            key={String(opt.value)}
            type="button"
            role="radio"
            aria-checked={value === opt.value}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              FILTER_SEGMENT_BTN,
              value === opt.value ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE,
              disabled && "cursor-not-allowed"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
