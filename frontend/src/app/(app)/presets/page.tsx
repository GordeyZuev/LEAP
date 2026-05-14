"use client";

import Link from "next/link";
import { Suspense, useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { FILTER_CARD, FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";

const PER_PAGE = 24;

const ALLOWED_PLATFORMS = new Set(["youtube", "vk", "yandex_disk"]);

interface PresetItem {
  id: number;
  name: string;
  description: string | null;
  platform: string;
  is_active: boolean;
  created_at: string;
}

interface PresetListResponse {
  items: PresetItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  vk: "VK Video",
  yandex_disk: "Yandex Disk",
};

const PLATFORM_COLORS: Record<string, string> = {
  youtube: "bg-red-100 text-red-600",
  vk: "bg-blue-100 text-blue-600",
  yandex_disk: "bg-yellow-100 text-yellow-700",
};

const SORT_OPTIONS = [
  { value: "created_at", label: "Created" },
  { value: "updated_at", label: "Updated" },
  { value: "name", label: "Name" },
];

const SORT_ALLOWED = new Set(SORT_OPTIONS.map((o) => o.value));

interface PresetsPagedGridProps {
  platform: string;
  activeOnly: boolean;
  sortBy: string;
  sortOrder: string;
}

function PresetsPagedGrid({ platform, activeOnly, sortBy, sortOrder }: PresetsPagedGridProps) {
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery<PresetListResponse>({
    queryKey: ["presets", platform, activeOnly, sortBy, sortOrder, page],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (platform) p.set("platform", platform);
      if (activeOnly) p.set("active_only", "true");
      p.set("sort_by", sortBy);
      p.set("sort_order", sortOrder);
      p.set("page", String(page));
      p.set("per_page", String(PER_PAGE));
      const res = await apiClient.get<PresetListResponse>(`/presets?${p.toString()}`);
      return res.data;
    },
  });

  const presets = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const hasPrev = page > 1;
  const hasNext = page < totalPages;

  return (
    <>
      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-2xl border border-[#D9D9D9] bg-white" />
          ))}
        </div>
      )}

      {error && <p className="text-sm text-red-400">Failed to load presets</p>}

      {!isLoading && !error && presets.length === 0 && (
        <p className="py-16 text-center text-sm text-gray-400">
          {platform || activeOnly ? "No presets match your filters" : "No presets yet"}
        </p>
      )}

      {!isLoading && !error && presets.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {presets.map((p) => (
            <Link
              key={p.id}
              href={`/presets/${p.id}`}
              className="flex flex-col gap-3 rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm transition-all hover:border-[#224C87]/30 hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="flex-1 text-sm font-semibold text-gray-900">{p.name}</span>
                <span
                  className={cn(
                    "inline-flex shrink-0 items-center rounded-full px-2.5 py-1 text-xs font-medium",
                    PLATFORM_COLORS[p.platform] ?? "bg-gray-100 text-gray-500"
                  )}
                >
                  {PLATFORM_LABELS[p.platform] ?? p.platform}
                </span>
              </div>
              {p.description && <p className="line-clamp-2 text-xs text-gray-400">{p.description}</p>}
              <div className="mt-auto flex items-center justify-between">
                <span className={cn("text-xs font-medium", p.is_active ? "text-green-600" : "text-gray-400")}>
                  {p.is_active ? "Active" : "Inactive"}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {data && data.total > 0 && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-gray-600">
            Page {page} of {totalPages}
            <span className="text-gray-400"> · </span>
            {data.total} preset{data.total !== 1 ? "s" : ""}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!hasPrev}
              onClick={() => setPage((pg) => Math.max(1, pg - 1))}
              className="rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={!hasNext}
              onClick={() => setPage((pg) => pg + 1)}
              className="rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function PresetsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const platRaw = searchParams.get("platform");
  const platform = platRaw && ALLOWED_PLATFORMS.has(platRaw) ? platRaw : "";

  const activeOnly = searchParams.get("active_only") === "true";

  const sortByRaw = searchParams.get("sort_by") ?? "created_at";
  const sortBy = SORT_ALLOWED.has(sortByRaw) ? sortByRaw : "created_at";

  const sortOrderRaw = searchParams.get("sort_order") ?? "desc";
  const sortOrder = sortOrderRaw === "asc" ? "asc" : "desc";

  const setParam = useCallback(
    (key: string, value: string | null) => {
      const p = new URLSearchParams(searchParams.toString());
      if (value === null || value === "") p.delete(key);
      else p.set(key, value);
      router.replace(`?${p.toString()}`);
    },
    [router, searchParams]
  );

  const filtersKey = useMemo(
    () => [platform, activeOnly ? "1" : "0", sortBy, sortOrder].join("|"),
    [platform, activeOnly, sortBy, sortOrder]
  );

  const hasActiveFilters = !!platform || activeOnly || sortBy !== "created_at" || sortOrder !== "desc";

  function clearFilters() {
    router.replace("?");
  }

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Output Presets</h1>
        <Link
          href="/presets/new"
          className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1a3d6e]"
        >
          <Plus size={16} /> New preset
        </Link>
      </div>

      <div className={FILTER_CARD}>
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between lg:gap-8">
          <div className="grid flex-1 grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:max-w-4xl xl:grid-cols-4">
            <div className="space-y-1.5 sm:col-span-2 lg:col-span-1 xl:col-span-2">
              <label htmlFor="preset-platform" className={FILTER_LABEL}>
                Platform
              </label>
              <select
                id="preset-platform"
                value={platform}
                onChange={(e) => setParam("platform", e.target.value || null)}
                className={FILTER_CONTROL}
              >
                <option value="">All platforms</option>
                <option value="youtube">YouTube</option>
                <option value="vk">VK Video</option>
                <option value="yandex_disk">Yandex Disk</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <span className={FILTER_LABEL}>Availability</span>
              <label
                className={cn(
                  FILTER_CONTROL,
                  "flex min-h-[2.5rem] cursor-pointer items-center gap-2.5 font-medium text-gray-700"
                )}
              >
                <input
                  type="checkbox"
                  checked={activeOnly}
                  onChange={(e) => setParam("active_only", e.target.checked ? "true" : null)}
                  className="rounded accent-[#224C87]"
                />
                Active only
              </label>
            </div>

            <div className="space-y-1.5">
              <span className={FILTER_LABEL}>Sort by</span>
              <div className="flex gap-1.5">
                <select
                  value={sortBy}
                  onChange={(e) => setParam("sort_by", e.target.value)}
                  className={cn(FILTER_CONTROL, "min-w-[9rem]")}
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
          </div>

          {hasActiveFilters && (
            <div className="space-y-1.5 lg:self-end">
              <span className={FILTER_LABEL} aria-hidden>
                &nbsp;
              </span>
              <button
                type="button"
                onClick={clearFilters}
                className={cn(
                  FILTER_CONTROL,
                  "flex min-h-[2.5rem] items-center gap-1.5 border-gray-200 text-gray-600 hover:bg-gray-50"
                )}
              >
                <X size={14} />
                Reset filters
              </button>
            </div>
          )}
        </div>
      </div>

      <PresetsPagedGrid key={filtersKey} platform={platform} activeOnly={activeOnly} sortBy={sortBy} sortOrder={sortOrder} />
    </div>
  );
}

export default function PresetsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-gray-400">Loading presets…</div>}>
      <PresetsContent />
    </Suspense>
  );
}
