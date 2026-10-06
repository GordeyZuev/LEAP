"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type HTMLAttributes,
  type ReactNode,
} from "react";

import { cssLengthToPx, scrollThumbGeometry } from "@/lib/scroll-thumb";
import { cn } from "@/lib/utils";

const HIDE_MS = 800;

type InsetScrollProps = {
  className?: string;
  /** Layout classes for the outer frame when it, not the scroller, is the flex child. */
  frameClassName?: string;
  /**
   * How far the thumb stays from the top and bottom. Defaults to the rounded-2xl
   * radius so the pill stops where the corner curve starts.
   */
  inset?: string;
  /** Override one end when a header or footer already clears that corner. */
  insetTop?: string;
  insetBottom?: string;
  children: ReactNode;
  onScroll?: HTMLAttributes<HTMLDivElement>["onScroll"];
} & Omit<HTMLAttributes<HTMLDivElement>, "className" | "children" | "onScroll">;

/**
 * Scroll box whose thumb is drawn over the content, hides when idle, and stops
 * short of the rounded corners. The system bar cannot do those three things at
 * once: shortening its track forces a permanent gutter.
 */
export function InsetScroll({
  className,
  frameClassName,
  inset = "1.75rem",
  insetTop = inset,
  insetBottom = inset,
  children,
  onScroll,
  ...rest
}: InsetScrollProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [thumb, setThumb] = useState<{ top: number; height: number } | null>(null);
  const [visible, setVisible] = useState(false);

  const measure = useCallback(() => {
    const el = scrollerRef.current;
    const frame = frameRef.current;
    if (!el || !frame) return null;
    const rootFont = Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    const specifiedTop = getComputedStyle(frame).getPropertyValue("--scroll-inset-top");
    const specifiedBottom = getComputedStyle(frame).getPropertyValue("--scroll-inset-bottom");
    const topPx = cssLengthToPx(specifiedTop || insetTop, rootFont);
    const bottomPx = cssLengthToPx(specifiedBottom || insetBottom, rootFont);
    return scrollThumbGeometry(el.scrollTop, el.scrollHeight, el.clientHeight, topPx, bottomPx);
  }, [insetTop, insetBottom]);

  const sync = useCallback(
    (reveal: boolean) => {
      const next = measure();
      setThumb(next);
      if (!reveal) return;
      setVisible(next !== null);
      if (hideTimer.current) clearTimeout(hideTimer.current);
      hideTimer.current = setTimeout(() => setVisible(false), HIDE_MS);
    },
    [measure],
  );

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => sync(false));
    ro.observe(el);
    for (const child of el.children) ro.observe(child);
    const mo = new MutationObserver(() => {
      for (const child of el.children) ro.observe(child);
      sync(false);
    });
    mo.observe(el, { childList: true });
    sync(false);
    return () => {
      ro.disconnect();
      mo.disconnect();
      if (hideTimer.current) clearTimeout(hideTimer.current);
    };
  }, [sync]);

  return (
    <div
      ref={frameRef}
      className={cn("relative", frameClassName)}
      style={{ "--scroll-inset-top": insetTop, "--scroll-inset-bottom": insetBottom } as CSSProperties}
    >
      <div
        ref={scrollerRef}
        onScroll={(event) => {
          sync(true);
          onScroll?.(event);
        }}
        className={cn(
          "overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
          className,
        )}
        {...rest}
      >
        {children}
      </div>
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute right-1 w-1.5 rounded-full bg-muted-foreground/45 transition-opacity duration-300 motion-reduce:transition-none",
          visible && thumb ? "opacity-100" : "opacity-0",
        )}
        style={thumb ? { top: thumb.top, height: thumb.height } : undefined}
      />
    </div>
  );
}
