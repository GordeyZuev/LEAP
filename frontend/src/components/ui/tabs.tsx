"use client";

import { useId, useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabItem<V extends string> {
  value: V;
  label: string;
  /** Trailing marker, e.g. an unsaved-change count. */
  badge?: ReactNode;
}

interface TabsProps<V extends string> {
  items: TabItem<V>[];
  value: V;
  onChange: (value: V) => void;
  /** Accessible name for the tab list. */
  label: string;
  children: ReactNode;
  className?: string;
  tablistClassName?: string;
  /** Render only the tab rail; pair with an external `role="tabpanel"` via `panelId`. */
  hidePanel?: boolean;
  panelId?: string;
  /** Stable id prefix for tab/panel nodes (defaults to `useId()`). */
  idPrefix?: string;
}

/**
 * Tab list + panel, following the ARIA APG tab pattern.
 *
 * Roving tabindex: only the selected tab is in the tab order, and arrow keys
 * move between tabs. Tab then jumps straight into the panel rather than walking
 * every tab first.
 *
 * The rail scrolls horizontally rather than wrapping or clipping, so a narrow
 * viewport never hides a section.
 */
export function Tabs<V extends string>({
  items,
  value,
  onChange,
  label,
  children,
  className,
  tablistClassName,
  hidePanel = false,
  panelId: panelIdProp,
  idPrefix,
}: TabsProps<V>) {
  const generated = useId();
  const base = idPrefix ?? generated;
  const tabId = (v: V) => `${base}-tab-${v}`;
  const panelId = (v: V) => `${base}-panel-${v}`;
  const refs = useRef(new Map<V, HTMLButtonElement | null>());

  function focusTab(next: V) {
    onChange(next);
    refs.current.get(next)?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const i = items.findIndex((t) => t.value === value);
    if (i < 0) return;
    switch (e.key) {
      case "ArrowRight":
        e.preventDefault();
        focusTab(items[(i + 1) % items.length].value);
        break;
      case "ArrowLeft":
        e.preventDefault();
        focusTab(items[(i - 1 + items.length) % items.length].value);
        break;
      case "Home":
        e.preventDefault();
        focusTab(items[0].value);
        break;
      case "End":
        e.preventDefault();
        focusTab(items[items.length - 1].value);
        break;
    }
  }

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
        // The active tab draws a ring outside its box, so the scroll container
        // needs vertical room or it clips the top edge. -my-1 keeps the padding
        // from changing the rail's outer spacing.
        className={cn(
          "-mx-1 -my-1 mb-5 flex gap-1 overflow-x-auto p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
          tablistClassName,
        )}
      >
        {items.map((t) => {
          const active = t.value === value;
          return (
            <button
              key={t.value}
              ref={(el) => { refs.current.set(t.value, el); }}
              id={tabId(t.value)}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={hidePanel && panelIdProp ? panelIdProp : panelId(t.value)}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(t.value)}
              className={cn(
                "flex shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3.5 py-2 text-sm font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                active
                  ? "bg-card text-primary shadow-sm ring-1 ring-border"
                  : "text-muted-foreground hover:bg-muted hover:text-secondary-foreground"
              )}
            >
              {t.label}
              {t.badge}
            </button>
          );
        })}
      </div>

      {/* No tabIndex: every panel here contains focusable controls, and APG
          only calls for making the panel itself focusable when it does not. */}
      {!hidePanel && (
        <div role="tabpanel" id={panelId(value)} aria-labelledby={tabId(value)}>
          {children}
        </div>
      )}
    </div>
  );
}
