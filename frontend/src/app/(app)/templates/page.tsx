"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { useDebounce } from "@/hooks/use-debounce";
import { DEBOUNCE_SEARCH, PER_PAGE_TEMPLATES } from "@/lib/constants";
import {
  FILTER_CARD,
  FILTER_CONTROL,
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
} from "@/lib/filter-field-classes";

interface TemplateListItem {
  id: number;
  name: string;
  description: string | null;
  is_draft: boolean;
  is_active: boolean;
  used_count: number;
  created_at: string;
  updated_at: string;
}

interface TemplateListResponse {
  items: TemplateListItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

const SORT_OPTIONS = [
  { value: "created_at", label: "Created" },
  { value: "updated_at", label: "Updated" },
  { value: "name",       label: "Name" },
  { value: "used_count", label: "Used count" },
];

const SORT_ALLOWED = new Set(SORT_OPTIONS.map((o) => o.value));

type IsActiveFilter = "all" | "active" | "inactive";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function TemplatesContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlKey = searchParams.toString();

  const urlSearch = searchParams.get("search") ?? "";
  const isActiveRaw = searchParams.get("is_active");
  const isActiveFilter: IsActiveFilter =
    isActiveRaw === "true" ? "active" : isActiveRaw === "false" ? "inactive" : "all";
  const sortByRaw = searchParams.get("sort_by") ?? "created_at";
  const sortBy = SORT_ALLOWED.has(sortByRaw) ? sortByRaw : "created_at";
  const sortOrder: "asc" | "desc" = searchParams.get("sort_order") === "asc" ? "asc" : "desc";
  const urlPage = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);

  const [searchInput, setSearchInput] = useState(urlSearch);
  const debouncedSearch = useDebounce(searchInput, DEBOUNCE_SEARCH);

  const [prevUrlKey, setPrevUrlKey] = useState(urlKey);
  if (urlKey !== prevUrlKey) {
    setPrevUrlKey(urlKey);
    setSearchInput(searchParams.get("search") ?? "");
  }

  const lastAppliedSearchRef = useRef(urlSearch);
  useEffect(() => {
    const trimmed = debouncedSearch.trim();
    if (trimmed === lastAppliedSearchRef.current) return;
    lastAppliedSearchRef.current = trimmed;
    const p = new URLSearchParams(searchParams.toString());
    if (trimmed) p.set("search", trimmed);
    else p.delete("search");
    p.delete("page");
    router.replace(`?${p.toString()}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  function setParam(key: string, value: string | null) {
    const p = new URLSearchParams(searchParams.toString());
    if (value === null || value === "") p.delete(key);
    else p.set(key, value);
    p.delete("page");
    router.replace(`?${p.toString()}`);
  }

  function setPage(page: number) {
    const p = new URLSearchParams(searchParams.toString());
    if (page === 1) p.delete("page");
    else p.set("page", String(page));
    router.replace(`?${p.toString()}`);
  }

  function resetFilters() {
    setSearchInput("");
    lastAppliedSearchRef.current = "";
    router.replace("?");
  }

  const hasActiveFilters =
    !!urlSearch ||
    isActiveFilter !== "all" ||
    sortBy !== "created_at" ||
    sortOrder !== "desc";

  const { data, isLoading, error } = useQuery<TemplateListResponse>({
    queryKey: ["templates", urlSearch, isActiveFilter, sortBy, sortOrder, urlPage],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (urlSearch) p.set("search", urlSearch);
      if (isActiveFilter === "active") p.set("is_active", "true");
      if (isActiveFilter === "inactive") p.set("is_active", "false");
      p.set("sort_by", sortBy);
      p.set("sort_order", sortOrder);
      p.set("page", String(urlPage));
      p.set("per_page", String(PER_PAGE_TEMPLATES));
      const res = await apiClient.get<TemplateListResponse>(`/templates?${p.toString()}`);
      return res.data;
    },
  });

  const templates = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const hasPrev = urlPage > 1;
  const hasNext = urlPage < totalPages;

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Templates</h1>
        <Link
          href="/templates/new"
          className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1a3d6e]"
        >
          <Plus size={16} />
          New template
        </Link>
      </div>

      {/* Search toolbar — только поиск */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1 space-y-1.5" style={{ maxWidth: "22rem" }}>
          <label htmlFor="templates-search" className={FILTER_LABEL}>
            Search
          </label>
          <input
            id="templates-search"
            type="search"
            placeholder="By template name…"
            autoComplete="off"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className={FILTER_CONTROL}
          />
        </div>
      </div>

      {/* Filter card — status + sort + reset */}
      <div className={FILTER_CARD}>
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-12 lg:items-end">
          {/* Status */}
          <div className="lg:col-span-4">
            <span className={FILTER_LABEL}>Status</span>
            <div className={FILTER_SEGMENT_WRAP}>
              {(["all", "active", "inactive"] as IsActiveFilter[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  className={cn(
                    FILTER_SEGMENT_BTN,
                    isActiveFilter === v ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                  )}
                  onClick={() =>
                    setParam("is_active", v === "all" ? null : v === "active" ? "true" : "false")
                  }
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
              <select
                value={sortBy}
                onChange={(e) => setParam("sort_by", e.target.value)}
                className={cn(FILTER_CONTROL, "min-w-[9rem] pr-8")}
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                title={sortOrder === "desc" ? "Descending" : "Ascending"}
                onClick={() => setParam("sort_order", sortOrder === "desc" ? "asc" : "desc")}
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
      <div className="overflow-hidden rounded-2xl border border-[#D9D9D9] bg-white shadow-sm">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#D9D9D9]">
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Used
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Updated
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#D9D9D9]">
            {isLoading && (
              <tr>
                <td colSpan={4} className="px-6 py-12 text-center text-sm text-gray-400">
                  Loading…
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={4} className="px-6 py-12 text-center text-sm text-red-400">
                  Failed to load templates
                </td>
              </tr>
            )}
            {!isLoading && !error && templates.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-12 text-center text-sm text-gray-400">
                  {hasActiveFilters ? "No templates match your filters" : "No templates yet"}
                </td>
              </tr>
            )}
            {templates.map((t) => (
              <tr key={t.id} className="transition-colors hover:bg-gray-50">
                <td className="px-6 py-4">
                  <div>
                    <Link
                      href={`/templates/${t.id}`}
                      className="text-sm font-medium text-gray-900 transition-colors hover:text-[#224C87]"
                    >
                      {t.name}
                    </Link>
                  </div>
                  {t.description && (
                    <p className="mt-0.5 max-w-xs truncate text-xs text-gray-400">{t.description}</p>
                  )}
                </td>
                <td className="px-6 py-4">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium",
                      t.is_draft
                        ? "bg-yellow-100 text-yellow-700"
                        : t.is_active
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                    )}
                  >
                    {t.is_draft ? "Draft" : t.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">{t.used_count}×</td>
                <td className="px-6 py-4 text-sm text-gray-500">{formatDate(t.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.total > 0 && (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-gray-600">
            Page {urlPage} of {totalPages}
            <span className="text-gray-400"> · </span>
            {data.total} template{data.total !== 1 ? "s" : ""}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!hasPrev}
              onClick={() => setPage(urlPage - 1)}
              className="rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={!hasNext}
              onClick={() => setPage(urlPage + 1)}
              className="rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TemplatesPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-gray-400">Loading templates…</div>}>
      <TemplatesContent />
    </Suspense>
  );
}
