"use client";

import { cloneElement, isValidElement, useEffect, useState } from "react";
import { Check, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ActionButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "neutral";
  size?: "md" | "sm";
  isPending?: boolean;
  isSuccess?: boolean;
  icon?: React.ReactNode;
  pendingLabel?: string;
}

const BASE =
  "pressable flex items-center gap-2 font-medium disabled:opacity-50";

const SIZES: Record<NonNullable<ActionButtonProps["size"]>, string> = {
  md: "px-4 py-2 rounded-xl text-sm",
  sm: "px-3 py-1.5 rounded-xl text-xs",
};

const VARIANTS: Record<NonNullable<ActionButtonProps["variant"]>, string> = {
  primary:   "bg-primary text-primary-foreground hover:bg-primary-hover",
  secondary: "border border-border text-secondary-foreground hover:bg-muted",
  // --destructive is tuned as a solid fill behind white text (globals.css).
  danger:    "bg-destructive text-white hover:brightness-95",
  neutral:   "bg-gray-900 text-white hover:bg-gray-800",
};

const SUCCESS = "bg-green-600 text-white hover:bg-green-600";

const ICON_SWAP =
  "absolute inset-0 flex items-center justify-center " +
  "transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)]";

function iconSwapClass(show: boolean) {
  return cn(
    ICON_SWAP,
    show ? "scale-100 opacity-100 blur-0" : "pointer-events-none scale-[0.25] opacity-0 blur-[4px]",
  );
}

export function ActionButton({
  variant = "primary",
  size = "md",
  isPending = false,
  isSuccess = false,
  icon,
  pendingLabel,
  children,
  disabled,
  className,
  ...rest
}: ActionButtonProps) {
  const [justSaved, setJustSaved] = useState(false);

  if (!isSuccess && justSaved) {
    setJustSaved(false);
  }

  useEffect(() => {
    if (!isSuccess) return;
    const t1 = setTimeout(() => setJustSaved(true), 0);
    const t2 = setTimeout(() => setJustSaved(false), 1500);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [isSuccess]);

  // The button owns icon sizing so one surface never mixes sizes. Both values
  // are clean divisions of lucide's 24px grid; off-grid sizes render soft.
  const iconSize = size === "sm" ? 12 : 16;
  const idleIcon = isValidElement<{ size?: number }>(icon)
    ? cloneElement(icon, { size: iconSize })
    : icon ?? null;
  const showIconSlot = Boolean(idleIcon) || isPending || justSaved;

  const variantClass = justSaved && variant === "primary" ? SUCCESS : VARIANTS[variant];

  return (
    <button
      type={rest.type ?? "button"}
      disabled={disabled || isPending}
      className={cn(BASE, SIZES[size], variantClass, className)}
      {...rest}
    >
      {showIconSlot && (
        <span className="relative shrink-0" style={{ width: iconSize, height: iconSize }}>
          <span className={iconSwapClass(isPending)} aria-hidden>
            <RefreshCw size={iconSize} className={isPending ? "animate-spin" : undefined} />
          </span>
          <span className={iconSwapClass(justSaved && !isPending)} aria-hidden>
            <Check size={iconSize} />
          </span>
          {idleIcon != null && (
            <span className={iconSwapClass(!isPending && !justSaved)} aria-hidden>
              {idleIcon}
            </span>
          )}
        </span>
      )}
      {isPending && pendingLabel ? pendingLabel : children}
    </button>
  );
}
