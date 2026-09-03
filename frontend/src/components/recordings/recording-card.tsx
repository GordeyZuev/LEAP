"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { ArchiveRestore, ExternalLink, MoreHorizontal, Pause, Pencil, Play, RotateCcw, Settings2, Trash2 } from "lucide-react";
import { cn, formatDate, stripLeadingTimestamp } from "@/lib/utils";
import { formatShareStatsSummary, type ShareStatsSummary } from "@/lib/share-stats";
import { type ProcessingStatus } from "@/components/ui/status-badge";
import { ProgressBar } from "@/components/ui/progress-bar";
import { RecordingPoster, RECORDING_CARD_POSTER } from "@/components/recordings/recording-poster";
import { PipelineStatusButton } from "@/components/recordings/pipeline-popover";
import {
  formatFailedStage,
  type PipelineStage,
} from "@/components/recordings/pipeline-stages";

interface UploadInfo { status: string; url: string | null }
interface SourceInfo { type: string; name: string | null; input_source_id: number | null }

export interface RecordingCardData {
  id: number;
  display_name: string;
  /** Presigned preview image; null when nothing to show yet. */
  poster_url?: string | null;
  poster_source?: "thumbnail" | "frame" | null;
  poster_fallback_url?: string | null;
  status: ProcessingStatus;
  start_time: string;
  duration: number;
  failed: boolean;
  on_pause: boolean;
  on_air: boolean;
  source: SourceInfo | null;
  template_id: number | null;
  template_name: string | null;
  can_run: boolean;
  can_pause: boolean;
  ready_to_upload: boolean;
  uploads: Record<string, UploadInfo>;
  share_token?: string | null;
  share_stats?: ShareStatsSummary | null;
  soft_deleted_at?: string | null;
  processing_stages?: PipelineStage[];
  failed_at_stage?: string | null;
}

interface RecordingCardProps {
  recording: RecordingCardData;
  selected: boolean;
  onToggleSelect: (id: number) => void;
  /** Any card selected — keeps every selector visible while selecting. */
  selectMode?: boolean;
  onRun: (id: number) => void;
  onPause: (id: number) => void;
  onRunWithConfig?: (id: number) => void;
  onReset?: (id: number) => void;
  onDelete?: (id: number) => void;
  onRestore?: (id: number) => void;
  onRename?: (id: number, name: string) => void;
  loadingId?: number | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  vk: "VK",
  yandex_disk: "YaDisk",
};

const UPLOAD_DOT: Record<string, string> = {
  UPLOADED:     "bg-success-fg",
  UPLOADING:    "bg-primary animate-pulse",
  FAILED:       "bg-danger-fg",
  NOT_UPLOADED: "bg-transparent ring-1 ring-inset ring-input",
};

const RUN_UNAVAILABLE = "Run is unavailable: this recording has no source file ready, or the pipeline is already running.";

function runButtonTitle(r: RecordingCardData): string {
  if (!r.can_run) return RUN_UNAVAILABLE;
  if (r.status === "PENDING_CONVERSION") {
    return "Run to check MTS Link conversion progress";
  }
  if (r.status === "PENDING_SOURCE" && r.source?.type === "MTS_LINK") {
    return "Run when MTS Link finishes assembling the recording";
  }
  return "Run the pipeline";
}

const UPLOAD_STATE_LABEL: Record<string, string> = {
  UPLOADED: "published",
  UPLOADING: "uploading",
  FAILED: "upload failed",
  NOT_UPLOADED: "not uploaded",
};

const CARD_TITLE =
  "line-clamp-2 min-h-[2.75rem] text-sm font-semibold leading-snug break-words";

// ---------------------------------------------------------------------------
// Kebab menu item
// ---------------------------------------------------------------------------

function MenuItem({ icon: Icon, label, onClick, danger }: {
  icon: React.ComponentType<{ size?: number }>;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium transition-colors hover:bg-muted",
        danger ? "text-danger-fg hover:bg-danger-fg/10" : "text-secondary-foreground"
      )}
    >
      <Icon size={13} />
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

export function RecordingCard({
  recording: r,
  selected,
  onToggleSelect,
  selectMode = false,
  onRun,
  onPause,
  onRunWithConfig,
  onReset,
  onDelete,
  onRestore,
  onRename,
  loadingId,
}: RecordingCardProps) {
  const isLoading = loadingId === r.id;
  const uploads = Object.entries(r.uploads);
  const isSoftDeleted = !!r.soft_deleted_at;
  const isProcessing = r.status === "DOWNLOADING" || r.status === "PROCESSING" || r.status === "UPLOADING";

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(r.display_name);
  const inputRef = useRef<HTMLInputElement>(null);

  const hasKebab = !!(onReset || onDelete || onRename || r.can_pause);

  useEffect(() => {
    if (!menuOpen) return;
    const h = (e: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("pointerdown", h);
    return () => document.removeEventListener("pointerdown", h);
  }, [menuOpen]);

  const startEdit = useCallback(() => {
    if (!onRename) return;
    setEditName(r.display_name);
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 0);
  }, [onRename, r.display_name]);

  const commitEdit = useCallback(() => {
    const t = editName.trim();
    if (t && t !== r.display_name) onRename?.(r.id, t);
    setEditing(false);
  }, [editName, r.display_name, r.id, onRename]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
    setEditName(r.display_name);
  }, [r.display_name]);

  return (
    <div
      className={cn(
        "group relative flex h-full min-w-0 flex-col rounded-xl border p-2 transition-[box-shadow,border-color,background-color] duration-150",
        isSoftDeleted && "opacity-60",
        selected
          ? "border-primary bg-card shadow-sm ring-2 ring-primary/20"
          : "border-transparent hover:border-border/60 hover:bg-primary/[0.07] hover:shadow-sm",
      )}
    >
      <div className="relative overflow-hidden rounded-lg">
        <Link href={`/recordings/${r.id}`} tabIndex={-1} aria-hidden="true" className="block">
          <RecordingPoster
            recordingId={r.id}
            posterUrl={r.poster_url}
            posterFallbackUrl={r.poster_fallback_url}
            duration={r.duration}
            className={RECORDING_CARD_POSTER}
          />
        </Link>

        <button
          type="button"
          onClick={() => onToggleSelect(r.id)}
          role="checkbox"
          aria-checked={selected}
          aria-label={`Select ${r.display_name}`}
          className={cn(
            "absolute start-2 top-2 grid size-6 place-items-center rounded-md border-2 transition-opacity",
            "focus-visible:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-primary/40",
            selected ? "border-primary bg-primary" : "border-white bg-black/50",
            "opacity-0 group-hover:opacity-100 [@media(hover:none)]:opacity-100",
            (selected || selectMode) && "opacity-100",
          )}
        >
          {selected && (
            <svg width="12" height="10" viewBox="0 0 10 8" fill="none" className="text-white" aria-hidden="true" focusable="false">
              <path d="M1 4L3.5 6.5L9 1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </button>

        {isProcessing && (
          <ProgressBar variant="indeterminate" className="absolute inset-x-0 bottom-0 h-0.5 rounded-none" />
        )}
      </div>

      <div className="relative flex flex-1 flex-col pt-3">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-2">
          {editing ? (
            <input
              ref={inputRef}
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onBlur={commitEdit}
              onKeyDown={(e) => {
                if (e.key === "Enter") { e.preventDefault(); commitEdit(); }
                if (e.key === "Escape") { e.preventDefault(); cancelEdit(); }
              }}
              className="col-span-2 w-full rounded border border-primary/40 px-1.5 py-0.5 text-sm font-semibold text-foreground outline-none ring-1 ring-primary/30"
              autoFocus
            />
          ) : (
            <Link
              href={`/recordings/${r.id}`}
              title={r.display_name}
              className={cn(
                CARD_TITLE,
                isSoftDeleted ? "text-muted-foreground line-through" : "text-foreground hover:text-primary",
              )}
            >
              {stripLeadingTimestamp(r.display_name)}
            </Link>
          )}

          {!editing && hasKebab && (
            <div className="relative shrink-0" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                aria-label="More actions"
                aria-expanded={menuOpen}
                className={cn(
                  "flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-secondary-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                  menuOpen && "bg-muted text-secondary-foreground",
                )}
              >
                <MoreHorizontal size={18} />
              </button>
              {menuOpen && (
                <div
                  className="absolute end-0 top-full z-30 mt-1 w-40 origin-top overflow-hidden rounded-xl border border-border bg-card shadow-lg animate-dropdown-in"
                >
                  {onRename && (
                    <MenuItem icon={Pencil} label="Rename" onClick={() => { setMenuOpen(false); startEdit(); }} />
                  )}
                  {r.can_pause && (
                    <MenuItem icon={Pause} label="Pause" onClick={() => { setMenuOpen(false); onPause(r.id); }} />
                  )}
                  {onReset && (
                    <MenuItem icon={RotateCcw} label="Reset" onClick={() => { setMenuOpen(false); onReset(r.id); }} />
                  )}
                  {(onRename || r.can_pause || onReset) && onDelete && (
                    <div className="my-1 border-t border-border" />
                  )}
                  {onDelete && (
                    <MenuItem icon={Trash2} label="Delete" onClick={() => { setMenuOpen(false); onDelete(r.id); }} danger />
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="mt-2 flex flex-col gap-2">
          <p className="min-w-0 truncate text-xs text-muted-foreground">
            <span title={r.source?.type ?? undefined}>{r.source?.type ?? "—"}</span>
            {" · "}
            <span className="tabular-nums">{formatDate(r.start_time)}</span>
          </p>

          {(uploads.length > 0 || r.share_token) && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {r.share_token && (
                <a
                  href={`/share/${r.share_token}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  title={formatShareStatsSummary(r.share_stats) || undefined}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-success-fg">
                    <span className="sr-only">active</span>
                  </span>
                  LEAP
                  <ExternalLink size={9} className="opacity-40" />
                </a>
              )}
              {uploads.map(([platform, info]) => {
                const dotCls = UPLOAD_DOT[info.status] ?? UPLOAD_DOT["NOT_UPLOADED"];
                const label = PLATFORM_LABELS[platform] ?? platform;
                const isLinked = info.url && info.status === "UPLOADED";
                const stateLabel = UPLOAD_STATE_LABEL[info.status] ?? "unknown state";
                const dot = (
                  <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotCls)}>
                    <span className="sr-only">{stateLabel}</span>
                  </span>
                );
                if (isLinked) {
                  return (
                    <a
                      key={platform}
                      href={info.url!}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      {dot}{label}<ExternalLink size={9} className="opacity-40" />
                    </a>
                  );
                }
                return (
                  <span key={platform} className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    {dot}{label}
                  </span>
                );
              })}
            </div>
          )}
        </div>

        <div className="mt-auto flex items-center justify-between gap-2 pt-2">
          <div className="flex shrink-0">
          {isSoftDeleted && onRestore ? (
            <button
              type="button"
              disabled={isLoading}
              onClick={() => onRestore(r.id)}
              className="inline-flex h-7 items-center gap-1 rounded-lg px-2.5 text-xs font-medium text-success-fg hover:bg-success-fg/10 disabled:opacity-50"
            >
              <ArchiveRestore size={12} /> Restore
            </button>
          ) : (
            <div className="flex">
              <button
                type="button"
                disabled={!r.can_run || isLoading}
                onClick={() => onRun(r.id)}
                title={runButtonTitle(r)}
                aria-describedby={r.can_run ? undefined : `run-why-${r.id}`}
                className={cn(
                  "inline-flex h-7 items-center gap-1 border border-border px-2.5 text-xs font-medium text-secondary-foreground transition-colors",
                  "disabled:cursor-not-allowed disabled:opacity-40",
                  onRunWithConfig
                    ? "rounded-l-lg border-e-0 hover:border-primary hover:bg-primary hover:text-white"
                    : "rounded-lg hover:border-primary hover:bg-primary hover:text-white",
                )}
              >
                <Play size={11} /> Run
              </button>
              {!r.can_run && (
                <span id={`run-why-${r.id}`} className="sr-only">{RUN_UNAVAILABLE}</span>
              )}
              {onRunWithConfig && (
                <button
                  type="button"
                  disabled={isLoading}
                  onClick={() => onRunWithConfig(r.id)}
                  title="Run with config"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-e-lg border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-secondary-foreground disabled:opacity-40"
                >
                  <Settings2 size={11} />
                </button>
              )}
            </div>
          )}
          </div>

          <div className="flex min-w-0 items-center justify-end gap-2">
            <PipelineStatusButton
              status={r.status}
              failed={r.failed}
              failedStage={formatFailedStage(r.failed_at_stage)}
              stages={r.processing_stages}
              size="control"
              className="min-w-0 shrink overflow-hidden"
            />
            {r.on_pause && (
              <span className="inline-flex h-7 shrink-0 items-center rounded-full bg-warning-fg/10 px-2.5 text-xs font-medium text-warning-fg">
                Paused
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
