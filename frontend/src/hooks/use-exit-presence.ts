"use client";

import { useEffect, useState } from "react";

/** Keep in sync with overlay/panel CSS exit duration (150ms). */
export const EXIT_PRESENCE_MS = 150;

/**
 * Delay unmount so CSS enter/exit transitions can run.
 * `visible` is false on the first paint after open, then true on the next
 * frames, so opening is interruptible (transitions, not keyframes).
 */
export function useExitPresence(open: boolean, durationMs = EXIT_PRESENCE_MS) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(false);

  if (open && !mounted) {
    setMounted(true);
  } else if (!open && visible) {
    setVisible(false);
  }

  useEffect(() => {
    if (open) {
      let inner = 0;
      const outer = requestAnimationFrame(() => {
        inner = requestAnimationFrame(() => setVisible(true));
      });
      return () => {
        cancelAnimationFrame(outer);
        cancelAnimationFrame(inner);
      };
    }
    const t = setTimeout(() => setMounted(false), durationMs);
    return () => clearTimeout(t);
  }, [open, durationMs]);

  return { mounted, visible };
}
