"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { ArchiveRestore, ExternalLink, MoreHorizontal, Pause, Pencil, Play, RotateCcw, Settings2, Trash2 } from "lucide-react";
import { cn, formatDate, stripLeadingTimestamp } from "@/lib/utils";
import { type ProcessingStatus } from "@/components/ui/status-badge";
import { ProgressBar } from "@/components/ui/progress-bar";
import { RecordingPoster } from "@/components/recordings/recording-poster";
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
  /** Presigned poster frame; null when the recording has no video yet. */
  poster_url?: string | null;
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

/** Upload state in words — the dot alone carries it by colour otherwise. */
const UPLOAD_STATE_LABEL: Record<string, string> = {
  UPLOADED: "published",
  UPLOADING: "uploading",
  FAILED: "upload failed",
  NOT_UPLOADED: "not uploaded",
};


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
    // h-full + a footer pinned with mt-auto. Sizing cards to their content
    // instead left every row with a staircase of Run buttons; the earlier
    // problem it was meant to avoid — a white gap above the footer — came from
    // the missing mt-auto, not from stretching.
    <div className={cn(
      "group relative flex h-full flex-col rounded-xl border bg-card transition-[box-shadow,border-color] duration-150",
      isSoftDeleted && "opacity-60",
      selected
        ? "border-primary ring-2 ring-primary/20 shadow-sm"
        : "border-border hover:shadow-md"
    )}>
      {/* ── Body: thumbnail leads, everything else to its trailing side ── */}
      <div className="flex gap-3 p-3">
        {/* The thumbnail carries the duration and nothing else, the way a video
            host does it — status moved into the text column so it never covers
            a frame. */}
        <div className="relative w-32 shrink-0">
          <Link href={`/recordings/${r.id}`} tabIndex={-1} aria-hidden="true" className="block">
            <RecordingPoster
              recordingId={r.id}
              posterUrl={r.poster_url}
              duration={r.duration}
            />
          </Link>

          <button
            type="button"
            onClick={() => onToggleSelect(r.id)}
            role="checkbox"
            aria-checked={selected}
            aria-label={`Select ${r.display_name}`}
            className={cn(
              "absolute start-1.5 top-1.5 grid size-6 place-items-center rounded-md border-2 transition-opacity",
              "focus-visible:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-primary/40",
              selected ? "border-primary bg-primary" : "border-white bg-black/50",
              // Quiet at rest, so the thumbnail is the first thing seen. Revealed
              // on hover — but only where hover exists: `hover: none` keeps it
              // permanently visible, or selection would be unreachable on touch.
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
        </div>

        {/* Title · meta · template · platforms */}
        <div className="min-w-0 flex-1 flex flex-col">
          {/* Title row */}
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
              className="mb-1.5 w-full rounded border border-primary/40 px-1.5 py-0.5 text-sm font-semibold text-foreground outline-none ring-1 ring-primary/30"
              autoFocus
            />
          ) : (
            // Rename lives in the kebab menu — as a pencil it sat permanently in
            // the top-right of every card, competing with the title for width.
            // Two lines are reserved whether or not the title needs both, so
            // the status badge below starts at the same height on every card.
            <Link
              href={`/recordings/${r.id}`}
              title={r.display_name}
              className={cn(
                // 2.5rem clears two lines at text-sm/leading-snug (2 × 19.25px),
                // so one- and two-line titles occupy exactly the same box.
                "mb-1.5 line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-snug [overflow-wrap:anywhere]",
                isSoftDeleted ? "text-muted-foreground line-through" : "text-foreground hover:text-primary"
              )}
            >
              {stripLeadingTimestamp(r.display_name)}
            </Link>
          )}

          {/* Status leads the meta line: aligned across cards, and off the frame.
              Duration lives on the thumbnail badge, so it is not repeated here.
              The failed stage rides inside the badge rather than on its own red
              line — that line repeated the word "Failed" in a second, different
              red and added a row that only some cards had. */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <PipelineStatusButton
              status={r.status}
              failed={r.failed}
              failedStage={formatFailedStage(r.failed_at_stage)}
              stages={r.processing_stages}
              className="shrink-0"
            />
            {r.on_pause && (
              <span className="shrink-0 rounded-full bg-warning-fg/10 px-2 py-0.5 text-xs font-medium text-warning-fg">
                Paused
              </span>
            )}
            {/* min-w-0 is what makes `truncate` work at all here: nowrap gives
                a flex item an automatic minimum size of its full text width, so
                without it this line never ellipsised — it wrapped instead, and
                the card grew by a row whenever the badge ran long.
                Only the source name gives way; the date is the more useful half
                and truncating the tail would eat the year first. */}
            <p className="flex min-w-0 flex-1 items-baseline gap-1 text-xs text-muted-foreground">
              <span className="truncate" title={r.source?.type ?? undefined}>
                {r.source?.type ?? "—"}
              </span>
              <span className="shrink-0">·</span>
              <span className="shrink-0">{formatDate(r.start_time)}</span>
            </p>
          </div>

          {/* Template */}
          {r.template_id != null && (
            <Link
              href={`/templates/${r.template_id}`}
              onClick={(e) => e.stopPropagation()}
              className="mt-0.5 block truncate text-xs text-primary/60 hover:text-primary"
            >
              {r.template_name ?? `Template #${r.template_id}`}
            </Link>
          )}

          {/* Platforms — horizontal row */}
          {uploads.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
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
      </div>

      {/* ── Active processing strip ── */}
      {(r.status === "DOWNLOADING" || r.status === "PROCESSING" || r.status === "UPLOADING") && (
        <ProgressBar variant="indeterminate" className="h-0.5 rounded-none" />
      )}

      {/* ── Footer: always visible ── */}
      <div className="mt-auto flex items-center gap-1.5 border-t border-border px-3 py-2">
        {isSoftDeleted && onRestore ? (
          <button
            type="button"
            disabled={isLoading}
            onClick={() => onRestore(r.id)}
            className="flex h-7 items-center gap-1.5 rounded-xl border border-success-fg/50 px-3 text-xs font-medium text-success-fg hover:bg-success-fg/10 disabled:opacity-50"
          >
            <ArchiveRestore size={12} /> Restore
          </button>
        ) : (
          <>
            {/* Split Run button */}
            <div className="flex">
              <button
                type="button"
                disabled={!r.can_run || isLoading}
                onClick={() => onRun(r.id)}
                title={r.can_run ? "Run the pipeline" : RUN_UNAVAILABLE}
                aria-describedby={r.can_run ? undefined : `run-why-${r.id}`}
                className={cn(
                  "flex h-7 items-center gap-1.5 border border-border px-3 text-xs font-medium text-secondary-foreground transition-colors",
                  "disabled:cursor-not-allowed disabled:opacity-40",
                  onRunWithConfig
                    ? "rounded-l-xl border-r-0 hover:border-primary hover:bg-primary hover:text-white"
                    : "rounded-xl hover:border-primary hover:bg-primary hover:text-white"
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
                  className="flex h-7 w-7 items-center justify-center rounded-r-xl border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-secondary-foreground disabled:opacity-40"
                >
                  <Settings2 size={11} />
                </button>
              )}
            </div>

            <div className="flex-1" />

            {hasKebab && (
              <div className="relative" ref={menuRef}>
                <button
                  type="button"
                  onClick={() => setMenuOpen((v) => !v)}
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:bg-muted",
                    menuOpen && "border-primary/30 bg-primary/5 text-primary"
                  )}
                >
                  <MoreHorizontal size={12} />
                </button>
                {menuOpen && (
                  <div className="absolute bottom-full right-0 z-30 mb-1.5 w-40 overflow-hidden rounded-xl border border-border bg-card shadow-lg animate-dropdown-in" style={{ transformOrigin: "bottom right" }}>
                    {onRename && (
                      <MenuItem icon={Pencil} label="Rename" onClick={() => { setMenuOpen(false); startEdit(); }} />
                    )}
                    {r.can_pause && (
                      <MenuItem icon={Pause} label="Pause" onClick={() => { setMenuOpen(false); onPause(r.id); }} />
                    )}
                    {onReset && (
                      <MenuItem icon={RotateCcw} label="Reset" onClick={() => { setMenuOpen(false); onReset(r.id); }} />
                    )}
                    {(r.can_pause || onReset) && onDelete && (
                      <div className="my-1 border-t border-border" />
                    )}
                    {onDelete && (
                      <MenuItem icon={Trash2} label="Delete" onClick={() => { setMenuOpen(false); onDelete(r.id); }} danger />
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
