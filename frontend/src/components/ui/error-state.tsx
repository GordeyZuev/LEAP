import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Consistent error placeholder with an optional retry action. Use inside a card
 * body or a full-width table cell when a query fails.
 */
export function ErrorState({
  title = "Something went wrong",
  description,
  onRetry,
  className,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 py-16 text-center", className)}>
      <div className="rounded-2xl bg-red-50 dark:bg-red-500/10 p-3 text-red-300">
        <AlertTriangle size={28} strokeWidth={1.5} />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-red-500">{title}</p>
        {description && <p className="mx-auto max-w-sm text-xs text-muted-foreground">{description}</p>}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-medium text-secondary-foreground transition-colors hover:bg-muted"
        >
          Try again
        </button>
      )}
    </div>
  );
}
