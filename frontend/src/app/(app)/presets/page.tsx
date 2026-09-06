"use client";

import Link from "next/link";
import { Suspense, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { SearchInput } from "@/components/filters/search-input";
import { FilterChips, type FilterChipItem } from "@/components/filters/filter-chips";
import { ResultCount } from "@/components/ui/result-count";
import { ActionButton } from "@/components/ui/action-button";
import { useUrlListState } from "@/hooks/use-url-list-state";

const ALLOWED_PLATFORMS = new Set<string>(["youtube", "yandex_disk"]);

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

const SORT_ALLOWED = SORT_OPTIONS.map((o) => o.value);

type ActiveFilter = "all" | "active" | "inactive";

// ---------------------------------------------------------------------------
// PresetsPagedGrid
// ---------------------------------------------------------------------------

interface PresetsPagedGridProps {
  list: ReturnType<typeof useUrlListState>;
  platforms: string[];
  activeFilter: ActiveFilter;
}

function PresetsPagedGrid({ list, platforms, activeFilter }: PresetsPagedGridProps) {
  const page = list.page;
  const onPageChange = list.setPage;

  const { data, isLoading, error, refetch } = useQuery<PresetListResponse>({
    queryKey: ["presets", list.urlKey],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (list.search) p.set("search", list.search);
      platforms.forEach((pl) => p.append("platform", pl));
      if (activeFilter !== "all") p.set("is_active", activeFilter === "active" ? "true" : "false");
      p.set("sort_by", list.sortBy);
      p.set("sort_order", list.sortOrder);
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
      <ResultCount total={data?.total} itemLabel="preset" filtered={list.hasActiveFilters} />

      {isLoading && <CardGridSkeleton />}

      {error && <ErrorState description="Failed to load presets" onRetry={() => refetch()} />}

      {!isLoading && !error && presets.length === 0 && (
        list.hasActiveFilters ? (
          <EmptyState
            icon={Package}
            title="No presets match your filters"
            description="Try adjusting or clearing the filters above."
            action={
              <ActionButton variant="secondary" onClick={list.resetAll}>
                Reset filters
              </ActionButton>
            }
          />
        ) : (
          <EmptyState
            icon={Package}
            title="No presets yet"
            description="Presets capture per-platform upload settings. Create one to get started."
          />
        )
      )}

      {!isLoading && !error && presets.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {presets.map((p, index) => (
            <div key={p.id} className="animate-card-in" style={{ animationDelay: `${index * 30}ms` }}>
            <Link
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
            </div>
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
  const { data: platformOptions = [] } = usePlatforms();

  // Filters live in the URL so a filtered view is shareable and survives reload.
  const list = useUrlListState({
    defaultSortBy: "created_at",
    defaultSortOrder: "desc",
    allowedSortFields: SORT_ALLOWED,
  });
  const platforms = list.getAllParams("platform").filter((p) => ALLOWED_PLATFORMS.has(p));
  const activeFilterRaw = list.getParam("active_filter");
  const activeFilter: ActiveFilter =
    activeFilterRaw === "active" ? "active" : activeFilterRaw === "inactive" ? "inactive" : "all";

  const chips: FilterChipItem[] = [
    ...(list.search
      ? [{
          key: "search",
          label: `Search: "${list.search}"`,
          onRemove: () => { list.setSearchInput(""); list.setParam("search", null); },
        }]
      : []),
    ...platforms.map((pl) => ({
      key: `platform:${pl}`,
      label: PLATFORM_LABELS[pl] ?? pl,
      onRemove: () => list.setMultiParam("platform", platforms.filter((x) => x !== pl)),
    })),
    ...(activeFilter !== "all"
      ? [{
          key: "active_filter",
          label: activeFilter === "active" ? "Active" : "Inactive",
          onRemove: () => list.setParam("active_filter", null),
        }]
      : []),
  ];

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
        search={
          <SearchInput
            id="presets-search"
            value={list.searchInput}
            onChange={list.setSearchInput}
            placeholder="By name or description…"
          />
        }
        controls={[
          <FilterMultiSelect<string>
            key="platform"
            label="Platform"
            emptySummary="All platforms"
            value={platforms}
            options={platformOptions.filter((o) => ALLOWED_PLATFORMS.has(o.value))}
            onChange={(next) => list.setMultiParam("platform", next)}
          />,
          <SegmentedFilter
            key="status"
            label="Status"
            value={activeFilter}
            options={ACTIVE_STATUS_OPTIONS}
            onChange={(v) => list.setParam("active_filter", v === "all" ? null : v)}
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

      <PresetsPagedGrid list={list} platforms={platforms} activeFilter={activeFilter} />
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
