"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";
import { useSearchParams, useRouter } from "next/navigation";
import {
  Suspense,
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
  type Dispatch,
  type SetStateAction,
} from "react";
import { apiClient } from "@/api/client";
import { Download, Pause, Play, Plus, RotateCcw, Trash2, ChevronDown, Filter, Video } from "lucide-react";
import { cn, extractApiError } from "@/lib/utils";
import { useDebounce } from "@/hooks/use-debounce";
import { useToast } from "@/hooks/use-toast";
import { Toast } from "@/components/ui/toast";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { RecordingCard, type RecordingCardData } from "@/components/recordings/recording-card";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { SegmentedFilter } from "@/components/filters/segmented-filter";
import { FilterMultiSelect, type FilterMultiSelectOption } from "@/components/filters/filter-multi-select";
import { FilterChips, type FilterChipItem } from "@/components/filters/filter-chips";
import { AddVideoModal } from "@/components/recordings/add-video-modal";
import { RunConfigModal } from "@/components/recordings/run-config-modal";
import { ExportModal } from "@/components/recordings/export-modal";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Pagination } from "@/components/ui/pagination";
import type { ProcessingStatus } from "@/components/ui/status-badge";
import {
  ACTIVE_POLL_STATUSES,
  DEBOUNCE_SEARCH,
  PER_PAGE_LARGE,
  PER_PAGE_RECORDINGS,
  POLL_INTERVAL_LIST,
} from "@/lib/constants";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RecordingListResponse {
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  items: RecordingCardData[];
}

interface TemplateListItem { id: number; name: string }
interface TemplateListResponse { items: TemplateListItem[]; total: number }
interface SourceListItem { id: number; name: string }
interface SourceListResponse { items: SourceListItem[]; total: number }

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALL_STATUSES: ProcessingStatus[] = [
  "PENDING_SOURCE", "INITIALIZED", "DOWNLOADING", "DOWNLOADED",
  "PROCESSING", "PROCESSED", "UPLOADING", "UPLOADED", "READY", "SKIPPED", "EXPIRED",
];

const STATUS_OPTIONS: FilterMultiSelectOption<ProcessingStatus>[] = ALL_STATUSES.map((s) => ({
  value: s,
  label: s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, " "),
}));

const SORT_OPTIONS = [
  { value: "start_time",   label: "Start time" },
  { value: "created_at",  label: "Created" },
  { value: "updated_at",  label: "Updated" },
  { value: "display_name", label: "Name" },
  { value: "status",       label: "Status" },
];

const SORT_BY_ALLOWED = new Set(SORT_OPTIONS.map((o) => o.value));

const STATUS_LABEL_BY_VALUE = new Map(STATUS_OPTIONS.map((o) => [o.value, o.label]));

type Notify = (type: "success" | "error" | "info", msg: string) => void;

// ---------------------------------------------------------------------------
// Filters — all read from / written to the URL; everything applies instantly
// ---------------------------------------------------------------------------

interface RecordingsFilters {
  status: ProcessingStatus[];
  templateIds: number[];
  sourceIds: number[];
  isMapped: boolean | null;
  includeBlank: boolean;
  includeDeleted: boolean;
  fromDate: string;
  toDate: string;
}

function parsePositiveIntParams(sp: URLSearchParams, key: string): number[] {
  const xs = sp.getAll(key).map((s) => parseInt(s, 10)).filter((n) => !Number.isNaN(n) && n > 0);
  return [...new Set(xs)].sort((a, b) => a - b);
}

function parseIsMappedFromUrl(raw: string | null): boolean | null {
  if (raw === "true") return true;
  if (raw === "false") return false;
  return null;
}

function filtersFromUrl(sp: URLSearchParams): RecordingsFilters {
  return {
    status: sp.getAll("status") as ProcessingStatus[],
    templateIds: parsePositiveIntParams(sp, "template_id"),
    sourceIds: parsePositiveIntParams(sp, "source_id"),
    isMapped: parseIsMappedFromUrl(sp.get("is_mapped")),
    includeBlank: sp.get("include_blank") === "true",
    includeDeleted: sp.get("include_deleted") === "true",
    fromDate: sp.get("from_date") ?? "",
    toDate: sp.get("to_date") ?? "",
  };
}

function advancedCount(f: RecordingsFilters): number {
  return (
    (f.isMapped !== null ? 1 : 0) +
    (f.fromDate ? 1 : 0) +
    (f.toDate ? 1 : 0) +
    (f.includeBlank ? 1 : 0) +
    (f.includeDeleted ? 1 : 0)
  );
}

// ---------------------------------------------------------------------------
// RecordingsPagedResults
// ---------------------------------------------------------------------------

interface RecordingsPagedResultsProps {
  queryParamsString: string;
  page: number;
  onPageChange: (page: number) => void;
  loadingRecordingId: number | null;
  selected: Set<number>;
  setSelected: Dispatch<SetStateAction<Set<number>>>;
  onRun: (id: number) => void;
  onPause: (id: number) => void;
  onRunWithConfig: (id: number) => void;
  onReset: (id: number) => void;
  onDelete: (id: number) => void;
  onRestore: (id: number) => void;
  bulkRun: UseMutationResult<unknown, unknown, number[], unknown>;
  bulkPause: UseMutationResult<unknown, unknown, number[], unknown>;
  bulkDelete: UseMutationResult<unknown, unknown, number[], unknown>;
  bulkReset: UseMutationResult<unknown, unknown, { ids: number[]; deleteFiles: boolean }, unknown>;
  deleteConfirm: boolean;
  setDeleteConfirm: (open: boolean) => void;
  resetConfirm: boolean;
  setResetConfirm: (open: boolean) => void;
  resetDeleteFiles: boolean;
  setResetDeleteFiles: (v: boolean) => void;
  onBulkRunWithConfig: () => void;
  notify: Notify;
  onAddVideo: () => void;
  onResetFilters: () => void;
}

function RecordingsPagedResults({
  queryParamsString,
  page,
  onPageChange,
  loadingRecordingId,
  selected,
  setSelected,
  onRun,
  onPause,
  onRunWithConfig,
  onReset,
  onDelete,
  onRestore,
  bulkRun,
  bulkPause,
  bulkDelete,
  bulkReset,
  deleteConfirm,
  setDeleteConfirm,
  resetConfirm,
  setResetConfirm,
  resetDeleteFiles,
  setResetDeleteFiles,
  onBulkRunWithConfig,
  notify,
  onAddVideo,
  onResetFilters,
}: RecordingsPagedResultsProps) {
  const [pipelineMenuOpen, setPipelineMenuOpen] = useState(false);
  const pipelineMenuRef = useRef<HTMLDivElement>(null);
  const qcInner = useQueryClient();

  function usePipelineMutation(path: string, label: string) {
    return useMutation({
      mutationFn: (ids: number[]) => apiClient.post(path, { recording_ids: ids }),
      onSuccess: () => {
        qcInner.invalidateQueries({ queryKey: ["recordings"] });
        notify("success", `${label} started`);
      },
      onError: (e) => notify("error", extractApiError(e, `${label} failed`)),
    });
  }

  const bulkDownload = usePipelineMutation("/recordings/bulk/download", "Download");
  const bulkTrim = usePipelineMutation("/recordings/bulk/trim", "Trim");
  const bulkTranscribe = usePipelineMutation("/recordings/bulk/transcribe", "Transcription");
  const bulkTopics = usePipelineMutation("/recordings/bulk/topics", "Topic extraction");
  const bulkSubtitles = usePipelineMutation("/recordings/bulk/subtitles", "Subtitle generation");
  const bulkUpload = usePipelineMutation("/recordings/bulk/upload", "Upload");

  useEffect(() => {
    if (!pipelineMenuOpen) return;
    function onPointerDown(e: PointerEvent) {
      if (pipelineMenuRef.current && !pipelineMenuRef.current.contains(e.target as Node)) {
        setPipelineMenuOpen(false);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [pipelineMenuOpen]);

  const { data, isLoading, error } = useQuery<RecordingListResponse>({
    queryKey: ["recordings", queryParamsString, page],
    queryFn: async () => {
      const p = new URLSearchParams(queryParamsString);
      p.set("page", String(page));
      p.set("per_page", String(PER_PAGE_RECORDINGS));
      const res = await apiClient.get<RecordingListResponse>(`/recordings?${p.toString()}`);
      return res.data;
    },
    refetchInterval: (q) => {
      const items = q.state.data?.items ?? [];
      return items.some((r) => ACTIVE_POLL_STATUSES.has(r.status)) ? POLL_INTERVAL_LIST : false;
    },
    refetchIntervalInBackground: false,
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

  const recordings = data?.items ?? [];
  const isBulkLoading =
    bulkRun.isPending || bulkPause.isPending || bulkDelete.isPending || bulkReset.isPending ||
    bulkDownload.isPending || bulkTrim.isPending || bulkTranscribe.isPending || bulkTopics.isPending ||
    bulkSubtitles.isPending || bulkUpload.isPending;
  const selectedIds = useMemo(() => Array.from(selected), [selected]);

  const hasActiveFilters = queryParamsString.length > 0;

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === recordings.length && recordings.length > 0) {
      setSelected(new Set());
    } else {
      setSelected(new Set(recordings.map((r) => r.id)));
    }
  }

  return (
    <>
      {selected.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-[#224C87]/20 bg-[#224C87]/5 p-3">
          <label className="mr-2 flex items-center gap-2">
            <input
              type="checkbox"
              checked={selected.size === recordings.length && recordings.length > 0}
              onChange={toggleAll}
              className="rounded accent-[#224C87]"
            />
            <span className="text-sm font-medium text-[#224C87]">{selected.size} selected</span>
          </label>

          <button
            type="button"
            onClick={() => bulkRun.mutate(selectedIds)}
            disabled={isBulkLoading}
            className="flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-white px-3 py-1.5 text-xs font-medium transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            <Play size={13} /> Run
          </button>
          <button
            type="button"
            onClick={onBulkRunWithConfig}
            disabled={isBulkLoading}
            className="flex items-center gap-1.5 rounded-lg border border-[#224C87]/30 bg-white px-3 py-1.5 text-xs font-medium text-[#224C87] transition-colors hover:bg-[#224C87]/5 disabled:opacity-50"
          >
            <Play size={13} /> Run with config…
          </button>
          <button
            type="button"
            onClick={() => bulkPause.mutate(selectedIds)}
            disabled={isBulkLoading}
            className="flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-white px-3 py-1.5 text-xs font-medium transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            <Pause size={13} /> Pause
          </button>
          <button
            type="button"
            onClick={() => setResetConfirm(true)}
            disabled={isBulkLoading}
            className="flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-white px-3 py-1.5 text-xs font-medium transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            <RotateCcw size={13} /> Reset
          </button>

          {/* Pipeline dropdown */}
          <div className="relative" ref={pipelineMenuRef}>
            <button
              type="button"
              onClick={() => setPipelineMenuOpen((v) => !v)}
              disabled={isBulkLoading}
              className="flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-white px-3 py-1.5 text-xs font-medium transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              Pipeline
              <ChevronDown size={12} className={cn("transition-transform", pipelineMenuOpen && "rotate-180")} />
            </button>
            {pipelineMenuOpen && (
              <div className="absolute left-0 top-full z-20 mt-1 w-36 overflow-hidden rounded-xl border border-[#D9D9D9] bg-white shadow-lg">
                {[
                  { label: "Download",   fn: () => { bulkDownload.mutate(selectedIds); setPipelineMenuOpen(false); } },
                  { label: "Trim",       fn: () => { bulkTrim.mutate(selectedIds); setPipelineMenuOpen(false); } },
                  { label: "Transcribe", fn: () => { bulkTranscribe.mutate(selectedIds); setPipelineMenuOpen(false); } },
                  { label: "Topics",     fn: () => { bulkTopics.mutate(selectedIds); setPipelineMenuOpen(false); } },
                  { label: "Subtitles",  fn: () => { bulkSubtitles.mutate(selectedIds); setPipelineMenuOpen(false); } },
                  { label: "Upload",     fn: () => { bulkUpload.mutate(selectedIds); setPipelineMenuOpen(false); } },
                ].map(({ label, fn }) => (
                  <button
                    key={label}
                    type="button"
                    onClick={fn}
                    className="flex w-full items-center px-3 py-2 text-left text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => setDeleteConfirm(true)}
            disabled={isBulkLoading}
            className="ml-auto flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-500 transition-colors hover:bg-red-50 disabled:opacity-50"
          >
            <Trash2 size={13} /> Delete
          </button>
        </div>
      )}

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-48 animate-pulse rounded-2xl border border-[#D9D9D9] bg-white" />
          ))}
        </div>
      )}

      {error && (
        <div className="py-16 text-center text-sm text-red-400">Failed to load recordings</div>
      )}

      {!isLoading && !error && recordings.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <div className="rounded-2xl bg-gray-50 p-3 text-gray-300">
            <Video size={28} strokeWidth={1.5} />
          </div>
          <p className="text-sm font-medium text-gray-500">
            {hasActiveFilters ? "No recordings match your filters" : "No recordings yet"}
          </p>
          {hasActiveFilters ? (
            <button
              type="button"
              onClick={onResetFilters}
              className="rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
            >
              Reset filters
            </button>
          ) : (
            <button
              type="button"
              onClick={onAddVideo}
              className="flex items-center gap-2 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1a3d6e]"
            >
              <Plus size={16} />
              Add video
            </button>
          )}
        </div>
      )}

      {!isLoading && !error && recordings.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {recordings.map((rec) => (
            <RecordingCard
              key={rec.id}
              recording={rec}
              selected={selected.has(rec.id)}
              onToggleSelect={toggleSelect}
              onRun={onRun}
              onPause={onPause}
              onRunWithConfig={onRunWithConfig}
              onReset={onReset}
              onDelete={onDelete}
              onRestore={onRestore}
              loadingId={loadingRecordingId}
            />
          ))}
        </div>
      )}

      {data && (
        <Pagination
          page={page}
          totalPages={data.total_pages}
          total={data.total}
          perPage={PER_PAGE_RECORDINGS}
          onPageChange={onPageChange}
          itemLabel="recording"
        />
      )}

      {/* Bulk delete confirm */}
      <ConfirmDialog
        open={deleteConfirm}
        title={`Delete ${selectedIds.length} recording${selectedIds.length !== 1 ? "s" : ""}?`}
        description="This will soft-delete the selected recordings. They can be restored for a limited time."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        onConfirm={() => {
          setDeleteConfirm(false);
          bulkDelete.mutate(selectedIds);
        }}
        onCancel={() => setDeleteConfirm(false)}
      />

      {/* Bulk reset confirm */}
      <ConfirmDialog
        open={resetConfirm}
        title={`Reset ${selectedIds.length} recording${selectedIds.length !== 1 ? "s" : ""}?`}
        description="Recordings will be reset to INITIALIZED status."
        confirmLabel="Reset"
        cancelLabel="Cancel"
        onConfirm={() => {
          setResetConfirm(false);
          bulkReset.mutate({ ids: selectedIds, deleteFiles: resetDeleteFiles });
        }}
        onCancel={() => setResetConfirm(false)}
      >
        <label className="flex items-center gap-2 text-sm text-gray-700 select-none cursor-pointer">
          <input
            type="checkbox"
            checked={resetDeleteFiles}
            onChange={(e) => setResetDeleteFiles(e.target.checked)}
            className="rounded border-gray-300 text-[#224C87] focus:ring-[#224C87]/30"
          />
          Delete processed files (video, audio, transcription)
        </label>
      </ConfirmDialog>
    </>
  );
}

// ---------------------------------------------------------------------------
// Advanced filters section (Scope & visibility)
// ---------------------------------------------------------------------------

interface AdvancedFiltersSectionProps {
  filters: RecordingsFilters;
  onPatch: (patch: Partial<RecordingsFilters>) => void;
}

function AdvancedFiltersSection({ filters, onPatch }: AdvancedFiltersSectionProps) {
  const count = advancedCount(filters);
  const [sectionOpen, setSectionOpen] = useState(() => count > 0);

  return (
    <>
      <button
        type="button"
        onClick={() => setSectionOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg py-1 text-left text-sm font-semibold text-[#224C87] transition-colors hover:text-[#1a3d6e]"
        aria-expanded={sectionOpen}
      >
        <Filter size={16} className="shrink-0 opacity-90" />
        Scope &amp; visibility
        {count > 0 && (
          <span className="rounded-full bg-[#224C87]/15 px-2 py-0.5 text-xs font-semibold tabular-nums text-[#224C87]">
            {count}
          </span>
        )}
        <ChevronDown
          size={16}
          className={cn("ml-auto shrink-0 text-gray-400 transition-transform", sectionOpen && "rotate-180")}
        />
      </button>

      {sectionOpen && (
        <div className="mt-4 space-y-5">
          {/* Date range */}
          <div className="space-y-1.5">
            <span className={FILTER_LABEL}>Recording start date</span>
            <div className="flex items-center gap-3">
              <input
                type="date"
                aria-label="From date"
                value={filters.fromDate}
                onChange={(e) => onPatch({ fromDate: e.target.value })}
                className={cn(FILTER_CONTROL, "max-w-[11rem]")}
              />
              <span className="text-gray-400 select-none">—</span>
              <input
                type="date"
                aria-label="To date"
                value={filters.toDate}
                onChange={(e) => onPatch({ toDate: e.target.value })}
                className={cn(FILTER_CONTROL, "max-w-[11rem]")}
              />
            </div>
          </div>

          {/* Segmented toggles */}
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-3">
            <SegmentedFilter
              label="Template mapping"
              value={filters.isMapped === null ? "any" : filters.isMapped ? "mapped" : "unmapped"}
              options={[
                { value: "any", label: "Any" },
                { value: "mapped", label: "Mapped" },
                { value: "unmapped", label: "Not mapped" },
              ]}
              onChange={(v) => onPatch({ isMapped: v === "any" ? null : v === "mapped" })}
            />
            <SegmentedFilter
              label="Blank recordings"
              value={filters.includeBlank ? "include" : "standard"}
              options={[
                { value: "standard", label: "Standard" },
                { value: "include", label: "Include blanks" },
              ]}
              onChange={(v) => onPatch({ includeBlank: v === "include" })}
            />
            <SegmentedFilter
              label="Deleted recordings"
              value={filters.includeDeleted ? "include" : "standard"}
              options={[
                { value: "standard", label: "Standard" },
                { value: "include", label: "Include deleted" },
              ]}
              onChange={(v) => onPatch({ includeDeleted: v === "include" })}
            />
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main content
// ---------------------------------------------------------------------------

function RecordingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const { toast, show: showToast, dismiss: dismissToast } = useToast();
  const urlKey = searchParams.toString();

  // --- Immediate controls (search + sort + page) ---
  const urlSearch = searchParams.get("search") ?? "";
  const urlSortBy = (() => {
    const raw = searchParams.get("sort_by") ?? "start_time";
    return SORT_BY_ALLOWED.has(raw) ? raw : "start_time";
  })();
  const urlSortOrder: "asc" | "desc" = searchParams.get("sort_order") === "asc" ? "asc" : "desc";
  const urlPage = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);

  // --- Selection state ---
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [addModalOpen, setAddModalOpen] = useState(false);

  // --- Confirm dialogs ---
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [resetDeleteFiles, setResetDeleteFiles] = useState(false);
  const [singleDeleteId, setSingleDeleteId] = useState<number | null>(null);
  const [singleResetId, setSingleResetId] = useState<number | null>(null);

  // --- Run-with-config modal ---
  const [runConfigRecordingId, setRunConfigRecordingId] = useState<number | null>(null);
  const [runConfigRecordingName, setRunConfigRecordingName] = useState<string | undefined>(undefined);
  const [runConfigMode, setRunConfigMode] = useState<"single" | "bulk">("single");
  const [runConfigOpen, setRunConfigOpen] = useState(false);

  // --- Export modal ---
  const [exportOpen, setExportOpen] = useState(false);

  // Local search input with debounce → syncs to URL
  const [searchInput, setSearchInput] = useState(urlSearch);
  const debouncedSearch = useDebounce(searchInput, DEBOUNCE_SEARCH);

  // Sync URL → searchInput on external navigation (browser back/fwd)
  const [prevUrlKey, setPrevUrlKey] = useState(urlKey);
  if (urlKey !== prevUrlKey) {
    setPrevUrlKey(urlKey);
    setSearchInput(searchParams.get("search") ?? "");
  }

  // Sync debounced search → URL (skip if already matches)
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
    setSelected(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  function updateSort(field?: string, order?: string) {
    const p = new URLSearchParams(searchParams.toString());
    if (field !== undefined) p.set("sort_by", field);
    if (order !== undefined) p.set("sort_order", order);
    p.delete("page");
    router.replace(`?${p.toString()}`);
    setSelected(new Set());
  }

  const setPage = useCallback(
    (next: number) => {
      const p = new URLSearchParams(searchParams.toString());
      if (next <= 1) p.delete("page");
      else p.set("page", String(next));
      router.replace(`?${p.toString()}`);
    },
    [router, searchParams],
  );

  // --- Current filters (read from URL) + instant-apply URL writers ---
  const filters = useMemo(() => filtersFromUrl(new URLSearchParams(urlKey)), [urlKey]);

  const commitFilters = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      const p = new URLSearchParams(urlKey);
      mutate(p);
      p.delete("page");
      router.replace(`?${p.toString()}`);
      setSelected(new Set());
    },
    [urlKey, router],
  );

  // Multi-selects commit their whole selection at once (on dropdown close).
  const setMultiParam = useCallback(
    (key: string, values: (string | number)[]) => {
      commitFilters((p) => {
        p.delete(key);
        values.forEach((v) => p.append(key, String(v)));
      });
    },
    [commitFilters],
  );

  // Scope & visibility (segments + dates) write their field instantly.
  const patchFilters = useCallback(
    (patch: Partial<RecordingsFilters>) => {
      commitFilters((p) => {
        if ("isMapped" in patch) {
          if (patch.isMapped == null) p.delete("is_mapped");
          else p.set("is_mapped", patch.isMapped ? "true" : "false");
        }
        if ("includeBlank" in patch) {
          if (patch.includeBlank) p.set("include_blank", "true");
          else p.delete("include_blank");
        }
        if ("includeDeleted" in patch) {
          if (patch.includeDeleted) p.set("include_deleted", "true");
          else p.delete("include_deleted");
        }
        if ("fromDate" in patch) {
          if (patch.fromDate) p.set("from_date", patch.fromDate);
          else p.delete("from_date");
        }
        if ("toDate" in patch) {
          if (patch.toDate) p.set("to_date", patch.toDate);
          else p.delete("to_date");
        }
      });
    },
    [commitFilters],
  );

  const hasActiveFilters = useMemo(() => {
    const sp = new URLSearchParams(urlKey);
    return !!(
      sp.get("search") ||
      sp.getAll("status").length ||
      parsePositiveIntParams(sp, "template_id").length ||
      parsePositiveIntParams(sp, "source_id").length ||
      sp.get("is_mapped") ||
      sp.get("include_blank") === "true" ||
      sp.get("include_deleted") === "true" ||
      sp.get("from_date") ||
      sp.get("to_date") ||
      (sp.get("sort_by") && sp.get("sort_by") !== "start_time") ||
      sp.get("sort_order") === "asc"
    );
  }, [urlKey]);

  // --- Reference data ---
  const { data: templatesData } = useQuery<TemplateListResponse>({
    queryKey: ["templates-dropdown"],
    queryFn: async () => {
      const res = await apiClient.get<TemplateListResponse>(`/templates?per_page=${PER_PAGE_LARGE}`);
      return res.data;
    },
  });

  const { data: sourcesData } = useQuery<SourceListResponse>({
    queryKey: ["sources-dropdown"],
    queryFn: async () => {
      const res = await apiClient.get<SourceListResponse>(`/sources?per_page=${PER_PAGE_LARGE}`);
      return res.data;
    },
  });

  const templateOptions = useMemo<FilterMultiSelectOption[]>(
    () => (templatesData?.items ?? []).map((t) => ({ value: t.id, label: t.name })),
    [templatesData]
  );

  const sourceOptions = useMemo<FilterMultiSelectOption[]>(
    () => (sourcesData?.items ?? []).map((s) => ({ value: s.id, label: s.name })),
    [sourcesData]
  );

  // --- Loading tracking per recording ---
  const [loadingRecordingId, setLoadingRecordingId] = useState<number | null>(null);

  // Clear search + every filter at once.
  const resetAllFilters = useCallback(() => {
    setSearchInput("");
    lastAppliedSearchRef.current = "";
    router.replace("?");
    setSelected(new Set());
  }, [router]);

  // --- Mutations ---
  const bulkRun = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/run", { recording_ids: ids }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recordings"] }); setSelected(new Set()); showToast("success", "Pipeline started"); },
    onError: (e) => showToast("error", extractApiError(e, "Failed to start pipeline")),
  });

  const bulkPause = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/pause", { recording_ids: ids }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recordings"] }); setSelected(new Set()); showToast("success", "Paused"); },
    onError: (e) => showToast("error", extractApiError(e, "Failed to pause")),
  });

  const bulkDelete = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/delete", { recording_ids: ids }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recordings"] }); setSelected(new Set()); showToast("success", "Recordings deleted"); },
    onError: (e) => showToast("error", extractApiError(e, "Failed to delete")),
  });

  // Bulk reset: parallel individual reset calls
  const bulkReset = useMutation({
    mutationFn: ({ ids, deleteFiles }: { ids: number[]; deleteFiles: boolean }) =>
      Promise.all(ids.map((id) => apiClient.post(`/recordings/${id}/reset`, null, { params: { delete_files: deleteFiles } }))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recordings"] }); setSelected(new Set()); showToast("success", "Recordings reset"); },
    onError: (e) => showToast("error", extractApiError(e, "Failed to reset")),
  });

  const singleRun = useMutation({
    mutationFn: (id: number) => apiClient.post(`/recordings/${id}/run`),
    onMutate: (id) => setLoadingRecordingId(id),
    onSettled: () => setLoadingRecordingId(null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
    onError: (e) => showToast("error", extractApiError(e, "Failed to start pipeline")),
  });

  const singlePause = useMutation({
    mutationFn: (id: number) => apiClient.post(`/recordings/${id}/pause`),
    onMutate: (id) => setLoadingRecordingId(id),
    onSettled: () => setLoadingRecordingId(null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
    onError: (e) => showToast("error", extractApiError(e, "Failed to pause")),
  });

  const singleReset = useMutation({
    mutationFn: ({ id, deleteFiles }: { id: number; deleteFiles: boolean }) =>
      apiClient.post(`/recordings/${id}/reset`, null, { params: { delete_files: deleteFiles } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
    onError: (e) => showToast("error", extractApiError(e, "Failed to reset")),
  });

  const singleDelete = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/recordings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
    onError: (e) => showToast("error", extractApiError(e, "Failed to delete")),
  });

  const singleRestore = useMutation({
    mutationFn: (id: number) => apiClient.post(`/recordings/${id}/restore`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
    onError: (e) => showToast("error", extractApiError(e, "Failed to restore")),
  });

  // --- Card action handlers ---
  function handleRunWithConfig(id: number) {
    // Find the recording name from any cached page data
    const cached = qc.getQueriesData<RecordingListResponse>({ queryKey: ["recordings"] });
    let name: string | undefined;
    for (const [, data] of cached) {
      if (data) {
        const found = data.items.find((r) => r.id === id);
        if (found) { name = found.display_name; break; }
      }
    }
    setRunConfigRecordingId(id);
    setRunConfigRecordingName(name);
    setRunConfigMode("single");
    setRunConfigOpen(true);
  }

  function handleReset(id: number) {
    setSingleResetId(id);
  }

  function handleDelete(id: number) {
    setSingleDeleteId(id);
  }

  function handleBulkRunWithConfig() {
    setRunConfigMode("bulk");
    setRunConfigOpen(true);
  }

  const selectedIds = useMemo(() => Array.from(selected), [selected]);
  // Remount results when filters change, but NOT on plain page navigation —
  // otherwise paging would reset internal state (open menus, etc.).
  const appliedKey = useMemo(() => {
    const p = new URLSearchParams(urlKey);
    p.delete("page");
    return p.toString();
  }, [urlKey]);

  // --- Applied-filter chips (derived from URL) ---
  const templateLabel = useCallback(
    (id: number) => templateOptions.find((o) => o.value === id)?.label ?? `#${id}`,
    [templateOptions],
  );
  const sourceLabel = useCallback(
    (id: number) => sourceOptions.find((o) => o.value === id)?.label ?? `#${id}`,
    [sourceOptions],
  );

  const appliedChips = useMemo<FilterChipItem[]>(() => {
    const f = filters;
    const chips: FilterChipItem[] = [];

    if (urlSearch) {
      chips.push({
        key: "search",
        label: `Search: "${urlSearch}"`,
        onRemove: () => {
          // Clear the input too; the debounced effect would otherwise re-add it.
          setSearchInput("");
          commitFilters((p) => p.delete("search"));
        },
      });
    }
    f.status.forEach((st) =>
      chips.push({
        key: `status:${st}`,
        label: STATUS_LABEL_BY_VALUE.get(st) ?? st,
        onRemove: () => setMultiParam("status", f.status.filter((x) => x !== st)),
      }),
    );
    f.templateIds.forEach((id) =>
      chips.push({
        key: `template:${id}`,
        label: `Template: ${templateLabel(id)}`,
        onRemove: () => setMultiParam("template_id", f.templateIds.filter((x) => x !== id)),
      }),
    );
    f.sourceIds.forEach((id) =>
      chips.push({
        key: `source:${id}`,
        label: `Source: ${sourceLabel(id)}`,
        onRemove: () => setMultiParam("source_id", f.sourceIds.filter((x) => x !== id)),
      }),
    );
    if (f.isMapped !== null) {
      chips.push({
        key: "is_mapped",
        label: f.isMapped ? "Mapped" : "Not mapped",
        onRemove: () => patchFilters({ isMapped: null }),
      });
    }
    if (f.fromDate) {
      chips.push({ key: "from_date", label: `From ${f.fromDate}`, onRemove: () => patchFilters({ fromDate: "" }) });
    }
    if (f.toDate) {
      chips.push({ key: "to_date", label: `To ${f.toDate}`, onRemove: () => patchFilters({ toDate: "" }) });
    }
    if (f.includeBlank) {
      chips.push({ key: "include_blank", label: "Include blanks", onRemove: () => patchFilters({ includeBlank: false }) });
    }
    if (f.includeDeleted) {
      chips.push({ key: "include_deleted", label: "Include deleted", onRemove: () => patchFilters({ includeDeleted: false }) });
    }
    return chips;
  }, [filters, urlSearch, templateLabel, sourceLabel, commitFilters, setMultiParam, patchFilters]);

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      {/* Page header */}
      <div className="mb-5 flex min-h-[2.5rem] flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Recordings</h1>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => setExportOpen(true)}
            className="flex items-center justify-center gap-2 rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            <Download size={16} />
            Export
          </button>
          <button
            type="button"
            onClick={() => setAddModalOpen(true)}
            className="flex items-center justify-center gap-2 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1a3d6e]"
          >
            <Plus size={16} />
            Add video
          </button>
        </div>
      </div>

      {/* ── Filters ── */}
      <FilterBar
        search={
          <SearchInput
            id="recordings-search"
            value={searchInput}
            onChange={setSearchInput}
            placeholder="By display name…"
          />
        }
        controls={[
          <FilterMultiSelect<ProcessingStatus>
            key="status"
            label="Status"
            emptySummary="All statuses"
            value={filters.status}
            options={STATUS_OPTIONS}
            onChange={(next) => setMultiParam("status", next)}
          />,
          <FilterMultiSelect
            key="templates"
            label="Templates"
            emptySummary="All templates"
            value={filters.templateIds}
            options={templateOptions}
            onChange={(next) => setMultiParam("template_id", next)}
          />,
          <FilterMultiSelect
            key="sources"
            label="Sources"
            emptySummary="All sources"
            value={filters.sourceIds}
            options={sourceOptions}
            onChange={(next) => setMultiParam("source_id", next)}
          />,
        ]}
        sort={
          <SortControl
            value={urlSortBy}
            order={urlSortOrder}
            options={SORT_OPTIONS}
            onChange={(field) => updateSort(field)}
            onToggleOrder={() => updateSort(undefined, urlSortOrder === "desc" ? "asc" : "desc")}
          />
        }
        onClearAll={hasActiveFilters ? resetAllFilters : undefined}
        advanced={<AdvancedFiltersSection filters={filters} onPatch={patchFilters} />}
        chips={<FilterChips chips={appliedChips} />}
      />

      {/* Results */}
      <RecordingsPagedResults
        key={appliedKey}
        queryParamsString={appliedKey}
        page={urlPage}
        onPageChange={setPage}
        loadingRecordingId={loadingRecordingId}
        selected={selected}
        setSelected={setSelected}
        onRun={(id) => singleRun.mutate(id)}
        onPause={(id) => singlePause.mutate(id)}
        onRunWithConfig={handleRunWithConfig}
        onReset={handleReset}
        onDelete={handleDelete}
        onRestore={(id) => singleRestore.mutate(id)}
        bulkRun={bulkRun}
        bulkPause={bulkPause}
        bulkDelete={bulkDelete}
        bulkReset={bulkReset}
        deleteConfirm={deleteConfirm}
        setDeleteConfirm={setDeleteConfirm}
        resetConfirm={resetConfirm}
        setResetConfirm={setResetConfirm}
        resetDeleteFiles={resetDeleteFiles}
        setResetDeleteFiles={setResetDeleteFiles}
        onBulkRunWithConfig={handleBulkRunWithConfig}
        notify={showToast}
        onAddVideo={() => setAddModalOpen(true)}
        onResetFilters={resetAllFilters}
      />

      {/* Single reset confirm */}
      <ConfirmDialog
        open={singleResetId !== null}
        title="Reset recording?"
        description="The recording will return to INITIALIZED status."
        confirmLabel="Reset"
        cancelLabel="Cancel"
        onConfirm={() => {
          if (singleResetId !== null) singleReset.mutate({ id: singleResetId, deleteFiles: resetDeleteFiles });
          setSingleResetId(null);
        }}
        onCancel={() => setSingleResetId(null)}
      >
        <label className="flex items-center gap-2 text-sm text-gray-700 select-none cursor-pointer">
          <input
            type="checkbox"
            checked={resetDeleteFiles}
            onChange={(e) => setResetDeleteFiles(e.target.checked)}
            className="rounded border-gray-300 text-[#224C87] focus:ring-[#224C87]/30"
          />
          Delete processed files (video, audio, transcription)
        </label>
      </ConfirmDialog>

      {/* Single delete confirm */}
      <ConfirmDialog
        open={singleDeleteId !== null}
        title="Delete recording?"
        description="The recording will be soft-deleted and can be restored for a limited time."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        onConfirm={() => {
          if (singleDeleteId !== null) singleDelete.mutate(singleDeleteId);
          setSingleDeleteId(null);
        }}
        onCancel={() => setSingleDeleteId(null)}
      />

      {/* Run with config modal */}
      <RunConfigModal
        open={runConfigOpen}
        onClose={() => setRunConfigOpen(false)}
        mode={runConfigMode}
        recordingId={runConfigMode === "single" ? (runConfigRecordingId ?? undefined) : undefined}
        recordingName={runConfigMode === "single" ? runConfigRecordingName : undefined}
        recordingIds={runConfigMode === "bulk" ? selectedIds : undefined}
        onSuccess={() => setSelected(new Set())}
      />

      {/* Export modal */}
      <ExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        selectedIds={selectedIds}
        appliedFilterParams={appliedKey}
      />

      <AddVideoModal open={addModalOpen} onClose={() => setAddModalOpen(false)} />

      {toast && (
        <Toast
          key={toast.serial}
          type={toast.type}
          message={toast.msg}
          exiting={toast.exiting}
          onDismiss={dismissToast}
        />
      )}
    </div>
  );
}

export default function RecordingsPage() {
  return (
    <Suspense>
      <RecordingsContent />
    </Suspense>
  );
}
