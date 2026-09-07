"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchAdminQuotaStats } from "@/api/admin";
import { COUNT_FORMATTER } from "@/components/settings/format";
import { Skeleton } from "@/components/ui/skeleton";
import { TABLE_BODY, TABLE_CARD, TABLE_ROW } from "@/lib/table-classes";
import { SortableTh } from "@/components/ui/sortable-th";

function formatQuotaPeriod(period: number): string {
  const s = String(period);
  if (s.length !== 6) return s;
  const year = Number(s.slice(0, 4));
  const month = Number(s.slice(4, 6));
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function AdminQuotaByPlanSection() {
  const query = useQuery({
    queryKey: ["admin-quota-stats"],
    queryFn: () => fetchAdminQuotaStats(),
    staleTime: 120_000,
  });

  const data = query.data;

  return (
    <div>
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-foreground">Quota usage by plan</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {data
            ? `${formatQuotaPeriod(data.period)} · recordings counted against monthly quotas`
            : "Current month · recordings counted against monthly quotas"}
        </p>
      </div>

      {query.isPending && <Skeleton className="h-32 rounded-2xl" />}

      {query.isError && (
        <p className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
          Unable to load quota statistics.
        </p>
      )}

      {data && data.plans.length === 0 && (
        <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
          No subscribed users yet.
        </p>
      )}

      {data && data.plans.length > 0 && (
        <div className={TABLE_CARD}>
          <table className="w-full min-w-[560px]">
            <thead>
              <tr className="border-b border-border">
                <SortableTh label="Plan" />
                <SortableTh label="Users" />
                <SortableTh label="Recordings" />
                <SortableTh label="Avg / user" />
              </tr>
            </thead>
            <tbody className={TABLE_BODY}>
              {data.plans.map((plan) => (
                <tr key={plan.plan_name} className={TABLE_ROW}>
                  <td className="px-6 py-3.5 text-sm font-medium text-foreground">{plan.plan_name}</td>
                  <td className="px-6 py-3.5 text-sm tabular-nums text-secondary-foreground">
                    {COUNT_FORMATTER.format(plan.total_users)}
                  </td>
                  <td className="px-6 py-3.5 text-sm tabular-nums text-secondary-foreground">
                    {COUNT_FORMATTER.format(plan.total_recordings)}
                  </td>
                  <td className="px-6 py-3.5 text-sm tabular-nums text-secondary-foreground">
                    {plan.avg_recordings_per_user.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
