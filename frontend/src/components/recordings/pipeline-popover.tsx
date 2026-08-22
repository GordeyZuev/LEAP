"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { StatusBadge, type ProcessingStatus } from "@/components/ui/status-badge";
import {
  PipelineStageList,
  orderStages,
  pipelineSummary,
  type PipelineStage,
} from "@/components/recordings/pipeline-stages";

const PANEL_WIDTH = 288;
const PANEL_GAP = 6;
const VIEWPORT_MARGIN = 8;

interface Coords {
  left: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

/** Places the portalled panel in viewport coordinates, flipping when short of room below. */
function place(r: DOMRect): Coords {
  const left = Math.max(
    VIEWPORT_MARGIN,
    Math.min(r.right - PANEL_WIDTH, window.innerWidth - PANEL_WIDTH - VIEWPORT_MARGIN),
  );
  const below = window.innerHeight - r.bottom - PANEL_GAP - VIEWPORT_MARGIN;
  const above = r.top - PANEL_GAP - VIEWPORT_MARGIN;
  return below < 220 && above > below
    ? { left, bottom: window.innerHeight - r.top + PANEL_GAP, maxHeight: above }
    : { left, top: r.bottom + PANEL_GAP, maxHeight: below };
}

interface PipelineStatusButtonProps {
  status: ProcessingStatus;
  failed: boolean;
  /** Human label of the failed stage; forwarded to the badge. */
  failedStage?: string | null;
  stages?: PipelineStage[];
  size?: "default" | "control";
  className?: string;
}

/**
 * Status badge that opens the pipeline audit view.
 *
 * Replaces a `<div onMouseEnter>` popover which had no accessible name, no focus
 * handling and no touch path — and which was nevertheless the only place in the
 * app where a stage's failure reason was rendered.
 */
export function PipelineStatusButton({ status, failed, failedStage, stages, size = "default", className }: PipelineStatusButtonProps) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const ordered = stages?.length ? orderStages(stages) : [];
  const hasStages = ordered.length > 0;

  const close = useCallback((restoreFocus = true) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    setCoords(place(triggerRef.current.getBoundingClientRect()));
  }, [open]);

  // Move focus into the panel so its contents are announced, and so Escape has
  // somewhere to return from.
  useEffect(() => {
    if (!open) return;
    const raf = requestAnimationFrame(() => panelRef.current?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(raf);
  }, [open, coords]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    }
    function onPointerDown(e: PointerEvent) {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      close(false);
    }
    // Repositioning across nested scrollers is not worth it; closing is correct.
    const onScroll = () => close(false);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open, close]);

  if (!hasStages) {
    return <StatusBadge status={status} failed={failed} failedStage={failedStage} size={size} className={className} />;
  }

  const summary = pipelineSummary(ordered);
  const triggerSize = size === "control" ? "inline-flex h-7 items-center" : undefined;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={summary}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
          triggerSize,
          className,
        )}
      >
        <StatusBadge status={status} failed={failed} failedStage={failedStage} size={size} className="cursor-pointer" />
      </button>

      {open && coords && createPortal(
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label={summary}
          tabIndex={-1}
          style={{
            position: "fixed",
            left: coords.left,
            top: coords.top,
            bottom: coords.bottom,
            width: PANEL_WIDTH,
            maxHeight: coords.maxHeight,
            transformOrigin: coords.bottom != null ? "bottom" : "top",
          }}
          className="animate-dropdown-in z-[100] overflow-auto rounded-2xl border border-border bg-card p-3 shadow-xl outline-none"
        >
          <p className="mb-2 text-xs font-semibold text-foreground">Pipeline</p>
          <PipelineStageList stages={ordered} showTimes={false} />
        </div>,
        document.body,
      )}
    </>
  );
}
