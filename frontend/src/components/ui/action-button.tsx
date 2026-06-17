"use client";

import { useEffect, useState } from "react";
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
  "flex items-center gap-2 font-medium disabled:opacity-50 transition-all duration-200 active:scale-[0.97]";

const SIZES: Record<NonNullable<ActionButtonProps["size"]>, string> = {
  md: "px-4 py-2 rounded-xl text-sm",
  sm: "px-3 py-1.5 rounded-lg text-xs",
};

const VARIANTS: Record<NonNullable<ActionButtonProps["variant"]>, string> = {
  primary:   "bg-[#224C87] text-white hover:bg-[#1a3d6e]",
  secondary: "border border-[#D9D9D9] text-gray-600 hover:bg-gray-50",
  danger:    "bg-red-500 text-white hover:bg-red-600",
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

  const iconSize = size === "sm" ? 12 : 15;
  const iconNode = isPending
    ? <RefreshCw size={iconSize} className="animate-spin" />
    : justSaved
      ? <Check size={iconSize} />
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
