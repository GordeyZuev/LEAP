"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { apiClient } from "@/api/client";
import { formatDateTimeShort } from "@/lib/utils";
import { EmptyState } from "@/components/ui/empty-state";
import { TableRowsSkeleton } from "@/components/ui/list-skeleton";
import { Pagination } from "@/components/ui/pagination";
import { SortableTh } from "@/components/ui/sortable-th";
import { TABLE_BODY, TABLE_CARD, TABLE_ROW } from "@/lib/table-classes";

interface AuditEntry {
  id: number;
  actor_email: string;
  action: string;
  target_user_id: string | null;
  target_label: string | null;
  details: Record<string, { from?: unknown; to?: unknown } | unknown> | null;
  ip_address: string | null;
  created_at: string;
}

interface AuditLogResponse {
  items: AuditEntry[];
  total: number;
  total_pages: number;
}

const ACTION_LABELS: Record<string, string> = {
  "user.updated": "User updated",
  "subscription.assigned": "Plan assigned",
  "subscription.updated": "Plan limits changed",
  "subscription.removed": "Plan removed",
  "plan.created": "Plan created",
  "plan.updated": "Plan updated",
  "plan.deleted": "Plan deleted",
};

/** Renders `{field: {from, to}}` as "field: a → b", falling back to raw values. */
function describeDetails(details: AuditEntry["details"]): string {
  if (!details || Object.keys(details).length === 0) return "—";
  return Object.entries(details)
    .map(([field, value]) => {
      if (value && typeof value === "object" && ("from" in value || "to" in value)) {
        const { from, to } = value as { from?: unknown; to?: unknown };
        return `${field}: ${String(from)} → ${String(to)}`;
      }
      return `${field}: ${String(value)}`;
    })
    .join(", ");
}

const PER_PAGE = 10;

/**
 * Administrative audit trail.
 *
 * Role changes, deactivations and plan assignments were previously untraceable:
 * nothing recorded who did what, so an incident could not be reconstructed.
 */
export function AdminAuditLog() {
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<AuditLogResponse>({
    queryKey: ["admin-audit-log", page],
    queryFn: async () =>
      (await apiClient.get<AuditLogResponse>(`/admin/audit-log?page=${page}&per_page=${PER_PAGE}`)).data,
  });

  const entries = data?.items ?? [];

  return (
    <div className="mt-8">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-foreground">Audit log</h2>
        {data && data.total > 0 && (
          <span className="text-xs tabular-nums text-muted-foreground">{data.total} entries</span>
        )}
      </div>

      <div className={TABLE_CARD}>
        <table className="w-full min-w-[760px]">
          <thead>
            <tr className="border-b border-border">
              <SortableTh label="When" />
              <SortableTh label="Admin" />
              <SortableTh label="Action" />
              <SortableTh label="Target" />
              <SortableTh label="Change" />
            </tr>
          </thead>
          <tbody className={TABLE_BODY}>
            {isLoading && <TableRowsSkeleton rows={4} cols={5} />}
            {!isLoading && entries.length === 0 && (
              <tr>
                <td colSpan={5} className="p-0">
                  <EmptyState
                    icon={ScrollText}
                    title="No administrative actions yet"
                    description="Role changes, plan assignments and deactivations are recorded here."
                  />
                </td>
              </tr>
            )}
            {entries.map((entry) => (
              <tr key={entry.id} className={TABLE_ROW}>
                <td className="whitespace-nowrap px-6 py-3 text-sm text-muted-foreground">
                  {formatDateTimeShort(entry.created_at)}
                </td>
                <td className="px-6 py-3 text-sm text-secondary-foreground">{entry.actor_email}</td>
                <td className="whitespace-nowrap px-6 py-3 text-sm font-medium text-foreground">
                  {ACTION_LABELS[entry.action] ?? entry.action}
                </td>
                <td className="px-6 py-3 text-sm text-muted-foreground">{entry.target_label ?? "—"}</td>
                <td className="px-6 py-3 text-xs text-muted-foreground">{describeDetails(entry.details)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && (
        <Pagination
          page={page}
          totalPages={data.total_pages}
          total={data.total}
          perPage={PER_PAGE}
          onPageChange={setPage}
          itemLabel="entry"
          itemLabelPlural="entries"
        />
      )}
    </div>
  );
}
