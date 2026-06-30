import { cn } from "@/lib/utils";

/**
 * Loading placeholder. Compose with width/height/rounding utilities via
 * `className` to match the shape of the content being loaded.
 */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-muted", className)} />;
}
