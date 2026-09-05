"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";

interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  /** Secondary line under the label. */
  hint?: string;
  disabled?: boolean;
  /** Track colour when on — `warning` marks a state that blocks something else. */
  tone?: "primary" | "warning";
  /** Hides the visible label when the surrounding layout already names the control. */
  labelHidden?: boolean;
  className?: string;
}

const TRACK_ON: Record<NonNullable<ToggleProps["tone"]>, string> = {
  primary: "bg-primary",
  warning: "bg-warning",
};

/**
 * Labelled on/off switch.
 *
 * Always renders as `role="switch"` so assistive tech reports the state — the
 * per-page copies this replaces were plain buttons on three of five screens.
 */
export function Toggle({
  label,
  checked,
  onChange,
  hint,
  disabled = false,
  tone = "primary",
  labelHidden = false,
  className,
}: ToggleProps) {
  const labelId = useId();
  const hintId = useId();

  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 py-1.5",
        disabled && "cursor-not-allowed opacity-40",
        className,
      )}
    >
      {!labelHidden && (
        <div className="min-w-0">
          <p id={labelId} className="text-sm font-medium leading-snug text-secondary-foreground">
            {label}
          </p>
          {hint && (
            <p id={hintId} className="mt-0.5 text-xs leading-snug text-muted-foreground">
              {hint}
            </p>
          )}
        </div>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelHidden ? undefined : labelId}
        aria-describedby={hint && !labelHidden ? hintId : undefined}
        aria-label={labelHidden ? label : undefined}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
          "disabled:cursor-not-allowed",
          checked ? TRACK_ON[tone] : "bg-muted",
        )}
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-6" : "translate-x-1",
          )}
        />
      </button>
    </div>
  );
}
