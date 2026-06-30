"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Play, CheckCircle2, XCircle, Zap } from "lucide-react";
import { cn, extractApiError } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { useDebounce } from "@/hooks/use-debounce";
import { useToast } from "@/hooks/use-toast";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { SegmentedFilter, ACTIVE_STATUS_OPTIONS } from "@/components/filters/segmented-filter";
import { DEBOUNCE_SEARCH } from "@/lib/constants";
import { ActionButton } from "@/components/ui/action-button";
import { Toast } from "@/components/ui/toast";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { TableRowsSkeleton } from "@/components/ui/list-skeleton";

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
}

const SORT_OPTIONS = [
  { value: "name",        label: "Name" },
  { value: "last_run_at", label: "Last run" },
  { value: "next_run_at", label: "Next run" },
  { value: "run_count",   label: "Run count" },
];

type StatusFilter = "all" | "active" | "inactive";
type SortField = "name" | "last_run_at" | "next_run_at" | "run_count";

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

function sortJobs(items: AutomationJob[], sortBy: SortField, sortOrder: "asc" | "desc"): AutomationJob[] {
  return [...items].sort((a, b) => {
    let cmp = 0;
    if (sortBy === "name") {
      cmp = a.name.localeCompare(b.name);
    } else if (sortBy === "last_run_at") {
      cmp = (a.last_run_at ?? "").localeCompare(b.last_run_at ?? "");
    } else if (sortBy === "next_run_at") {
      cmp = (a.next_run_at ?? "").localeCompare(b.next_run_at ?? "");
    } else if (sortBy === "run_count") {
      cmp = a.run_count - b.run_count;
    }
    return sortOrder === "asc" ? cmp : -cmp;
  });
}

function AutomationContent() {
  const qc = useQueryClient();
  const { toast, show: showToast, dismiss: dismissToast } = useToast();

  const [searchInput, setSearchInput] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortField>("next_run_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const debouncedSearch = useDebounce(searchInput, DEBOUNCE_SEARCH);

  const { data, isLoading, error, refetch } = useQuery<AutomationJobListResponse>({
    queryKey: ["automation-jobs"],
    queryFn: async () => {
      const res = await apiClient.get<AutomationJobListResponse>("/automation/jobs?per_page=50");
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

  const hasActiveFilters =
    !!debouncedSearch ||
    statusFilter !== "all" ||
    sortBy !== "next_run_at" ||
    sortOrder !== "asc";

  function resetFilters() {
    setSearchInput("");
    setStatusFilter("all");
    setSortBy("next_run_at");
    setSortOrder("asc");
  }

  const allJobs = useMemo(() => data?.items ?? [], [data]);

  const visibleJobs = useMemo(() => {
    const filtered = allJobs.filter((j) => {
      if (debouncedSearch) {
        const q = debouncedSearch.toLowerCase();
        if (!j.name.toLowerCase().includes(q) && !(j.description ?? "").toLowerCase().includes(q)) return false;
      }
      if (statusFilter === "active" && !j.is_active) return false;
      if (statusFilter === "inactive" && j.is_active) return false;
      return true;
    });
    return sortJobs(filtered, sortBy, sortOrder);
  }, [allJobs, debouncedSearch, statusFilter, sortBy, sortOrder]);

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
            value={searchInput}
            onChange={setSearchInput}
            placeholder="By name or description…"
          />
        }
        controls={[
          <SegmentedFilter
            key="status"
            label="Status"
            value={statusFilter}
            options={ACTIVE_STATUS_OPTIONS}
            onChange={(v) => setStatusFilter(v)}
          />,
        ]}
        sort={
          <SortControl
            value={sortBy}
            order={sortOrder}
            options={SORT_OPTIONS}
            onChange={(f) => setSortBy(f as SortField)}
            onToggleOrder={() => setSortOrder((o) => (o === "desc" ? "asc" : "desc"))}
          />
        }
        onClearAll={hasActiveFilters ? resetFilters : undefined}
      />

      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-x-auto">
        <table className="w-full min-w-[760px]">
          <thead>
            <tr className="border-b border-border">
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Job</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Last run</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Next run</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Runs</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">Status</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wide">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && <TableRowsSkeleton rows={5} cols={6} />}
            {error && (
              <tr>
                <td colSpan={6} className="p-0">
                  <ErrorState description="Failed to load jobs" onRetry={() => refetch()} />
                </td>
              </tr>
            )}
            {!isLoading && !error && allJobs.length === 0 && (
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
            {!isLoading && !error && allJobs.length > 0 && visibleJobs.length === 0 && (
              <tr>
                <td colSpan={6} className="p-0">
                  <EmptyState icon={Zap} title="No jobs match your filters" description="Try adjusting or clearing the filters above." />
                </td>
              </tr>
            )}
            {visibleJobs.map((job) => (
              <tr key={job.id} className="hover:bg-muted transition-colors">
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
