"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";

export interface FilterSelectOption<V extends string | number = string> {
  value: V;
  label: string;
}

interface PanelCoords {
  left: number;
  width: number;
  maxHeight: number;
  /** Exactly one of top/bottom is set — bottom means the panel opened upwards. */
  top?: number;
  bottom?: number;
}

const PANEL_GAP = 6;
const PANEL_VIEWPORT_MARGIN = 8;
const PANEL_MIN_WIDTH = 176;
const PANEL_MAX_HEIGHT = 288; // matches the previous max-h-72
const PANEL_MIN_HEIGHT = 120; // never collapse to an unusable slit
const PANEL_OPTION_HEIGHT = 40; // px per option row (py-2 + text-sm)
const PANEL_PADDING = 16; // p-2 top + bottom

/**
 * Places the portalled panel in viewport coordinates. Opens downwards by
 * default and flips above the trigger when the space below can't hold the
 * panel — otherwise a select near the bottom of the page (e.g. the page-size
 * picker in the pagination row) would render off-screen and be unreachable.
 */
function placePanel(r: DOMRect, optionCount: number): PanelCoords {
  const width = Math.max(r.width, PANEL_MIN_WIDTH);
  const left = Math.max(
    PANEL_VIEWPORT_MARGIN,
    Math.min(r.left, window.innerWidth - width - PANEL_VIEWPORT_MARGIN),
  );

  const wanted = Math.min(
    PANEL_MAX_HEIGHT,
    optionCount * PANEL_OPTION_HEIGHT + PANEL_PADDING,
  );
  const below = window.innerHeight - r.bottom - PANEL_GAP - PANEL_VIEWPORT_MARGIN;
  const above = r.top - PANEL_GAP - PANEL_VIEWPORT_MARGIN;
  const flip = below < wanted && above > below;

  const fit = (space: number) => Math.max(PANEL_MIN_HEIGHT, Math.min(wanted, space));

  return flip
    ? { left, width, bottom: window.innerHeight - r.top + PANEL_GAP, maxHeight: fit(above) }
    : { left, width, top: r.bottom + PANEL_GAP, maxHeight: fit(below) };
}

interface FilterSelectProps<V extends string | number = string> {
  value: V;
  options: FilterSelectOption<V>[];
  onChange: (value: V) => void;
  className?: string;
  disabled?: boolean;
  /** Shorter trigger (h-9) for dense rows like pagination — panel is unchanged. */
  compact?: boolean;
  /** Accessible name for the trigger when no visible label sits next to it. */
  ariaLabel?: string;
  /** Applied to the trigger so an external <label htmlFor> resolves. */
  id?: string;
  "aria-describedby"?: string;
}

export function FilterSelect<V extends string | number = string>({
  value,
  options,
  onChange,
  className,
  disabled = false,
  compact = false,
  ariaLabel,
  id,
  "aria-describedby": describedBy,
}: FilterSelectProps<V>) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const optionId = (i: number) => `${listboxId}-opt-${i}`;
  // Index of the keyboard-highlighted option. Focus stays on the trigger and
  // the highlight is published via aria-activedescendant (the APG combobox
  // pattern) — the panel is portalled to <body>, so moving real focus into it
  // would drop the user at the end of the document on the next Tab.
  const [activeIndex, setActiveIndex] = useState(-1);
  // Dropdown is portalled to <body> with fixed positioning so it never gets
  // clipped by a scrollable parent (modals, overflow containers).
  const [coords, setCoords] = useState<PanelCoords | null>(null);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    setCoords(placePanel(triggerRef.current.getBoundingClientRect(), options.length));
  }, [open, options.length]);

  useEffect(() => {
    if (!open) return;
    const el = panelRef.current?.querySelector<HTMLElement>('[data-highlighted="true"]');
    el?.scrollIntoView({ block: "nearest" });
  }, [open, coords, activeIndex]);

  useEffect(() => {
    if (!open) return;
    function close() { setOpen(false); }
    function onMouseDown(e: MouseEvent) {
      if (triggerRef.current && !triggerRef.current.contains(e.target as Node)) {
        // Clicks inside the portalled panel are handled by the option buttons
        // (which close on select); any other click closes the menu.
        if (!panelRef.current || !panelRef.current.contains(e.target as Node)) close();
      }
    }
    function onScroll(e: Event) {
      // Ignore scroll events from within the panel itself (e.g. scrollIntoView
      // on the active option triggers a scroll on the overflow container).
      if (panelRef.current && panelRef.current.contains(e.target as Node)) return;
      close();
    }
    document.addEventListener("mousedown", onMouseDown);
    // Reposition is non-trivial across nested scrollers — closing on scroll is
    // the simplest correct behavior.
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  const selected = options.find((o) => o.value === value);

  function openAt(index: number) {
    setActiveIndex(index);
    setOpen(true);
  }

  function commit(index: number) {
    const opt = options[index];
    if (!opt) return;
    onChange(opt.value);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onTriggerKeyDown(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    const selectedIndex = options.findIndex((o) => o.value === value);

    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openAt(selectedIndex >= 0 ? selectedIndex : 0);
      }
      return;
    }

    switch (e.key) {
      case "Escape":
        e.preventDefault();
        setOpen(false);
        break;
      case "ArrowDown":
        e.preventDefault();
        setActiveIndex((i) => Math.min(options.length - 1, i + 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActiveIndex((i) => Math.max(0, i - 1));
        break;
      case "Home":
        e.preventDefault();
        setActiveIndex(0);
        break;
      case "End":
        e.preventDefault();
        setActiveIndex(options.length - 1);
        break;
      case "Enter":
      case " ":
        // preventDefault stops the button's native click, which would otherwise
        // re-toggle the panel we just closed.
        e.preventDefault();
        commit(activeIndex);
        break;
      case "Tab":
        setOpen(false);
        break;
    }
  }

  return (
    <div className={cn("relative", className)}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        disabled={disabled}
        role="combobox"
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-activedescendant={open && activeIndex >= 0 ? optionId(activeIndex) : undefined}
        onKeyDown={onTriggerKeyDown}
        onClick={() => {
          if (open) setOpen(false);
          else openAt(Math.max(0, options.findIndex((o) => o.value === value)));
        }}
        className={cn(
          FILTER_CONTROL,
          "flex w-full items-center justify-between gap-2 text-left font-medium text-secondary-foreground",
          compact && "min-h-9 px-2.5 py-1 text-xs",
          disabled && "cursor-not-allowed opacity-50"
        )}
      >
        <span className="truncate">{selected?.label ?? "—"}</span>
        <ChevronDown
          size={compact ? 13 : 16}
          className={cn("shrink-0 opacity-60 transition-transform duration-150", open && "rotate-180")}
        />
      </button>

      {open && coords && createPortal(
        <div
          ref={panelRef}
          style={{
            position: "fixed",
            top: coords.top,
            bottom: coords.bottom,
            left: coords.left,
            width: coords.width,
            maxHeight: coords.maxHeight,
            // animate-dropdown-in grows from the top; a flipped panel must grow
            // from its bottom edge instead.
            transformOrigin: coords.bottom != null ? "bottom" : "top",
          }}
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel}
          className="animate-dropdown-in z-[100] overflow-auto rounded-2xl border border-border bg-card p-2 shadow-xl"
        >
          {options.map((opt, i) => (
            <div
              key={String(opt.value)}
              id={optionId(i)}
              role="option"
              aria-selected={opt.value === value}
              data-highlighted={i === activeIndex ? "true" : undefined}
              onMouseEnter={() => setActiveIndex(i)}
              // The panel closes on mousedown-outside, so commit on mousedown
              // rather than click or the option would unmount first.
              onMouseDown={(e) => { e.preventDefault(); commit(i); }}
              className={cn(
                "flex w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2 text-sm",
                opt.value === value ? "text-primary font-medium" : "text-secondary-foreground",
                i === activeIndex ? "bg-accent" : opt.value === value && "bg-accent/60"
              )}
            >
              <span className="flex-1 truncate text-left">{opt.label}</span>
              {opt.value === value && <Check size={14} className="shrink-0" />}
            </div>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}
