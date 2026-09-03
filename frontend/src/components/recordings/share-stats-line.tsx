import { formatShareStatsSummary, type ShareStatsSummary } from "@/lib/share-stats";
import { cn } from "@/lib/utils";

export function ShareStatsLine({
  stats,
  className,
}: {
  stats: ShareStatsSummary | null | undefined;
  className?: string;
}) {
  const text = formatShareStatsSummary(stats);
  if (!text) return null;

  return (
    <p className={cn("text-xs text-muted-foreground tabular-nums", className)}>{text}</p>
  );
}
