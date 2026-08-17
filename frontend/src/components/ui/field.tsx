"use client";

import { cloneElement, isValidElement, useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { FILTER_LABEL } from "@/lib/filter-field-classes";

interface FieldProps {
  label: string;
  /** Secondary line under the label, wired up via aria-describedby. */
  hint?: string;
  children: ReactNode;
  className?: string;
}

/**
 * Labelled form row.
 *
 * Generates the id and injects it into the control, so the `<label>` actually
 * names it — a bare `<label>` with no `htmlFor` announces nothing, which is how
 * most of this codebase's forms were built (`<span className={FILTER_LABEL}>`
 * sitting next to an input it has no relationship with).
 *
 * Not for radio groups: those need `role="radiogroup"` on a wrapper rather than
 * a label pointing at one of several buttons — use `SegmentedField`.
 */
export function Field({ label, hint, children, className }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const control = isValidElement<{ id?: string; "aria-describedby"?: string }>(children)
    ? cloneElement(children, { id, "aria-describedby": hint ? hintId : undefined })
    : children;
  return (
    <div className={className}>
      <label htmlFor={id} className={cn(FILTER_LABEL, "mb-1.5")}>{label}</label>
      {hint && <p id={hintId} className="mb-1.5 text-xs text-muted-foreground">{hint}</p>}
      {control}
    </div>
  );
}
