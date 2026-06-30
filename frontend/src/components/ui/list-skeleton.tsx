import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Loading placeholder for a responsive card grid. Mirrors the real grid
 * (1 / 2 / 3 columns) so the layout doesn't jump when data arrives.
 */
export function CardGridSkeleton({ count = 6, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3", className)}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex h-28 flex-col gap-3 rounded-2xl border border-border bg-card p-5">
          <div className="flex items-start justify-between gap-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="h-3 w-1/3" />
          <Skeleton className="mt-auto h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}

/**
 * Loading placeholder rows for a table body. Render inside `<tbody>`.
 */
export function TableRowsSkeleton({ rows = 5, cols }: { rows?: number; cols: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c} className="px-6 py-4">
              <Skeleton className={cn("h-4", c === 0 ? "w-40" : "w-20")} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
