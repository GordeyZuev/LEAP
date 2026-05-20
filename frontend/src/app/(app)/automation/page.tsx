"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Play, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { useDebounce } from "@/hooks/use-debounce";
import { FilterSelect } from "@/components/recordings/filter-select";
import { DEBOUNCE_SEARCH } from "@/lib/constants";
import {
  FILTER_CARD,
  FILTER_CONTROL,
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
} from "@/lib/filter-field-classes";

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

  const [searchInput, setSearchInput] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortField>("next_run_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const debouncedSearch = useDebounce(searchInput, DEBOUNCE_SEARCH);

  const { data, isLoading, error } = useQuery<AutomationJobListResponse>({
    queryKey: ["automation-jobs"],
    queryFn: async () => {
      const res = await apiClient.get<AutomationJobListResponse>("/automation/jobs?per_page=50");
      return res.data;
    },
  });

  const runNow = useMutation({
    mutationFn: (id: number) => apiClient.post(`/automation/jobs/${id}/run`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automation-jobs"] }),
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

  const allJobs = data?.items ?? [];

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
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Automations</h1>
        <Link
          href="/automation/new"
          className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] transition-colors"
        >
          <Plus size={16} /> New job
        </Link>
      </div>

      {/* Search toolbar */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1 space-y-1.5" style={{ maxWidth: "22rem" }}>
          <label htmlFor="automation-search" className={FILTER_LABEL}>Search</label>
          <input
            id="automation-search"
            type="search"
            placeholder="By name or description…"
            autoComplete="off"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className={FILTER_CONTROL}
          />
        </div>
      </div>

      {/* Filter card */}
      <div className={FILTER_CARD}>
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-12 lg:items-end">
          {/* Status */}
          <div className="lg:col-span-4">
            <span className={FILTER_LABEL}>Status</span>
            <div className={FILTER_SEGMENT_WRAP}>
              {(["all", "active", "inactive"] as StatusFilter[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  className={cn(
                    FILTER_SEGMENT_BTN,
                    statusFilter === v ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                  )}
                  onClick={() => setStatusFilter(v)}
                >
                  {v === "all" ? "All" : v === "active" ? "Active" : "Inactive"}
                </button>
              ))}
            </div>
          </div>

          {/* Sort */}
          <div className="lg:col-span-4">
            <span className={FILTER_LABEL}>Sort by</span>
            <div className="flex gap-1.5">
              <FilterSelect
                value={sortBy}
                options={SORT_OPTIONS}
                onChange={(v) => setSortBy(v as SortField)}
                className="flex-1 min-w-0"
              />
              <button
                type="button"
                title={sortOrder === "desc" ? "Descending" : "Ascending"}
                onClick={() => setSortOrder((o) => (o === "desc" ? "asc" : "desc"))}
                className={cn(FILTER_CONTROL, "w-11 shrink-0 px-0 text-center font-mono")}
              >
                {sortOrder === "desc" ? "↓" : "↑"}
              </button>
            </div>
          </div>

          {/* Reset */}
          <div className="lg:col-span-4">
            <span className={FILTER_LABEL} aria-hidden>&nbsp;</span>
            <button
              type="button"
              onClick={resetFilters}
              disabled={!hasActiveFilters}
              className="w-full min-h-[2.5rem] rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#D9D9D9]">
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Job</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Last run</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Next run</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Runs</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wide">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#D9D9D9]">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-gray-400">Loading…</td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-red-400">Failed to load jobs</td>
              </tr>
            )}
            {!isLoading && !error && allJobs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-gray-400">
                  No automation jobs.{" "}
                  <Link href="/automation/new" className="text-[#224C87] hover:underline">
                    Create the first →
                  </Link>
                </td>
              </tr>
            )}
            {!isLoading && !error && allJobs.length > 0 && visibleJobs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-gray-400">
                  No jobs match your filters
                </td>
              </tr>
            )}
            {visibleJobs.map((job) => (
              <tr key={job.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-4">
                  <Link
                    href={`/automation/${job.id}`}
                    className="text-sm font-medium text-gray-900 hover:text-[#224C87] transition-colors"
                  >
                    {job.name}
                  </Link>
                  {job.description && (
                    <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{job.description}</p>
                  )}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">{formatDate(job.last_run_at)}</td>
                <td className="px-6 py-4 text-sm text-gray-700 font-medium">{formatDate(job.next_run_at)}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{job.run_count}</td>
                <td className="px-6 py-4">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 text-sm",
                      job.is_active ? "text-green-600" : "text-gray-400"
                    )}
                  >
                    {job.is_active ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                    {job.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex justify-end">
                    <button
                      onClick={() => runNow.mutate(job.id)}
                      disabled={runNow.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border border-[#D9D9D9] bg-white hover:bg-[#224C87] hover:text-white hover:border-[#224C87] disabled:opacity-40 transition-colors"
                    >
                      <Play size={12} /> Run
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function AutomationPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-gray-400">Loading…</div>}>
      <AutomationContent />
    </Suspense>
  );
}
