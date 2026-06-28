"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { ExternalLink, MoreHorizontal, Pause, Play, RotateCcw, Settings2, Trash2, ArchiveRestore } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { StatusBadge, type ProcessingStatus } from "@/components/ui/status-badge";
import type { PipelineStage } from "@/components/ui/pipeline-progress";

interface UploadInfo { status: string; url: string | null }
interface SourceInfo { type: string; name: string | null; input_source_id: number | null }

export interface RecordingCardData {
  id: number;
  display_name: string;
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

function formatDuration(s: number) {
  if (s === 0) return null;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  vk: "VK",
  yandex_disk: "YaDisk",
};

const UPLOAD_DOT: Record<string, string> = {
  UPLOADED:     "bg-green-400",
  UPLOADING:    "bg-blue-400 animate-pulse",
  FAILED:       "bg-red-400",
  NOT_UPLOADED: "bg-gray-300",
};

// ---------------------------------------------------------------------------
// StatusDot — small coloured circle in top-right; hover shows status + pipeline
// ---------------------------------------------------------------------------


const STAGE_ORDER = ["DOWNLOAD", "TRIM", "TRANSCRIBE", "EXTRACT_TOPICS", "GENERATE_SUBTITLES"] as const;
const STAGE_NAME: Record<string, string> = {
  DOWNLOAD: "Download",
  TRIM: "Trim",
  TRANSCRIBE: "Transcribe",
  EXTRACT_TOPICS: "Topics",
  GENERATE_SUBTITLES: "Subtitles",
};

export function StatusDot({ status, failed, stages }: {
  status: ProcessingStatus;
  failed: boolean;
  stages?: PipelineStage[];
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <StatusBadge status={status} failed={failed} className="cursor-default" />

      {open && !!stages?.length && (
        <div className="absolute right-0 top-full z-30 pt-2">
          <div className="w-44 overflow-hidden rounded-lg border border-gray-100 bg-white shadow-md">
            <div className="border-t border-gray-100 px-3 py-2 space-y-1.5">
              {STAGE_ORDER.map((key) => {
                const st = stages.find((s) => s.stage_type === key);
                const state = st?.failed ? "FAILED" : (st?.status ?? "PENDING");
                const dotCls = cn("mt-px h-1.5 w-1.5 shrink-0 rounded-full",
                  state === "COMPLETED"   ? "bg-green-500" :
                  state === "IN_PROGRESS" ? "bg-blue-500 animate-pulse" :
                  state === "FAILED"      ? "bg-red-500" : "bg-gray-200"
                );
                const dur = st?.duration_seconds;
                return (
                  <div key={key}>
                    <div className="flex items-start gap-1.5 text-xs">
                      <span className={dotCls} />
                      <span className={cn("flex-1 leading-none",
                        state === "FAILED"    ? "font-medium text-red-600" :
                        state === "COMPLETED" ? "text-gray-600" : "text-gray-400"
                      )}>
                        {STAGE_NAME[key]}
                      </span>
                      {dur != null && (
                        <span className="tabular-nums text-gray-400">
                          {dur < 60 ? `${Math.round(dur)}s` : `${Math.floor(dur / 60)}m`}
                        </span>
                      )}
                    </div>
                    {st?.failed && st.failed_reason && (
                      <p className="mt-0.5 ml-3 text-[10px] leading-relaxed text-red-500 line-clamp-2">
                        {st.failed_reason}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


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
        "flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium transition-colors hover:bg-gray-50",
        danger ? "text-red-500 hover:bg-red-50" : "text-gray-700"
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
  const dur = formatDuration(r.duration);

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(r.display_name);
  const inputRef = useRef<HTMLInputElement>(null);

  const hasKebab = !!(onReset || onDelete || r.can_pause);

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
  }, [onRename, r.display_name, selectMode]);

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
    <div className={cn(
      "group relative flex flex-col rounded-xl border bg-white transition-[box-shadow,border-color] duration-150",
      isSoftDeleted && "opacity-60",
      selected
        ? "border-[#224C87] ring-2 ring-[#224C87]/20 shadow-sm"
        : "border-gray-200 hover:shadow-md"
    )}>
      {/* ── Body ── */}
      <div className="flex flex-1 gap-2 px-3 pt-3 pb-3">
        {/* Checkbox — always in layout, opacity-only animation to avoid reflow */}
        <button
          type="button"
          onClick={() => onToggleSelect(r.id)}
          aria-label="Toggle selection"
          className={cn(
            "mt-0.5 shrink-0 h-5 w-5 flex items-center justify-center rounded border-2 transition-opacity duration-150",
            selected
              ? "border-[#224C87] bg-[#224C87] opacity-100"
              : selectMode
              ? "border-gray-300 bg-white opacity-100"
              : "border-gray-300 bg-white opacity-0 group-hover:opacity-100"
          )}
        >
          {selected && (
            <svg width="10" height="8" viewBox="0 0 10 8" fill="none" className="text-white">
              <path d="M1 4L3.5 6.5L9 1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </button>

        {/* Left: title · meta · template · platforms */}
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
              className="mb-1.5 w-full rounded border border-[#224C87]/40 px-1.5 py-0.5 text-sm font-semibold text-gray-900 outline-none ring-1 ring-[#224C87]/30"
              autoFocus
            />
          ) : (
            <div className="group/title mb-1.5 flex items-start gap-1">
              <Link
                href={`/recordings/${r.id}`}
                title={r.display_name}
                className={cn(
                  "line-clamp-2 text-sm font-semibold leading-snug [overflow-wrap:anywhere]",
                  isSoftDeleted ? "text-gray-400 line-through" : "text-gray-900 hover:text-[#224C87]"
                )}
              >
                {r.display_name}
              </Link>
              {!selectMode && onRename && (
                <button
                  type="button"
                  onClick={startEdit}
                  title="Rename"
                  className="mt-px shrink-0 text-gray-300 opacity-0 transition-opacity hover:text-[#224C87] group-hover/title:opacity-100"
                >
                  <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                    <path d="M7.5 1.5L9.5 3.5L3.5 9.5H1.5V7.5L7.5 1.5Z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              )}
            </div>
          )}

          {/* Meta */}
          <p className="truncate text-xs text-gray-400">
            {r.source?.type ?? "—"}
            {dur && <> · {dur}</>}
            {" · "}{formatDate(r.start_time)}
          </p>

          {/* Template */}
          {r.template_id != null && (
            <Link
              href={`/templates/${r.template_id}`}
              onClick={(e) => e.stopPropagation()}
              className="mt-0.5 block truncate text-xs text-[#224C87]/60 hover:text-[#224C87]"
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
                const dot = <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotCls)} />;
                if (isLinked) {
                  return (
                    <a
                      key={platform}
                      href={info.url!}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-1 text-xs text-[#224C87] hover:underline"
                    >
                      {dot}{label}<ExternalLink size={9} className="opacity-40" />
                    </a>
                  );
                }
                return (
                  <span key={platform} className="inline-flex items-center gap-1 text-xs text-gray-400">
                    {dot}{label}
                  </span>
                );
              })}
            </div>
          )}
        </div>

        {/* Right: status dot */}
        <div className="shrink-0 pt-0.5">
          <StatusDot status={r.status} failed={r.failed} stages={r.processing_stages} />
        </div>
      </div>

      {/* ── Footer: always visible ── */}
      <div className="flex items-center gap-1.5 border-t border-gray-100 px-3 py-2">
        {isSoftDeleted && onRestore ? (
          <button
            type="button"
            disabled={isLoading}
            onClick={() => onRestore(r.id)}
            className="flex h-7 items-center gap-1.5 rounded-xl border border-green-200 px-3 text-xs font-medium text-green-600 hover:bg-green-50 disabled:opacity-50"
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
                className={cn(
                  "flex h-7 items-center gap-1.5 border border-gray-200 px-3 text-xs font-medium text-gray-600 transition-colors",
                  "disabled:cursor-not-allowed disabled:opacity-40",
                  onRunWithConfig
                    ? "rounded-l-xl border-r-0 hover:border-[#224C87] hover:bg-[#224C87] hover:text-white"
                    : "rounded-xl hover:border-[#224C87] hover:bg-[#224C87] hover:text-white"
                )}
              >
                <Play size={11} /> Run
              </button>
              {onRunWithConfig && (
                <button
                  type="button"
                  disabled={isLoading}
                  onClick={() => onRunWithConfig(r.id)}
                  title="Run with config"
                  className="flex h-7 w-7 items-center justify-center rounded-r-xl border border-gray-200 text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-600 disabled:opacity-40"
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
                    "flex h-7 w-7 items-center justify-center rounded-xl border border-gray-200 text-gray-400 transition-colors hover:bg-gray-50",
                    menuOpen && "border-[#224C87]/30 bg-[#224C87]/5 text-[#224C87]"
                  )}
                >
                  <MoreHorizontal size={12} />
                </button>
                {menuOpen && (
                  <div className="absolute bottom-full right-0 z-30 mb-1.5 w-40 overflow-hidden rounded-xl border border-gray-100 bg-white shadow-lg">
                    {r.can_pause && (
                      <MenuItem icon={Pause} label="Pause" onClick={() => { setMenuOpen(false); onPause(r.id); }} />
                    )}
                    {onReset && (
                      <MenuItem icon={RotateCcw} label="Reset" onClick={() => { setMenuOpen(false); onReset(r.id); }} />
                    )}
                    {(r.can_pause || onReset) && onDelete && (
                      <div className="my-1 border-t border-gray-100" />
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
