"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";

interface NumberInputProps {
  value: number;
  onCommit: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  /** Round to a whole number and use the numeric keypad on mobile. */
  integer?: boolean;
  disabled?: boolean;
  className?: string;
  id?: string;
  "aria-describedby"?: string;
}

/**
 * Number input that keeps the user's raw keystrokes and only coerces on blur.
 *
 * Coercing per keystroke — `parseInt(e.target.value) || 1` and friends — makes a
 * field impossible to clear, because it snaps to a default mid-typing, and
 * silently produces wrong values: clearing "5000" then typing "3000" left 13000
 * behind, and a lone "-" jumped straight to the default.
 */
export function NumberInput({
  value,
  onCommit,
  min,
  max,
  step,
  integer = false,
  disabled,
  className,
  id,
  "aria-describedby": describedBy,
}: NumberInputProps) {
  const [draft, setDraft] = useState(() => String(value));
  const editingRef = useRef(false);

  useEffect(() => {
    // Follow external changes (server hydration, reset to defaults) but never
    // yank the value out from under someone mid-edit.
    if (!editingRef.current) setDraft(String(value));
  }, [value]);

  function commit() {
    editingRef.current = false;
    const parsed = Number.parseFloat(draft);
    if (Number.isNaN(parsed)) {
      setDraft(String(value));
      return;
    }
    let next = integer ? Math.round(parsed) : parsed;
    if (min != null) next = Math.max(min, next);
    if (max != null) next = Math.min(max, next);
    setDraft(String(next));
    onCommit(next);
  }

  return (
    <input
      id={id}
      aria-describedby={describedBy}
      type="number"
      inputMode={integer ? "numeric" : "decimal"}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      value={draft}
      onChange={(e) => {
        editingRef.current = true;
        setDraft(e.target.value);
      }}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
      className={cn(FILTER_CONTROL, "tabular-nums", className)}
    />
  );
}
