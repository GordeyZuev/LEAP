import { AlertTriangle } from "lucide-react";
import { cn, extractApiError } from "@/lib/utils";

/**
 * Consistent error placeholder with an optional retry action. Use inside a card
 * body or a full-width table cell when a query fails.
 *
 * Pass `error` so a rate limit, outage, or lost connection replaces `description`.
 */
export function ErrorState({
  title = "Something went wrong",
  description,
  error,
  onRetry,
  className,
}: {
  title?: string;
  description?: string;
  error?: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const detail = error ? extractApiError(error, description ?? "") : description;
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 py-16 text-center animate-card-in", className)}>
      <div className="rounded-2xl bg-danger-fg/10 p-3 text-danger-fg">
        <AlertTriangle size={28} strokeWidth={1.5} />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-danger-fg">{title}</p>
        {detail && <p className="mx-auto max-w-sm text-xs text-muted-foreground">{detail}</p>}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="pressable rounded-xl border border-border bg-card px-4 py-2 text-sm font-medium text-secondary-foreground hover:bg-muted"
        >
          Try again
        </button>
      )}
    </div>
  );
}
