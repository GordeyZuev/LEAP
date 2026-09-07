"use client";

import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export function ChartCard({
  title,
  description,
  isLoading,
  isError,
  errorMessage,
  isEmpty,
  emptyMessage = "No data in this period",
  children,
  className,
}: {
  title: string;
  description?: string;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  isEmpty?: boolean;
  emptyMessage?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-2xl border border-border bg-card p-4 shadow-sm sm:p-5",
        className,
      )}
    >
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </div>
      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : isError ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-xs text-red-600">
          {errorMessage ?? "Unable to load chart"}
        </p>
      ) : isEmpty ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-xs text-muted-foreground">
          {emptyMessage}
        </p>
      ) : (
        <div className="w-full min-w-0">{children}</div>
      )}
    </div>
  );
}
