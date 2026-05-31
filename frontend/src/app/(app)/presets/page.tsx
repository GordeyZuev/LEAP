"use client";

import Link from "next/link";
import { Suspense, useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import {
  FILTER_CARD,
  FILTER_CONTROL,
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
} from "@/lib/filter-field-classes";
import { FilterMultiSelect } from "@/components/recordings/filter-multi-select";
import { FilterSelect } from "@/components/recordings/filter-select";
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
  youtube: "bg-red-100 text-red-600",
  vk: "bg-blue-100 text-blue-600",
  yandex_disk: "bg-yellow-100 text-yellow-700",
};

const SORT_OPTIONS = [
  { value: "created_at", label: "Created" },
  { value: "updated_at", label: "Updated" },
  { value: "name",       label: "Name" },
];

const SORT_ALLOWED = new Set(SORT_OPTIONS.map((o) => o.value));

type ActiveFilter = "all" | "active" | "inactive";

// ---------------------------------------------------------------------------
// Filter draft
// ---------------------------------------------------------------------------

interface PresetFilterDraft {
  platforms: string[];
  activeFilter: ActiveFilter;
  sortBy: string;
  sortOrder: "asc" | "desc";
}

const DEFAULT_DRAFT: PresetFilterDraft = {
  platforms: [],
  activeFilter: "all",
  sortBy: "created_at",
  sortOrder: "desc",
};

function draftFromUrl(sp: URLSearchParams): PresetFilterDraft {
  const platforms = sp.getAll("platform").filter((p) => ALLOWED_PLATFORMS.has(p));
  const activeRaw = sp.get("active_filter");
  const activeFilter: ActiveFilter =
    activeRaw === "active" ? "active" : activeRaw === "inactive" ? "inactive" : "all";
  const sortByRaw = sp.get("sort_by") ?? "created_at";
  const sortBy = SORT_ALLOWED.has(sortByRaw) ? sortByRaw : "created_at";
  const sortOrder: "asc" | "desc" = sp.get("sort_order") === "asc" ? "asc" : "desc";
  return { platforms, activeFilter, sortBy, sortOrder };
}

function draftSignature(d: PresetFilterDraft): string {
  return [d.platforms.slice().sort().join(","), d.activeFilter, d.sortBy, d.sortOrder].join("|");
}

// ---------------------------------------------------------------------------
// PresetsPagedGrid
// ---------------------------------------------------------------------------

interface PresetsPagedGridProps {
  platforms: string[];
  activeFilter: ActiveFilter;
  sortBy: string;
  sortOrder: string;
}

function PresetsPagedGrid({ platforms, activeFilter, sortBy, sortOrder }: PresetsPagedGridProps) {
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery<PresetListResponse>({
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
          {platforms.length || activeFilter !== "all" ? "No presets match your filters" : "No presets yet"}
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

// ---------------------------------------------------------------------------
// Main content
// ---------------------------------------------------------------------------

function PresetsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: platformOptions = [] } = usePlatforms();
  const urlKey = searchParams.toString();

  const [draft, setDraft] = useState<PresetFilterDraft>(() => draftFromUrl(searchParams));
  const [platformDropdownOpen, setPlatformDropdownOpen] = useState(false);

  const patchDraft = useCallback((patch: Partial<PresetFilterDraft>) => {
    setDraft((d) => ({ ...d, ...patch }));
  }, []);

  const appliedDraft = useMemo(() => draftFromUrl(new URLSearchParams(urlKey)), [urlKey]);
  const isDirty = draftSignature(draft) !== draftSignature(appliedDraft);

  const hasAppliedFilters =
    appliedDraft.platforms.length > 0 ||
    appliedDraft.activeFilter !== "all" ||
    appliedDraft.sortBy !== "created_at" ||
    appliedDraft.sortOrder !== "desc";

  function applyFilters() {
    const p = new URLSearchParams();
    draft.platforms.forEach((pl) => p.append("platform", pl));
    if (draft.activeFilter !== "all") p.set("active_filter", draft.activeFilter);
    if (draft.sortBy !== "created_at") p.set("sort_by", draft.sortBy);
    if (draft.sortOrder !== "desc") p.set("sort_order", draft.sortOrder);
    router.replace(`?${p.toString()}`);
    setPlatformDropdownOpen(false);
  }

  function resetFilters() {
    setDraft(DEFAULT_DRAFT);
    router.replace("?");
    setPlatformDropdownOpen(false);
  }

  const toggleDraftPlatform = useCallback((val: string) => {
    setDraft((d) => ({
      ...d,
      platforms: d.platforms.includes(val)
        ? d.platforms.filter((x) => x !== val)
        : [...d.platforms, val],
    }));
  }, []);

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

      {/* Filter card */}
      <div className={FILTER_CARD}>
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-12 lg:items-end">
          {/* Platform multi-select */}
          <div className="lg:col-span-3">
            <FilterMultiSelect<string>
              label="Platform"
              emptySummary="All platforms"
              selectedIds={draft.platforms}
              options={platformOptions}
              open={platformDropdownOpen}
              onOpenChange={setPlatformDropdownOpen}
              onToggle={toggleDraftPlatform}
            />
          </div>

          {/* Active status */}
          <div className="lg:col-span-3">
            <span className={FILTER_LABEL}>Status</span>
            <div className={FILTER_SEGMENT_WRAP}>
              {(["all", "active", "inactive"] as ActiveFilter[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  className={cn(
                    FILTER_SEGMENT_BTN,
                    draft.activeFilter === v ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                  )}
                  onClick={() => patchDraft({ activeFilter: v })}
                >
                  {v === "all" ? "All" : v === "active" ? "Active" : "Inactive"}
                </button>
              ))}
            </div>
          </div>

          {/* Sort */}
          <div className="lg:col-span-3">
            <span className={FILTER_LABEL}>Sort by</span>
            <div className="flex gap-1.5">
              <FilterSelect
                value={draft.sortBy}
                options={SORT_OPTIONS}
                onChange={(v) => patchDraft({ sortBy: v as string })}
                className="flex-1 min-w-0"
              />
              <button
                type="button"
                title={draft.sortOrder === "desc" ? "Descending" : "Ascending"}
                onClick={() => patchDraft({ sortOrder: draft.sortOrder === "desc" ? "asc" : "desc" })}
                className={cn(FILTER_CONTROL, "w-11 shrink-0 px-0 text-center font-mono")}
              >
                {draft.sortOrder === "desc" ? "↓" : "↑"}
              </button>
            </div>
          </div>

          {/* Apply + Reset */}
          <div className="lg:col-span-3">
            <span className={FILTER_LABEL} aria-hidden>&nbsp;</span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={!isDirty}
                onClick={applyFilters}
                className={cn(
                  "flex-1 min-h-[2.5rem] rounded-xl px-3 py-2 text-sm font-semibold text-white transition-colors",
                  isDirty ? "bg-[#224C87] hover:bg-[#1a3d6e]" : "cursor-not-allowed bg-[#224C87]/35"
                )}
              >
                Apply
              </button>
              <button
                type="button"
                onClick={resetFilters}
                disabled={!(isDirty || hasAppliedFilters)}
                className="flex-1 min-h-[2.5rem] rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Reset
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Backdrop */}
      {platformDropdownOpen && (
        <div className="fixed inset-0 z-[35]" aria-hidden onClick={() => setPlatformDropdownOpen(false)} />
      )}

      <PresetsPagedGrid
        key={urlKey}
        platforms={appliedDraft.platforms}
        activeFilter={appliedDraft.activeFilter}
        sortBy={appliedDraft.sortBy}
        sortOrder={appliedDraft.sortOrder}
      />
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
