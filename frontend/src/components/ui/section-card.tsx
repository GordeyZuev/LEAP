"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The two card densities in the app.
 *
 * `comfortable` is the settings density: a sentence-case title over a divider.
 * `compact` is the recording-surface density: an uppercase eyebrow label and no
 * divider under a static header, so a stack of cards reads as one rhythm.
 *
 * Both share one shell and one header padding per density. Before this existed
 * the recording pages carried four collapse implementations with three
 * different header paddings, so identical-looking cards behaved differently.
 */
export type CardDensity = "comfortable" | "compact";

export const CARD_SHELL = "rounded-2xl border border-border bg-card shadow-sm";

const HEADER_PAD: Record<CardDensity, string> = {
  comfortable: "px-6 py-4",
  compact: "px-5 py-4",
};

const BODY_PAD: Record<CardDensity, string> = {
  comfortable: "p-6",
  compact: "p-5",
};

/** Body padding when it sits under an open disclosure header. */
const BODY_OPEN_PAD: Record<CardDensity, string> = {
  comfortable: "px-6 pb-6 pt-4",
  compact: "px-5 pb-5 pt-4",
};

const TITLE: Record<CardDensity, string> = {
  comfortable: "text-sm font-semibold text-foreground",
  compact: "text-xs font-semibold uppercase tracking-wider text-muted-foreground",
};

export function SectionCard({
  title,
  description,
  action,
  density = "comfortable",
  className,
  bodyClassName,
  children,
}: {
  title: string;
  description?: string;
  /** Trailing header slot: a button, a count badge, a status chip. */
  action?: ReactNode;
  density?: CardDensity;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  if (density === "compact") {
    return (
      <div className={cn(CARD_SHELL, BODY_PAD.compact, className)}>
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className={TITLE.compact}>{title}</h2>
            {description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}
          </div>
          {action}
        </div>
        <div className={bodyClassName}>{children}</div>
      </div>
    );
  }

  return (
    <div className={cn(CARD_SHELL, className)}>
      <div
        className={cn(
          "flex flex-wrap items-start justify-between gap-3 border-b border-border",
          HEADER_PAD.comfortable
        )}
      >
        <div className="min-w-0">
          <h2 className={TITLE.comfortable}>{title}</h2>
          {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        </div>
        {action}
      </div>
      <div className={cn("space-y-5", BODY_PAD.comfortable, bodyClassName)}>{children}</div>
    </div>
  );
}

export function CollapsibleCard({
  title,
  subtitle,
  badge,
  action,
  defaultOpen = true,
  open: openProp,
  onOpenChange,
  density = "compact",
  className,
  bodyClassName,
  children,
}: {
  title: string;
  /** Preview shown beside the title while collapsed, e.g. the rendered name. */
  subtitle?: ReactNode;
  /** Chip rendered inside the trigger, before the chevron. */
  badge?: ReactNode;
  /** Control rendered outside the trigger so it stays independently clickable. */
  action?: ReactNode;
  defaultOpen?: boolean;
  /** Pass with `onOpenChange` to drive the card from outside. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  density?: CardDensity;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  const bodyId = useId();
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const open = openProp ?? internalOpen;

  function toggle() {
    const next = !open;
    if (openProp === undefined) setInternalOpen(next);
    onOpenChange?.(next);
  }

  return (
    <div className={cn(CARD_SHELL, className)}>
      <div className={cn("flex items-center gap-3", HEADER_PAD[density])}>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-controls={bodyId}
          className="flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
        >
          <h2 className={cn("shrink-0", TITLE[density])}>{title}</h2>
          {subtitle && (
            <span className="min-w-0 truncate text-sm font-medium text-foreground">{subtitle}</span>
          )}
          <span className="ml-auto flex shrink-0 items-center gap-2">
            {badge}
            <ChevronDown
              size={15}
              className={cn(
                "text-muted-foreground transition-transform duration-200",
                open && "rotate-180"
              )}
            />
          </span>
        </button>
        {action}
      </div>
      {/* The body wrapper is always rendered so `aria-controls` never dangles. */}
      <div id={bodyId}>
        {open && (
          <div className={cn("min-w-0 border-t border-border", BODY_OPEN_PAD[density], bodyClassName)}>
            {children}
          </div>
        )}
      </div>
    </div>
  );
}
