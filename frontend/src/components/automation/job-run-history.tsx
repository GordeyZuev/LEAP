"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock, SkipForward, XCircle } from "lucide-react";
import { apiClient } from "@/api/client";
import { cn, formatDateTimeShort } from "@/lib/utils";
import { EmptyState } from "@/components/ui/empty-state";
import { TableRowsSkeleton } from "@/components/ui/list-skeleton";
import { SortableTh } from "@/components/ui/sortable-th";
import { TABLE_BODY, TABLE_CARD, TABLE_ROW } from "@/lib/table-classes";

interface JobRun {
  id: number;
  status: string;
  trigger: string;
  started_at: string;
  finished_at: string;
  duration_seconds: number | null;
  synced_count: number;
  recordings_found: number;
  matched_count: number;
  processed_count: number;
  error: string | null;
}

interface JobRunListResponse {
  items: JobRun[];
  total: number;
}

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle2; label: string; className: string }> = {
  SUCCESS: { icon: CheckCircle2, label: "Success", className: "text-green-600" },
  FAILED: { icon: XCircle, label: "Failed", className: "text-red-600" },
  SKIPPED: { icon: SkipForward, label: "Skipped", className: "text-muted-foreground" },
};

function formatRunDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

/**
 * Execution history for one automation job.
 *
 * A scheduled job is otherwise unverifiable: the job row only keeps
 * `last_run_at`, so "ran and did nothing" and "crashed" look identical.
 */
export function JobRunHistory({ jobId }: { jobId: number }) {
  const { data, isLoading } = useQuery<JobRunListResponse>({
    queryKey: ["automation-job-runs", jobId],
    queryFn: async () =>
      (await apiClient.get<JobRunListResponse>(`/automation/jobs/${jobId}/runs?per_page=20`)).data,
  });

  const runs = data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold text-secondary-foreground">Run history</h2>
        {data && data.total > 0 && (
          <span className="text-xs tabular-nums text-muted-foreground">last {runs.length} of {data.total}</span>
        )}
      </div>

      <div className={TABLE_CARD}>
        <table className="w-full min-w-[720px]">
          <thead>
            <tr className="border-b border-border">
              <SortableTh label="Started" className="px-5 py-3" />
              <SortableTh label="Result" className="px-5 py-3" />
              <SortableTh label="Trigger" className="px-5 py-3" />
              <SortableTh label="Duration" className="px-5 py-3" />
              <SortableTh label="Found" className="px-5 py-3" />
              <SortableTh label="Processed" className="px-5 py-3" />
            </tr>
          </thead>
          <tbody className={TABLE_BODY}>
            {isLoading && <TableRowsSkeleton rows={3} cols={6} />}
            {!isLoading && runs.length === 0 && (
              <tr>
                <td colSpan={6} className="p-0">
                  <EmptyState
                    icon={Clock}
                    title="No runs yet"
                    description="Runs appear here once the schedule fires or you start the job manually."
                  />
                </td>
              </tr>
            )}
            {runs.map((run) => {
              const cfg = STATUS_CONFIG[run.status] ?? STATUS_CONFIG.SKIPPED;
              const Icon = cfg.icon;
              return (
                <tr key={run.id} className={TABLE_ROW}>
                  <td className="whitespace-nowrap px-5 py-3 text-sm text-muted-foreground">
                    {formatDateTimeShort(run.started_at)}
                  </td>
                  <td className="px-5 py-3">
                    <span className={cn("inline-flex items-center gap-1.5 text-sm", cfg.className)}>
                      <Icon size={14} className="shrink-0" />
                      {cfg.label}
                    </span>
                    {run.error && (
                      <p className="mt-0.5 max-w-[280px] break-words text-xs text-red-500">{run.error}</p>
                    )}
                  </td>
                  <td className="px-5 py-3 text-sm text-muted-foreground">
                    {run.trigger === "MANUAL" ? "Manual" : "Schedule"}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3 tabular-nums text-sm text-muted-foreground">
                    {formatRunDuration(run.duration_seconds)}
                  </td>
                  <td className="px-5 py-3 tabular-nums text-sm text-muted-foreground">{run.recordings_found}</td>
                  <td className="px-5 py-3 tabular-nums text-sm text-secondary-foreground">{run.processed_count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
