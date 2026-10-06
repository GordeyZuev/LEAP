import { Eye } from "lucide-react";

import { formatCompactNumber, formatExactViewCount } from "@/lib/format-compact-number";

/** All-time LEAP page views. Renders nothing until the first view so empty catalogs stay quiet. */
export function ViewCount({
  count,
  hint,
}: {
  count: number | null | undefined;
  /** Completes the exact count in the tooltip and for screen readers, e.g. "across all videos in this playlist". */
  hint?: string;
}) {
  if (!count || count <= 0) return null;
  const label = hint ? `${formatExactViewCount(count)} ${hint}` : formatExactViewCount(count);
  return (
    <span title={label} className="inline-flex shrink-0 items-center gap-1.5 text-xs tabular-nums text-muted-foreground">
      <Eye size={12} strokeWidth={2} className="shrink-0 text-muted-foreground/80" aria-hidden />
      <span aria-hidden>{formatCompactNumber(count)}</span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
