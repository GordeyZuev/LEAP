"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Toggle } from "@/components/ui/toggle";

/** Nested Extra* blocks — pale wash so they sit inside a main section. */
export const ACCORDION_SHELL = "rounded-xl border border-border bg-muted/40";

/** Top-level override rows (Processing, Metadata, …) — solid card, not a nested well. */
export const ACCORDION_SHELL_MAIN = "rounded-xl border border-border bg-card";

/** Nested accordion. `plain` is a chevron row inside an existing card — no second box. */
export function Disclosure({
  title,
  hint,
  children,
  defaultOpen = false,
  open: openProp,
  onOpenChange,
  variant = "card",
}: {
  title: string;
  hint?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** `card` = nested Extra well. `main` = same white shell as OverrideSection. */
  variant?: "card" | "plain" | "main";
}) {
  const [uncontrolled, setUncontrolled] = useState(defaultOpen);
  const controlled = openProp !== undefined;
  const open = controlled ? openProp : uncontrolled;
  const bodyId = useId();
  const plain = variant === "plain";
  const shell = variant === "main" ? ACCORDION_SHELL_MAIN : ACCORDION_SHELL;

  function setOpen(next: boolean) {
    if (!controlled) setUncontrolled(next);
    onOpenChange?.(next);
  }

  return (
    <div className={plain ? "border-t border-border" : shell}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={bodyId}
        className={cn(
          "flex w-full items-center gap-2 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
          plain ? "px-0 py-3" : cn("px-4 py-3", open ? "rounded-t-xl" : "rounded-xl"),
        )}
      >
        <span className="text-sm font-semibold text-foreground">{title}</span>
        {hint ? <span className="min-w-0 truncate text-xs text-muted-foreground">{hint}</span> : null}
        <ChevronDown
          size={16}
          aria-hidden
          className={cn(
            "ms-auto shrink-0 text-muted-foreground motion-reduce:transition-none transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      <div id={bodyId}>
        {open && (
          <div className={cn("space-y-4 pt-1 pb-1", !plain && "border-t border-border px-4 pb-4 pt-3")}>
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

/** Two columns so the switch sits next to its label. */
export function ToggleGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">{children}</div>;
}

/** Same accordion as platform rows (YouTube): bordered panel, title, rotating chevron. */
export function AdvancedBlock({
  title = "Advanced",
  children,
  defaultOpen = false,
}: {
  title?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <Disclosure title={title} defaultOpen={defaultOpen}>
      {children}
    </Disclosure>
  );
}

/**
 * Override gate + disclosure. The switch writes the whole section at this
 * config level; the chevron peeks inherited values without enabling write.
 */
export function OverrideSection({
  title,
  switchLabel,
  enabled,
  onEnabledChange,
  open,
  onOpenChange,
  enabledHint,
  disabledHint = "inherits effective config",
  children,
}: {
  title: string;
  switchLabel: string;
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  enabledHint?: string;
  disabledHint?: string;
  children: ReactNode;
}) {
  const titleId = useId();
  const bodyId = useId();
  return (
    <div className={ACCORDION_SHELL_MAIN}>
      <div className="flex items-center gap-3 px-4 py-3">
        <Toggle
          label={switchLabel}
          labelHidden
          checked={enabled}
          onChange={(v) => {
            onEnabledChange(v);
            if (v) onOpenChange(true);
            else onOpenChange(false);
          }}
        />
        <button
          type="button"
          onClick={() => onOpenChange(!open)}
          aria-expanded={open}
          aria-controls={bodyId}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-1 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
        >
          <span id={titleId} className="text-sm font-semibold text-foreground">
            {title}
          </span>
          <span className="text-xs text-muted-foreground">
            {enabled ? (enabledHint ?? "overridden for this run") : disabledHint}
          </span>
          <ChevronDown
            size={16}
            aria-hidden
            className={cn(
              "ms-auto shrink-0 text-muted-foreground motion-reduce:transition-none transition-transform",
              open && "rotate-180",
            )}
          />
        </button>
      </div>

      {open && (
        <fieldset
          id={bodyId}
          disabled={!enabled}
          className="space-y-4 border-t border-border px-4 pb-4 pt-4 disabled:opacity-50"
        >
          <legend className="sr-only">{title}</legend>
          {children}
        </fieldset>
      )}
    </div>
  );
}
