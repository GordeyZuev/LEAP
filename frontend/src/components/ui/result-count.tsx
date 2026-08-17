import { cn } from "@/lib/utils";

interface ResultCountProps {
  total: number | undefined;
  /** Singular noun; pluralised with a trailing "s" unless overridden. */
  itemLabel: string;
  /** For nouns that do not pluralise with a trailing "s" (entry → entries). */
  itemLabelPlural?: string;
  /** Adds "matching filters" so a narrowed list reads as narrowed, not empty. */
  filtered?: boolean;
  className?: string;
}

/**
 * "N recordings matching filters" — shown next to the filters so the effect of
 * narrowing is visible without scrolling down to the pagination line.
 *
 * A polite live region: filtering changes this number with no page load, so it
 * is the canonical case for `role="status"`. The element is always rendered and
 * only its text changes — a region inserted together with its content is
 * announced inconsistently.
 */
export function ResultCount({ total, itemLabel, itemLabelPlural, filtered = false, className }: ResultCountProps) {
  return (
    <p role="status" className={cn("mb-4 text-sm tabular-nums text-muted-foreground", className)}>
      {total !== undefined && (
        <>
          <span className="font-semibold text-foreground">{total.toLocaleString()}</span>{" "}
          {total === 1 ? itemLabel : (itemLabelPlural ?? `${itemLabel}s`)}
          {filtered && " matching filters"}
        </>
      )}
    </p>
  );
}
