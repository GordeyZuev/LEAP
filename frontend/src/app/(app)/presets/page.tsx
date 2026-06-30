"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, Package } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { FilterBar } from "@/components/filters/filter-bar";
import { SortControl } from "@/components/filters/sort-control";
import { SegmentedFilter, ACTIVE_STATUS_OPTIONS } from "@/components/filters/segmented-filter";
import { FilterMultiSelect } from "@/components/filters/filter-multi-select";
import { Pagination } from "@/components/ui/pagination";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { CardGridSkeleton } from "@/components/ui/list-skeleton";
import { usePlatforms } from "@/hooks/use-references";
import { PER_PAGE_PRESETS } from "@/lib/constants";

const ALLOWED_PLATFORMS = new Set(["youtube", "vk_video", "yandex_disk", "zoom"]);

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
  youtube: "bg-red-100 text-red-600 dark:bg-red-500/15 dark:text-red-300",
  vk: "bg-blue-100 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300",
  yandex_disk: "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-300",
};

const SORT_OPTIONS = [
  { value: "created_at", label: "Created" },
  { value: "updated_at", label: "Updated" },
  { value: "name",       label: "Name" },
];

const SORT_ALLOWED = new Set(SORT_OPTIONS.map((o) => o.value));

type ActiveFilter = "all" | "active" | "inactive";

// ---------------------------------------------------------------------------
// Filters (read from URL)
// ---------------------------------------------------------------------------

interface PresetFilters {
  platforms: string[];
  activeFilter: ActiveFilter;
  sortBy: string;
  sortOrder: "asc" | "desc";
}

function filtersFromUrl(sp: URLSearchParams): PresetFilters {
  const platforms = sp.getAll("platform").filter((p) => ALLOWED_PLATFORMS.has(p));
  const activeRaw = sp.get("active_filter");
  const activeFilter: ActiveFilter =
    activeRaw === "active" ? "active" : activeRaw === "inactive" ? "inactive" : "all";
  const sortByRaw = sp.get("sort_by") ?? "created_at";
  const sortBy = SORT_ALLOWED.has(sortByRaw) ? sortByRaw : "created_at";
  const sortOrder: "asc" | "desc" = sp.get("sort_order") === "asc" ? "asc" : "desc";
  return { platforms, activeFilter, sortBy, sortOrder };
}

// ---------------------------------------------------------------------------
// PresetsPagedGrid
// ---------------------------------------------------------------------------

interface PresetsPagedGridProps {
  platforms: string[];
  activeFilter: ActiveFilter;
  sortBy: string;
  sortOrder: string;
  page: number;
  onPageChange: (page: number) => void;
}

function PresetsPagedGrid({ platforms, activeFilter, sortBy, sortOrder, page, onPageChange }: PresetsPagedGridProps) {
  const { data, isLoading, error, refetch } = useQuery<PresetListResponse>({
    queryKey: ["presets", platforms, activeFilter, sortBy, sortOrder, page],
    queryFn: async () => {
      const p = new URLSearchParams();
      platforms.forEach((pl) => p.append("platform", pl));
      if (activeFilter === "active") p.set("active_only", "true");
      if (activeFilter === "inactive") p.set("active_only", "false");
      p.set("sort_by", sortBy);
      p.set("sort_order", sortOrder);
      p.set("page", String(page));
      p.set("per_page", String(PER_PAGE_PRESETS));
      const res = await apiClient.get<PresetListResponse>(`/presets?${p.toString()}`);
      return res.data;
    },
  });

  // Self-correct out-of-range `page` (e.g. after deletes, shared stale links).
  useEffect(() => {
    if (!data) return;
    if (data.total === 0) {
      if (page !== 1) onPageChange(1);
    } else if (page > data.total_pages) {
      onPageChange(data.total_pages);
    }
  }, [data, page, onPageChange]);

  const presets = data?.items ?? [];

  return (
    <>
      {isLoading && <CardGridSkeleton />}

      {error && <ErrorState description="Failed to load presets" onRetry={() => refetch()} />}

      {!isLoading && !error && presets.length === 0 && (
        <EmptyState
          icon={Package}
          title={platforms.length || activeFilter !== "all" ? "No presets match your filters" : "No presets yet"}
          description={
            platforms.length || activeFilter !== "all"
              ? "Try adjusting or clearing the filters above."
              : "Presets capture per-platform upload settings. Create one to get started."
          }
        />
      )}

      {!isLoading && !error && presets.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {presets.map((p) => (
            <Link
              key={p.id}
              href={`/presets/${p.id}`}
              className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-sm transition-all hover:border-primary/30 hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="flex-1 text-sm font-semibold text-foreground">{p.name}</span>
                <span
                  className={cn(
                    "inline-flex shrink-0 items-center rounded-full px-2.5 py-1 text-xs font-medium",
                    PLATFORM_COLORS[p.platform] ?? "bg-muted text-muted-foreground"
                  )}
                >
                  {PLATFORM_LABELS[p.platform] ?? p.platform}
                </span>
              </div>
              {p.description && <p className="line-clamp-2 text-xs text-muted-foreground">{p.description}</p>}
              <div className="mt-auto flex items-center justify-between">
                <span className={cn("text-xs font-medium", p.is_active ? "text-green-600" : "text-muted-foreground")}>
                  {p.is_active ? "Active" : "Inactive"}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {data && (
        <Pagination
          page={page}
          totalPages={data.total_pages}
          total={data.total}
          perPage={PER_PAGE_PRESETS}
          onPageChange={onPageChange}
          itemLabel="preset"
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main content
// ---------------------------------------------------------------------------

function PresetsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: platformOptions = [] } = usePlatforms();
  const urlKey = searchParams.toString();
  const urlPage = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);

  const filters = useMemo(() => filtersFromUrl(new URLSearchParams(urlKey)), [urlKey]);

  // Filter key excludes `page` so paging doesn't remount the grid (and its query state).
  const filterKey = useMemo(() => {
    const p = new URLSearchParams(urlKey);
    p.delete("page");
    return p.toString();
  }, [urlKey]);

  const setPage = useCallback(
    (next: number) => {
      const p = new URLSearchParams(searchParams.toString());
      if (next <= 1) p.delete("page");
      else p.set("page", String(next));
      router.replace(`?${p.toString()}`);
    },
    [router, searchParams],
  );

  // Instant apply: every control writes straight to the URL (drops `page`).
  const commit = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      const p = new URLSearchParams(urlKey);
      mutate(p);
      p.delete("page");
      router.replace(`?${p.toString()}`);
    },
    [urlKey, router],
  );

  const hasActiveFilters =
    filters.platforms.length > 0 ||
    filters.activeFilter !== "all" ||
    filters.sortBy !== "created_at" ||
    filters.sortOrder !== "desc";

  const resetFilters = useCallback(() => router.replace("?"), [router]);

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader
        title="Output Presets"
        actions={
          <Link
            href="/presets/new"
            className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
          >
            <Plus size={16} /> New preset
          </Link>
        }
      />

      {/* Filters */}
      <FilterBar
        controls={[
          <FilterMultiSelect<string>
            key="platform"
            label="Platform"
            emptySummary="All platforms"
            value={filters.platforms}
            options={platformOptions}
            onChange={(next) =>
              commit((p) => {
                p.delete("platform");
                next.forEach((pl) => p.append("platform", pl));
              })
            }
          />,
          <SegmentedFilter
            key="status"
            label="Status"
            value={filters.activeFilter}
            options={ACTIVE_STATUS_OPTIONS}
            onChange={(v) =>
              commit((p) => {
                if (v === "all") p.delete("active_filter");
                else p.set("active_filter", v);
              })
            }
          />,
        ]}
        sort={
          <SortControl
            value={filters.sortBy}
            order={filters.sortOrder}
            options={SORT_OPTIONS}
            onChange={(f) =>
              commit((p) => {
                if (f === "created_at") p.delete("sort_by");
                else p.set("sort_by", f);
              })
            }
            onToggleOrder={() =>
              commit((p) => {
                if (filters.sortOrder === "desc") p.set("sort_order", "asc");
                else p.delete("sort_order");
              })
            }
          />
        }
        onClearAll={hasActiveFilters ? resetFilters : undefined}
      />

      <PresetsPagedGrid
        key={filterKey}
        platforms={filters.platforms}
        activeFilter={filters.activeFilter}
        sortBy={filters.sortBy}
        sortOrder={filters.sortOrder}
        page={urlPage}
        onPageChange={setPage}
      />
    </div>
  );
}

export default function PresetsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading presets…</div>}>
      <PresetsContent />
    </Suspense>
  );
}
