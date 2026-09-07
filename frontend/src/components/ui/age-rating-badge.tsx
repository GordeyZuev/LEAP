import { cn } from "@/lib/utils";

/** Product information-product mark (12+). Use on landing, chrome, auth, and public share. */
export const AGE_RATING = "12+";

const DEFAULT_LABEL = "Age rating 12+";

export function AgeRatingBadge({
  className,
  label = DEFAULT_LABEL,
}: {
  className?: string;
  label?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded-sm border border-foreground/60 px-1.5 text-[11px] font-semibold tabular-nums leading-none tracking-tight text-foreground",
        className,
      )}
      title={label}
      aria-label={label}
    >
      {AGE_RATING}
    </span>
  );
}
