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

// Name the properties that actually change: `transition-all` makes the browser
// watch every property and animates ones we never meant to (padding, radius).
const BASE =
  "flex items-center gap-2 font-medium disabled:opacity-50 " +
  "transition-[color,background-color,border-color,box-shadow,opacity,scale] duration-200 ease-out " +
  "active:scale-[0.96]";

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

  useEffect(() => {
    if (!isSuccess) return;
    const t1 = setTimeout(() => setJustSaved(true), 0);
    const t2 = setTimeout(() => setJustSaved(false), 1500);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [isSuccess]);

  // The button owns icon sizing so one surface never mixes sizes. Both values
  // are clean divisions of lucide's 24px grid; off-grid sizes render soft.
  const iconSize = size === "sm" ? 12 : 16;
  const iconNode = isPending
    ? <RefreshCw size={iconSize} className="animate-spin" />
    : justSaved
      ? <Check size={iconSize} />
      : isValidElement<{ size?: number }>(icon)
        ? cloneElement(icon, { size: iconSize })
        : icon ?? null;

  const variantClass = justSaved && variant === "primary" ? SUCCESS : VARIANTS[variant];

  return (
    <button
      type={rest.type ?? "button"}
      disabled={disabled || isPending}
      className={cn(BASE, SIZES[size], variantClass, className)}
      {...rest}
    >
      {iconNode}
      {isPending && pendingLabel ? pendingLabel : children}
    </button>
  );
}
