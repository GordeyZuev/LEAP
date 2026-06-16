"use client";

import { cn } from "@/lib/utils";

type ProgressBarProps =
  | { variant: "determinate"; value: number; className?: string }
  | { variant: "indeterminate"; className?: string; value?: never };

export function ProgressBar(props: ProgressBarProps) {
  const { variant, className } = props;
  const value = variant === "determinate" ? props.value : undefined;

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-gray-100", className)}
    >
      {variant === "determinate" && (
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
          style={{ width: `${Math.min(100, Math.max(0, value ?? 0))}%` }}
        />
      )}
      {variant === "indeterminate" && (
        <div className="h-full w-full rounded-full animate-progress-stripe" />
      )}
    </div>
  );
}
