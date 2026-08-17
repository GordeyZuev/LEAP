"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Play, CheckCircle2, XCircle, Zap } from "lucide-react";
import { cn, extractApiError } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { useToast } from "@/hooks/use-toast";
import { useUrlListState } from "@/hooks/use-url-list-state";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { SegmentedFilter, ACTIVE_STATUS_OPTIONS } from "@/components/filters/segmented-filter";
import { FilterChips, type FilterChipItem } from "@/components/filters/filter-chips";
import { PER_PAGE_AUTOMATION } from "@/lib/constants";
import { ActionButton } from "@/components/ui/action-button";
import { Toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { TableRowsSkeleton } from "@/components/ui/list-skeleton";
import { Pagination } from "@/components/ui/pagination";
import { ResultCount } from "@/components/ui/result-count";
import { SortableTh } from "@/components/ui/sortable-th";
import { TABLE_BODY, TABLE_CARD, TABLE_ROW } from "@/lib/table-classes";

interface AutomationJob {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  run_count: number;
  created_at?: string | null;
}

interface AutomationJobListResponse {
  items: AutomationJob[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

const SORT_OPTIONS = [
  { value: "name",        label: "Name" },
  { value: "last_run_at", label: "Last run" },
  { value: "next_run_at", label: "Next run" },
  { value: "run_count",   label: "Run count" },
  { value: "created_at",  label: "Created" },
];

const SORT_ALLOWED = SORT_OPTIONS.map((o) => o.value);

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const isCurrentYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    ...(isCurrentYear ? {} : { year: "numeric" }),
    hour: "2-digit",
    minute: "2-digit",
  });
}

function AutomationContent() {
  const qc = useQueryClient();
  const { toast, show: showToast, dismiss: dismissToast } = useToast();

  // Filters live in the URL so a filtered view is shareable and survives reload.
  const list = useUrlListState({
    defaultSortBy: "next_run_at",
    defaultSortOrder: "asc",
    allowedSortFields: SORT_ALLOWED,
  });
  const statusFilter = list.getParam("status") ?? "all";

  const { data, isLoading, error, refetch } = useQuery<AutomationJobListResponse>({
    queryKey: ["automation-jobs", list.urlKey],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (list.search) p.set("search", list.search);
      if (statusFilter !== "all") p.set("is_active", statusFilter === "active" ? "true" : "false");
      p.set("sort_by", list.sortBy);
      p.set("sort_order", list.sortOrder);
      p.set("page", String(list.page));
      p.set("per_page", String(PER_PAGE_AUTOMATION));
      const res = await apiClient.get<AutomationJobListResponse>(`/automation/jobs?${p.toString()}`);
      return res.data;
    },
  });

  const runNow = useMutation({
    mutationFn: (id: number) => apiClient.post(`/automation/jobs/${id}/run`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["automation-jobs"] });
      showToast("success", "Job run started");
    },
    onError: (e) => showToast("error", extractApiError(e, "Failed to start job")),
  });

  // Filtering, sorting and paging are done by the API — the page just renders.
  const jobs = data?.items ?? [];
  const sortProps = { sortBy: list.sortBy, sortOrder: list.sortOrder, onSort: list.setSort };

  const chips: FilterChipItem[] = [
    ...(list.search
      ? [{
          key: "search",
          label: `Search: "${list.search}"`,
          onRemove: () => { list.setSearchInput(""); list.setParam("search", null); },
        }]
      : []),
    ...(statusFilter !== "all"
      ? [{
          key: "status",
          label: statusFilter === "active" ? "Active" : "Inactive",
          onRemove: () => list.setParam("status", null),
        }]
      : []),
  ];

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader
        title="Automations"
        actions={
          <Link
            href="/automation/new"
            className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-primary-hover transition-colors"
          >
            <Plus size={16} /> New job
          </Link>
        }
      />

      {/* Filters */}
      <FilterBar
        search={
          <SearchInput
            id="automation-search"
            value={list.searchInput}
            onChange={list.setSearchInput}
            placeholder="By name or description…"
          />
        }
        controls={[
          <SegmentedFilter
            key="status"
            label="Status"
            value={statusFilter}
            options={ACTIVE_STATUS_OPTIONS}
            onChange={(v) => list.setParam("status", v === "all" ? null : v)}
          />,
        ]}
        sort={
          <SortControl
            value={list.sortBy}
            order={list.sortOrder}
            options={SORT_OPTIONS}
            onChange={list.setSort}
            onToggleOrder={list.toggleSortOrder}
          />
        }
        onClearAll={list.hasActiveFilters || list.hasNonDefaultSort ? list.resetAll : undefined}
        chips={<FilterChips chips={chips} />}
      />

      <ResultCount total={data?.total} itemLabel="job" filtered={list.hasActiveFilters} />

      {/* Table */}
      <div className={TABLE_CARD}>
        <table className="w-full min-w-[760px]">
          <thead>
            <tr className="border-b border-border">
              <SortableTh sticky className="px-6 py-3" label="Job" field="name" {...sortProps} />
              <SortableTh sticky className="px-6 py-3" label="Last run" field="last_run_at" {...sortProps} />
              <SortableTh sticky className="px-6 py-3" label="Next run" field="next_run_at" {...sortProps} />
              <SortableTh sticky className="px-6 py-3" label="Runs" field="run_count" {...sortProps} />
              <SortableTh sticky className="px-6 py-3" label="Status" />
              <SortableTh sticky className="px-6 py-3 text-right" label="Actions" />
            </tr>
          </thead>
          <tbody className={TABLE_BODY}>
            {isLoading && <TableRowsSkeleton rows={5} cols={6} />}
            {error && (
              <tr>
                <td colSpan={6} className="p-0">
                  <ErrorState description="Failed to load jobs" onRetry={() => refetch()} />
                </td>
              </tr>
            )}
            {!isLoading && !error && jobs.length === 0 && list.hasActiveFilters && (
              <tr>
                <td colSpan={6} className="p-0">
                  <EmptyState icon={Zap} title="No jobs match your filters" description="Try adjusting or clearing the filters above." />
                </td>
              </tr>
            )}
            {!isLoading && !error && jobs.length === 0 && !list.hasActiveFilters && (
              <tr>
                <td colSpan={6} className="p-0">
                  <EmptyState
                    icon={Zap}
                    title="No automation jobs yet"
                    description="Automation jobs run your pipeline on a schedule. Create the first to put ingestion on autopilot."
                    action={
                      <Link
                        href="/automation/new"
                        className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
                      >
                        <Plus size={16} /> New job
                      </Link>
                    }
                  />
                </td>
              </tr>
            )}
            {jobs.map((job) => (
              <tr key={job.id} className={TABLE_ROW}>
                <td className="px-6 py-4">
                  <Link
                    href={`/automation/${job.id}`}
                    className="text-sm font-medium text-foreground hover:text-primary transition-colors"
                  >
                    {job.name}
                  </Link>
                  {job.description && (
                    <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-xs">{job.description}</p>
                  )}
                </td>
                <td className="px-6 py-4 text-sm text-muted-foreground">{formatDate(job.last_run_at)}</td>
                <td className="px-6 py-4 text-sm text-secondary-foreground font-medium">{formatDate(job.next_run_at)}</td>
                <td className="px-6 py-4 text-sm text-muted-foreground">{job.run_count}</td>
                <td className="px-6 py-4">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 text-sm",
                      job.is_active ? "text-green-600" : "text-muted-foreground"
                    )}
                  >
                    {job.is_active ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                    {job.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex justify-end">
                    <ActionButton
                      size="sm"
                      variant="secondary"
                      onClick={() => runNow.mutate(job.id)}
                      isPending={runNow.isPending && runNow.variables === job.id}
                      icon={<Play size={12} />}
                      pendingLabel="Running…"
                      className="hover:border-primary hover:bg-primary hover:text-white"
                    >
                      Run
                    </ActionButton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && (
        <Pagination
          page={list.page}
          totalPages={data.total_pages}
          total={data.total}
          perPage={PER_PAGE_AUTOMATION}
          onPageChange={list.setPage}
          itemLabel="job"
        />
      )}

      {toast && (
        <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismissToast} />
      )}
    </div>
  );
}

export default function AutomationPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading…</div>}>
      <AutomationContent />
    </Suspense>
  );
}
