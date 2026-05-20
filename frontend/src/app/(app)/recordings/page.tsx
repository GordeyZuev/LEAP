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
import { Download, Pause, Play, Plus, RotateCcw, Trash2, ChevronDown, X, Filter } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDebounce } from "@/hooks/use-debounce";
import {
  FILTER_CARD,
  FILTER_CONTROL,
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
} from "@/lib/filter-field-classes";
import { RecordingCard, type RecordingCardData } from "@/components/recordings/recording-card";
import { FilterMultiSelect, type FilterMultiSelectOption } from "@/components/recordings/filter-multi-select";
import { AddVideoModal } from "@/components/recordings/add-video-modal";
import { RunConfigModal } from "@/components/recordings/run-config-modal";
import { ExportModal } from "@/components/recordings/export-modal";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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

// ---------------------------------------------------------------------------
// Filter draft — only filter fields (search + sort are immediate / URL-direct)
// ---------------------------------------------------------------------------

interface RecordingsFilterDraft {
  status: ProcessingStatus[];
  templateIds: number[];
  sourceIds: number[];
  isMapped: boolean | null;
  includeBlank: boolean;
  includeDeleted: boolean;
  fromDate: string;
  toDate: string;
}

const DEFAULT_FILTER_DRAFT: RecordingsFilterDraft = {
  status: [],
  templateIds: [],
  sourceIds: [],
  isMapped: null,
  includeBlank: false,
  includeDeleted: false,
  fromDate: "",
  toDate: "",
};

function parsePositiveIntParams(sp: URLSearchParams, key: string): number[] {
  const xs = sp.getAll(key).map((s) => parseInt(s, 10)).filter((n) => !Number.isNaN(n) && n > 0);
  return [...new Set(xs)].sort((a, b) => a - b);
}

function parseIsMappedFromUrl(raw: string | null): boolean | null {
  if (raw === "true") return true;
  if (raw === "false") return false;
  return null;
}

function filterDraftFromUrl(sp: URLSearchParams): RecordingsFilterDraft {
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

function filterDraftSignature(d: RecordingsFilterDraft): string {
  return [
    [...d.status].sort().join(","),
    d.templateIds.join(","),
    d.sourceIds.join(","),
    d.isMapped === null ? "" : d.isMapped ? "1" : "0",
    d.includeBlank ? "1" : "0",
    d.includeDeleted ? "1" : "0",
    d.fromDate,
    d.toDate,
  ].join("|");
}

function advancedDraftCount(d: RecordingsFilterDraft): number {
  return (
    (d.isMapped !== null ? 1 : 0) +
    (d.fromDate ? 1 : 0) +
    (d.toDate ? 1 : 0) +
    (d.includeBlank ? 1 : 0) +
    (d.includeDeleted ? 1 : 0)
  );
}

// ---------------------------------------------------------------------------
// RecordingsPagedResults
// ---------------------------------------------------------------------------

interface RecordingsPagedResultsProps {
  queryParamsString: string;
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
}

function RecordingsPagedResults({
  queryParamsString,
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
}: RecordingsPagedResultsProps) {
  const [page, setPage] = useState(1);
  const [pipelineMenuOpen, setPipelineMenuOpen] = useState(false);
  const pipelineMenuRef = useRef<HTMLDivElement>(null);
  const qcInner = useQueryClient();

  const bulkDownload = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/download", { recording_ids: ids }),
    onSuccess: () => qcInner.invalidateQueries({ queryKey: ["recordings"] }),
  });
  const bulkTranscribe = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/transcribe", { recording_ids: ids }),
    onSuccess: () => qcInner.invalidateQueries({ queryKey: ["recordings"] }),
  });
  const bulkTopics = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/topics", { recording_ids: ids }),
    onSuccess: () => qcInner.invalidateQueries({ queryKey: ["recordings"] }),
  });
  const bulkSubtitles = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/subtitles", { recording_ids: ids }),
    onSuccess: () => qcInner.invalidateQueries({ queryKey: ["recordings"] }),
  });
  const bulkUpload = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/upload", { recording_ids: ids }),
    onSuccess: () => qcInner.invalidateQueries({ queryKey: ["recordings"] }),
  });

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

  const recordings = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const hasPrev = page > 1;
  const hasNext = page < totalPages;
  const isBulkLoading =
    bulkRun.isPending || bulkPause.isPending || bulkDelete.isPending || bulkReset.isPending ||
    bulkDownload.isPending || bulkTranscribe.isPending || bulkTopics.isPending ||
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
        <div className="py-16 text-center text-sm text-gray-400">
          {hasActiveFilters ? "No recordings match your filters" : "No recordings yet"}
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

      {data && data.total > 0 && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-gray-600">
            Page {page} of {totalPages}
            <span className="text-gray-400"> · </span>
            {data.total} recording{data.total !== 1 ? "s" : ""}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!hasPrev}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={!hasNext}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
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
  draft: RecordingsFilterDraft;
  patchDraft: (patch: Partial<RecordingsFilterDraft>) => void;
  draftAdvancedCount: number;
}

function AdvancedFiltersSection({
  draft,
  patchDraft,
  draftAdvancedCount,
}: AdvancedFiltersSectionProps) {
  const [sectionOpen, setSectionOpen] = useState(() => draftAdvancedCount > 0);

  return (
    <div className="border-t border-gray-100 pt-4">
      <button
        type="button"
        onClick={() => setSectionOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg py-1 text-left text-sm font-semibold text-[#224C87] transition-colors hover:text-[#1a3d6e]"
        aria-expanded={sectionOpen}
      >
        <Filter size={16} className="shrink-0 opacity-90" />
        Scope &amp; visibility
        {draftAdvancedCount > 0 && (
          <span className="rounded-full bg-[#224C87]/15 px-2 py-0.5 text-xs font-semibold tabular-nums text-[#224C87]">
            {draftAdvancedCount}
          </span>
        )}
        <ChevronDown
          size={16}
          className={cn("ml-auto shrink-0 text-gray-400 transition-transform", sectionOpen && "rotate-180")}
        />
      </button>

      {sectionOpen && (
        <div className="mt-4 space-y-5">
          {/* Row 1 — date range on one line */}
          <div className="space-y-1.5">
            <span className={FILTER_LABEL}>Recording start date</span>
            <div className="flex items-center gap-3">
              <input
                type="date"
                aria-label="From date"
                value={draft.fromDate}
                onChange={(e) => patchDraft({ fromDate: e.target.value })}
                className={cn(FILTER_CONTROL, "max-w-[11rem]")}
              />
              <span className="text-gray-400 select-none">—</span>
              <input
                type="date"
                aria-label="To date"
                value={draft.toDate}
                onChange={(e) => patchDraft({ toDate: e.target.value })}
                className={cn(FILTER_CONTROL, "max-w-[11rem]")}
              />
            </div>
          </div>

          {/* Row 2 — three toggles */}
          <div className="flex flex-wrap gap-x-8 gap-y-4">
            <div className="space-y-1.5">
              <span className={FILTER_LABEL}>Template mapping</span>
              <div className={FILTER_SEGMENT_WRAP}>
                {([null, true, false] as const).map((val) => (
                  <button
                    key={String(val)}
                    type="button"
                    className={cn(
                      FILTER_SEGMENT_BTN,
                      draft.isMapped === val ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                    )}
                    onClick={() => patchDraft({ isMapped: val })}
                  >
                    {val === null ? "Any" : val ? "Mapped" : "Not mapped"}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <span className={FILTER_LABEL}>Blank recordings</span>
              <div className={FILTER_SEGMENT_WRAP}>
                <button
                  type="button"
                  className={cn(FILTER_SEGMENT_BTN, !draft.includeBlank ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
                  onClick={() => patchDraft({ includeBlank: false })}
                >
                  Standard
                </button>
                <button
                  type="button"
                  className={cn(FILTER_SEGMENT_BTN, draft.includeBlank ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
                  onClick={() => patchDraft({ includeBlank: true })}
                >
                  Include blanks
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <span className={FILTER_LABEL}>Deleted recordings</span>
              <div className={FILTER_SEGMENT_WRAP}>
                <button
                  type="button"
                  className={cn(FILTER_SEGMENT_BTN, !draft.includeDeleted ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
                  onClick={() => patchDraft({ includeDeleted: false })}
                >
                  Standard
                </button>
                <button
                  type="button"
                  className={cn(FILTER_SEGMENT_BTN, draft.includeDeleted ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
                  onClick={() => patchDraft({ includeDeleted: true })}
                >
                  Include deleted
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main content
// ---------------------------------------------------------------------------

function RecordingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const urlKey = searchParams.toString();

  // --- Immediate controls (search + sort) ---
  const urlSearch = searchParams.get("search") ?? "";
  const urlSortBy = (() => {
    const raw = searchParams.get("sort_by") ?? "start_time";
    return SORT_BY_ALLOWED.has(raw) ? raw : "start_time";
  })();
  const urlSortOrder: "asc" | "desc" = searchParams.get("sort_order") === "asc" ? "asc" : "desc";

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
    router.replace(`?${p.toString()}`);
    setSelected(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  function updateSort(field?: string, order?: string) {
    const p = new URLSearchParams(searchParams.toString());
    if (field !== undefined) p.set("sort_by", field);
    if (order !== undefined) p.set("sort_order", order);
    router.replace(`?${p.toString()}`);
    setSelected(new Set());
  }

  // --- Filter draft (Apply/Reset pattern) ---
  const [filterDraft, setFilterDraft] = useState<RecordingsFilterDraft>(() =>
    filterDraftFromUrl(searchParams)
  );

  const patchDraft = useCallback((patch: Partial<RecordingsFilterDraft>) => {
    setFilterDraft((d) => ({ ...d, ...patch }));
  }, []);

  const appliedFilterDraft = useMemo(() => filterDraftFromUrl(new URLSearchParams(urlKey)), [urlKey]);
  const filtersDirty = useMemo(
    () => filterDraftSignature(filterDraft) !== filterDraftSignature(appliedFilterDraft),
    [filterDraft, appliedFilterDraft]
  );
  const draftAdvCount = advancedDraftCount(filterDraft);

  const hasAppliedFilters = useMemo(() => {
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

  // --- Dropdown state ---
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false);
  const [templateDropdownOpen, setTemplateDropdownOpen] = useState(false);
  const [sourceDropdownOpen, setSourceDropdownOpen] = useState(false);

  function closeAllDropdowns() {
    setStatusDropdownOpen(false);
    setTemplateDropdownOpen(false);
    setSourceDropdownOpen(false);
  }

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

  const toggleDraftTemplateId = useCallback((id: number) => {
    setFilterDraft((d) => {
      const next = d.templateIds.includes(id)
        ? d.templateIds.filter((x) => x !== id)
        : [...d.templateIds, id].sort((a, b) => a - b);
      return { ...d, templateIds: next };
    });
  }, []);

  const toggleDraftSourceId = useCallback((id: number) => {
    setFilterDraft((d) => {
      const next = d.sourceIds.includes(id)
        ? d.sourceIds.filter((x) => x !== id)
        : [...d.sourceIds, id].sort((a, b) => a - b);
      return { ...d, sourceIds: next };
    });
  }, []);

  const toggleDraftStatus = useCallback((s: ProcessingStatus) => {
    setFilterDraft((d) => ({
      ...d,
      status: d.status.includes(s) ? d.status.filter((x) => x !== s) : [...d.status, s],
    }));
  }, []);

  // --- Loading tracking per recording ---
  const [loadingRecordingId, setLoadingRecordingId] = useState<number | null>(null);

  // --- Apply / Reset ---
  function applyFilters() {
    const p = new URLSearchParams();
    const trimmedSearch = searchInput.trim();
    if (trimmedSearch) { p.set("search", trimmedSearch); lastAppliedSearchRef.current = trimmedSearch; }
    p.set("sort_by", urlSortBy);
    p.set("sort_order", urlSortOrder);
    filterDraft.status.forEach((s) => p.append("status", s));
    filterDraft.templateIds.forEach((id) => p.append("template_id", String(id)));
    filterDraft.sourceIds.forEach((id) => p.append("source_id", String(id)));
    if (filterDraft.isMapped !== null) p.set("is_mapped", filterDraft.isMapped ? "true" : "false");
    if (filterDraft.includeBlank) p.set("include_blank", "true");
    if (filterDraft.includeDeleted) p.set("include_deleted", "true");
    if (filterDraft.fromDate) p.set("from_date", filterDraft.fromDate);
    if (filterDraft.toDate) p.set("to_date", filterDraft.toDate);
    router.replace(`?${p.toString()}`);
    setSelected(new Set());
    closeAllDropdowns();
  }

  function resetAllFilters() {
    setFilterDraft(DEFAULT_FILTER_DRAFT);
    setSearchInput("");
    lastAppliedSearchRef.current = "";
    router.replace("?");
    setSelected(new Set());
    closeAllDropdowns();
  }

  // --- Mutations ---
  const bulkRun = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/run", { recording_ids: ids }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recordings"] }); setSelected(new Set()); },
  });

  const bulkPause = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/pause", { recording_ids: ids }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recordings"] }); setSelected(new Set()); },
  });

  const bulkDelete = useMutation({
    mutationFn: (ids: number[]) => apiClient.post("/recordings/bulk/delete", { recording_ids: ids }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recordings"] }); setSelected(new Set()); },
  });

  // Bulk reset: parallel individual reset calls
  const bulkReset = useMutation({
    mutationFn: ({ ids, deleteFiles }: { ids: number[]; deleteFiles: boolean }) =>
      Promise.all(ids.map((id) => apiClient.post(`/recordings/${id}/reset`, null, { params: { delete_files: deleteFiles } }))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["recordings"] }); setSelected(new Set()); },
  });

  const singleRun = useMutation({
    mutationFn: (id: number) => apiClient.post(`/recordings/${id}/run`),
    onMutate: (id) => setLoadingRecordingId(id),
    onSettled: () => setLoadingRecordingId(null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
  });

  const singlePause = useMutation({
    mutationFn: (id: number) => apiClient.post(`/recordings/${id}/pause`),
    onMutate: (id) => setLoadingRecordingId(id),
    onSettled: () => setLoadingRecordingId(null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
  });

  const singleReset = useMutation({
    mutationFn: ({ id, deleteFiles }: { id: number; deleteFiles: boolean }) =>
      apiClient.post(`/recordings/${id}/reset`, null, { params: { delete_files: deleteFiles } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
  });

  const singleDelete = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/recordings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
  });

  const singleRestore = useMutation({
    mutationFn: (id: number) => apiClient.post(`/recordings/${id}/restore`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
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
  const appliedKey = urlKey;

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      {/* Page header */}
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
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

      {/* ── Search + Sort toolbar (immediate) ── */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1 space-y-1.5" style={{ maxWidth: "22rem" }}>
          <label htmlFor="recordings-search" className={FILTER_LABEL}>
            Search
          </label>
          <input
            id="recordings-search"
            type="search"
            placeholder="By display name…"
            autoComplete="off"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className={FILTER_CONTROL}
          />
        </div>

        <div className="space-y-1.5">
          <span className={FILTER_LABEL}>Sort by</span>
          <div className="flex gap-1.5">
            <select
              value={urlSortBy}
              onChange={(e) => updateSort(e.target.value)}
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
              title={urlSortOrder === "desc" ? "Descending" : "Ascending"}
              onClick={() => updateSort(undefined, urlSortOrder === "desc" ? "asc" : "desc")}
              className={cn(FILTER_CONTROL, "w-11 shrink-0 px-0 text-center font-mono")}
            >
              {urlSortOrder === "desc" ? "↓" : "↑"}
            </button>
          </div>
        </div>

      </div>

      {/* ── Filter card (Apply/Reset pattern) ── */}
      <div className={FILTER_CARD}>
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-12 lg:items-end">
          {/* Status */}
          <div className="lg:col-span-3">
            <FilterMultiSelect<ProcessingStatus>
              label="Status"
              emptySummary="All statuses"
              selectedIds={filterDraft.status}
              options={STATUS_OPTIONS}
              open={statusDropdownOpen}
              onOpenChange={(next) => {
                setStatusDropdownOpen(next);
                if (next) { setTemplateDropdownOpen(false); setSourceDropdownOpen(false); }
              }}
              onToggle={toggleDraftStatus}
            />
          </div>

          {/* Templates */}
          <div className="lg:col-span-3">
            <FilterMultiSelect
              label="Templates"
              emptySummary="All templates"
              selectedIds={filterDraft.templateIds}
              options={templateOptions}
              open={templateDropdownOpen}
              onOpenChange={(next) => {
                setTemplateDropdownOpen(next);
                if (next) { setStatusDropdownOpen(false); setSourceDropdownOpen(false); }
              }}
              onToggle={toggleDraftTemplateId}
            />
          </div>

          {/* Sources */}
          <div className="lg:col-span-3">
            <FilterMultiSelect
              label="Sources"
              emptySummary="All sources"
              selectedIds={filterDraft.sourceIds}
              options={sourceOptions}
              open={sourceDropdownOpen}
              onOpenChange={(next) => {
                setSourceDropdownOpen(next);
                if (next) { setStatusDropdownOpen(false); setTemplateDropdownOpen(false); }
              }}
              onToggle={toggleDraftSourceId}
            />
          </div>

          {/* Apply + Reset */}
          <div className="lg:col-span-3">
            <span className={FILTER_LABEL} aria-hidden>&nbsp;</span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={!filtersDirty}
                onClick={applyFilters}
                className={cn(
                  "flex-1 min-h-[2.5rem] rounded-xl px-3 py-2 text-sm font-semibold text-white transition-colors",
                  filtersDirty ? "bg-[#224C87] hover:bg-[#1a3d6e]" : "cursor-not-allowed bg-[#224C87]/35"
                )}
              >
                Apply
              </button>
              <button
                type="button"
                onClick={resetAllFilters}
                disabled={!(filtersDirty || hasAppliedFilters)}
                className="flex-1 min-h-[2.5rem] rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Reset
              </button>
            </div>
          </div>
        </div>

        <AdvancedFiltersSection
          draft={filterDraft}
          patchDraft={patchDraft}
          draftAdvancedCount={draftAdvCount}
        />
      </div>

      {/* Results */}
      <RecordingsPagedResults
        key={appliedKey}
        queryParamsString={urlKey}
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
      />

      {/* Backdrop to close filter dropdowns */}
      {(statusDropdownOpen || templateDropdownOpen || sourceDropdownOpen) && (
        <div
          className="fixed inset-0 z-[35]"
          aria-hidden
          onClick={closeAllDropdowns}
        />
      )}

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
        appliedFilterParams={urlKey}
      />

      <AddVideoModal open={addModalOpen} onClose={() => setAddModalOpen(false)} />
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
