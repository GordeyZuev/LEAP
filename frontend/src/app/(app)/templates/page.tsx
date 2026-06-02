"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { useDebounce } from "@/hooks/use-debounce";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { SegmentedFilter, ACTIVE_STATUS_OPTIONS } from "@/components/filters/segmented-filter";
import { Pagination } from "@/components/ui/pagination";
import { DEBOUNCE_SEARCH, PER_PAGE_TEMPLATES } from "@/lib/constants";

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

  // Self-correct out-of-range `page` (e.g. after deletes, shared stale links).
  useEffect(() => {
    if (!data) return;
    if (data.total === 0) {
      if (urlPage !== 1) setPage(1);
    } else if (urlPage > data.total_pages) {
      setPage(data.total_pages);
    }
    // setPage closes over searchParams via router; safe to omit from deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, urlPage]);

  const templates = data?.items ?? [];

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <div className="mb-5 flex min-h-[2.5rem] flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Templates</h1>
        <Link
          href="/templates/new"
          className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1a3d6e]"
        >
          <Plus size={16} />
          New template
        </Link>
      </div>

      {/* Filters */}
      <FilterBar
        search={
          <SearchInput
            id="templates-search"
            value={searchInput}
            onChange={setSearchInput}
            placeholder="By template name…"
          />
        }
        controls={[
          <SegmentedFilter
            key="status"
            label="Status"
            value={isActiveFilter}
            options={ACTIVE_STATUS_OPTIONS}
            onChange={(v) => setParam("is_active", v === "all" ? null : v === "active" ? "true" : "false")}
          />,
        ]}
        sort={
          <SortControl
            value={sortBy}
            order={sortOrder}
            options={SORT_OPTIONS}
            onChange={(f) => setParam("sort_by", f)}
            onToggleOrder={() => setParam("sort_order", sortOrder === "desc" ? "asc" : "desc")}
          />
        }
        onClearAll={hasActiveFilters ? resetFilters : undefined}
      />

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

      {data && (
        <Pagination
          page={urlPage}
          totalPages={data.total_pages}
          total={data.total}
          perPage={PER_PAGE_TEMPLATES}
          onPageChange={setPage}
          itemLabel="template"
          className="mt-5"
        />
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
