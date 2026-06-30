"use client";

import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastType = "success" | "error" | "info";

interface ToastProps {
  type: ToastType;
  message: string;
  exiting: boolean;
  onDismiss: () => void;
}

export function Toast({ type, message, exiting, onDismiss }: ToastProps) {
  return (
    <div
      role="status"
      aria-live={type === "error" ? "assertive" : "polite"}
      className={cn(
        "fixed bottom-6 right-6 left-6 z-50 flex max-w-sm items-center gap-2.5 rounded-2xl border bg-card px-4 py-3 shadow-lg sm:left-auto",
        type === "success" && "border-green-200",
        type === "error"   && "border-red-200",
        type === "info"    && "border-blue-200",
        exiting ? "animate-toast-out" : "animate-toast-in",
      )}
    >
      {type === "success" && <CheckCircle2 size={15} className="shrink-0 text-green-500" />}
      {type === "error"   && <XCircle      size={15} className="shrink-0 text-red-500"   />}
      {type === "info"    && <Info         size={15} className="shrink-0 text-blue-500"  />}
      <span
        className={cn(
          "text-sm font-medium",
          type === "success" && "text-green-700",
          type === "error"   && "text-red-600",
          type === "info"    && "text-blue-700",
        )}
      >
        {message}
      </span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="ml-auto shrink-0 text-muted-foreground hover:text-secondary-foreground"
      >
        <X size={14} />
      </button>
    </div>
  );
}
