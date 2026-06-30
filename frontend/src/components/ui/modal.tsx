"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name. Either pass `labelledBy` (id of an in-content <h2>) or `label`. */
  label?: string;
  labelledBy?: string;
  /** Close when the backdrop is clicked. Default true. */
  closeOnBackdrop?: boolean;
  /** Close on ESC. Default true. Disable if the dialog contains nested popovers that should handle ESC first. */
  closeOnEsc?: boolean;
  className?: string;
  /** Wrapper class around the dialog box (controls width/max-width). */
  panelClassName?: string;
  children: ReactNode;
}

// Selector for focusable elements inside the dialog. Excludes elements with
// `tabIndex={-1}` (e.g. the password-input eye toggle).
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[contenteditable]",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.hasAttribute("disabled") && el.tabIndex !== -1 && isVisible(el),
  );
}

function isVisible(el: HTMLElement): boolean {
  return el.offsetParent !== null || el.getClientRects().length > 0;
}

// Refcounted body scroll lock — multiple stacked modals share one lock so
// closing the inner one doesn't unlock while the outer is still open.
let scrollLockCount = 0;
let savedBodyOverflow = "";
let savedBodyPaddingRight = "";

function acquireScrollLock() {
  if (typeof document === "undefined") return;
  if (scrollLockCount === 0) {
    savedBodyOverflow = document.body.style.overflow;
    savedBodyPaddingRight = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    if (scrollbarWidth > 0) {
      document.body.style.paddingRight = `${scrollbarWidth}px`;
    }
  }
  scrollLockCount += 1;
}

function releaseScrollLock() {
  if (typeof document === "undefined") return;
  scrollLockCount = Math.max(0, scrollLockCount - 1);
  if (scrollLockCount === 0) {
    document.body.style.overflow = savedBodyOverflow;
    document.body.style.paddingRight = savedBodyPaddingRight;
  }
}

export function Modal({
  open,
  onClose,
  label,
  labelledBy,
  closeOnBackdrop = true,
  closeOnEsc = true,
  className,
  panelClassName,
  children,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const fallbackLabelId = useId();

  // ESC + body scroll lock + focus management — all gated on `open`.
  useEffect(() => {
    if (!open) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;
    acquireScrollLock();

    // Move focus into the dialog. Prefer the first focusable element; if none,
    // focus the panel itself (which is made focusable via tabIndex={-1}).
    const focusInitial = () => {
      const panel = panelRef.current;
      if (!panel) return;
      const focusables = getFocusable(panel);
      const target = focusables[0] ?? panel;
      target.focus({ preventScroll: true });
    };
    // requestAnimationFrame: let React paint the dialog before we focus,
    // otherwise autoFocus inputs lose the race and offsetParent checks fail.
    const raf = requestAnimationFrame(focusInitial);

    function onKeyDown(e: globalThis.KeyboardEvent) {
      if (closeOnEsc && e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    document.addEventListener("keydown", onKeyDown);

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKeyDown);
      releaseScrollLock();
      // Restore focus to whoever opened the dialog. The element may have been
      // removed from the DOM in the meantime — guard with isConnected.
      const prev = previouslyFocused.current;
      if (prev && prev.isConnected && typeof prev.focus === "function") {
        prev.focus({ preventScroll: true });
      }
      previouslyFocused.current = null;
    };
  }, [open, closeOnEsc, onClose]);

  const handleKeyDownTrap = useCallback((e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab") return;
    const panel = panelRef.current;
    if (!panel) return;
    const focusables = getFocusable(panel);
    if (focusables.length === 0) {
      e.preventDefault();
      panel.focus({ preventScroll: true });
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement as HTMLElement | null;
    if (e.shiftKey) {
      if (active === first || !panel.contains(active)) {
        e.preventDefault();
        last.focus({ preventScroll: true });
      }
    } else {
      if (active === last || !panel.contains(active)) {
        e.preventDefault();
        first.focus({ preventScroll: true });
      }
    }
  }, []);

  const handleBackdropClick = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (!closeOnBackdrop) return;
      if (e.target === e.currentTarget) onClose();
    },
    [closeOnBackdrop, onClose],
  );

  if (!open) return null;

  const ariaLabelledBy = labelledBy ?? (label ? fallbackLabelId : undefined);

  return (
    <div
      role="presentation"
      onClick={handleBackdropClick}
      className={cn(
        "animate-overlay-in fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4",
        className,
      )}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={ariaLabelledBy}
        tabIndex={-1}
        onKeyDown={handleKeyDownTrap}
        className={cn(
          "animate-panel-in outline-none w-full max-w-md rounded-2xl bg-card shadow-xl",
          panelClassName,
        )}
      >
        {label && !labelledBy && (
          <span id={fallbackLabelId} className="sr-only">
            {label}
          </span>
        )}
        {children}
      </div>
    </div>
  );
}
