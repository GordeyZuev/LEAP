"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, ExternalLink, MoreHorizontal, Pause, Play, RotateCcw, Settings2, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { StatusBadge, type ProcessingStatus } from "@/components/ui/status-badge";

interface UploadInfo {
  status: string;
  url: string | null;
}

interface SourceInfo {
  type: string;
  name: string | null;
  input_source_id: number | null;
}

export interface RecordingCardData {
  id: number;
  display_name: string;
  status: ProcessingStatus;
  start_time: string;
  duration: number;
  failed: boolean;
  on_pause: boolean;
  source: SourceInfo | null;
  template_id: number | null;
  template_name: string | null;
  can_run: boolean;
  can_pause: boolean;
  ready_to_upload: boolean;
  uploads: Record<string, UploadInfo>;
}

interface RecordingCardProps {
  recording: RecordingCardData;
  selected: boolean;
  onToggleSelect: (id: number) => void;
  onRun: (id: number) => void;
  onPause: (id: number) => void;
  onRunWithConfig?: (id: number) => void;
  onReset?: (id: number) => void;
  onDelete?: (id: number) => void;
  loadingId?: number | null;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function formatDuration(seconds: number) {
  if (seconds === 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  vk: "VK",
  yandex_disk: "YaDisk",
};

const UPLOAD_STATUS_CONFIG: Record<string, { dot: string; text: string }> = {
  UPLOADED:     { dot: "bg-green-400",                   text: "text-green-600" },
  UPLOADING:    { dot: "bg-blue-400 animate-pulse",      text: "text-blue-600" },
  FAILED:       { dot: "bg-red-400",                     text: "text-red-500" },
  NOT_UPLOADED: { dot: "bg-gray-300",                    text: "text-gray-400" },
};

// ---------------------------------------------------------------------------
// Kebab menu item
// ---------------------------------------------------------------------------

function MenuItem({
  icon: Icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
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
  onRun,
  onPause,
  onRunWithConfig,
  onReset,
  onDelete,
  loadingId,
}: RecordingCardProps) {
  const isLoading = loadingId === r.id;
  const uploadEntries = Object.entries(r.uploads);

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const hasMenuItems = !!(onRunWithConfig || onReset || onDelete);

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    function onPointerDown(e: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [menuOpen]);

  return (
    <div
      className={cn(
        "flex flex-col rounded-2xl border bg-white transition-all duration-150",
        selected
          ? "border-[#224C87] shadow-md ring-1 ring-[#224C87]/20"
          : "border-[#D9D9D9] shadow-sm hover:border-[#224C87]/30 hover:shadow-md"
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2 px-4 pb-2 pt-4">
        <input
          type="checkbox"
          className="mt-0.5 shrink-0 rounded accent-[#224C87]"
          checked={selected}
          onChange={() => onToggleSelect(r.id)}
        />
        <StatusBadge status={r.status} failed={r.failed} />
      </div>

      {/* Title */}
      <div className="px-4 pb-1">
        <Link
          href={`/recordings/${r.id}`}
          className="line-clamp-2 text-sm font-semibold leading-snug text-gray-900 transition-colors hover:text-[#224C87]"
        >
          {r.display_name}
        </Link>
      </div>

      {/* Meta row */}
      <div className="px-4 pb-2">
        <p className="truncate text-xs text-gray-400">
          {r.source?.type ?? "—"}
          {r.duration > 0 && <> · {formatDuration(r.duration)}</>}
          {" · "}{formatDate(r.start_time)}
        </p>
        {r.template_name && (
          <p className="mt-0.5 truncate text-xs text-[#224C87]/70">
            Template: {r.template_name}
          </p>
        )}
      </div>

      {/* Uploads */}
      {uploadEntries.length > 0 && (
        <div className="flex flex-wrap gap-2 px-4 pb-3">
          {uploadEntries.map(([platform, info]) => {
            const cfg = UPLOAD_STATUS_CONFIG[info.status] ?? UPLOAD_STATUS_CONFIG["NOT_UPLOADED"];
            return (
              <span
                key={platform}
                className={cn("inline-flex items-center gap-1 text-xs font-medium", cfg.text)}
              >
                <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
                {PLATFORM_LABELS[platform] ?? platform}
                {info.url && info.status === "UPLOADED" && (
                  <a
                    href={info.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink size={10} className="opacity-60 hover:opacity-100" />
                  </a>
                )}
              </span>
            );
          })}
        </div>
      )}

      <div className="flex-1" />

      {/* Actions */}
      <div className="flex items-center gap-2 border-t border-[#D9D9D9] px-4 pb-4 pt-2">
        <button
          disabled={!r.can_run || isLoading}
          onClick={() => onRun(r.id)}
          className="flex items-center gap-1.5 rounded-xl border border-[#D9D9D9] bg-white px-3 py-1.5 text-xs font-medium transition-colors hover:border-[#224C87] hover:bg-[#224C87] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Play size={12} />
          Run
        </button>
        <button
          disabled={!r.can_pause || isLoading}
          onClick={() => onPause(r.id)}
          className="flex items-center gap-1.5 rounded-xl border border-[#D9D9D9] bg-white px-3 py-1.5 text-xs font-medium transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Pause size={12} />
          Pause
        </button>

        <div className="flex-1" />

        {/* Kebab menu */}
        {hasMenuItems && (
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-xl border border-[#D9D9D9] bg-white text-gray-500 transition-colors hover:bg-gray-50",
                menuOpen && "border-[#224C87]/30 bg-[#224C87]/5 text-[#224C87]"
              )}
              aria-label="More actions"
            >
              <MoreHorizontal size={14} />
            </button>

            {menuOpen && (
              <div className="absolute bottom-full right-0 z-20 mb-1.5 w-44 overflow-hidden rounded-xl border border-[#D9D9D9] bg-white shadow-lg">
                {onRunWithConfig && (
                  <MenuItem
                    icon={Settings2}
                    label="Run with config…"
                    onClick={() => { setMenuOpen(false); onRunWithConfig(r.id); }}
                  />
                )}
                {onReset && (
                  <MenuItem
                    icon={RotateCcw}
                    label="Reset"
                    onClick={() => { setMenuOpen(false); onReset(r.id); }}
                  />
                )}
                {(onRunWithConfig || onReset) && onDelete && (
                  <div className="my-1 border-t border-[#F0F0F0]" />
                )}
                {onDelete && (
                  <MenuItem
                    icon={Trash2}
                    label="Delete"
                    onClick={() => { setMenuOpen(false); onDelete(r.id); }}
                    danger
                  />
                )}
              </div>
            )}
          </div>
        )}

        <Link
          href={`/recordings/${r.id}`}
          className="flex h-8 w-8 items-center justify-center rounded-xl border border-[#D9D9D9] bg-white transition-colors hover:border-[#224C87] hover:bg-[#224C87] hover:text-white"
        >
          <ArrowRight size={14} />
        </Link>
      </div>
    </div>
  );
}
