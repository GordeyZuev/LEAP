"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { ExternalLink, MoreHorizontal, Pause, Play, RotateCcw, Settings2, Trash2, ArchiveRestore } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { StatusDot, type RecordingCardData } from "./recording-card";

interface RecordingsTableProps {
  recordings: RecordingCardData[];
  selected: Set<number>;
  onToggleSelect: (id: number) => void;
  onToggleAll: () => void;
  onRun: (id: number) => void;
  onPause: (id: number) => void;
  onRunWithConfig?: (id: number) => void;
  onReset?: (id: number) => void;
  onDelete?: (id: number) => void;
  onRestore?: (id: number) => void;
  onRename?: (id: number, name: string) => void;
  loadingId?: number | null;
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

const UPLOAD_STATUS_DOT: Record<string, string> = {
  UPLOADED: "bg-green-400",
  UPLOADING: "bg-blue-400 animate-pulse",
  FAILED: "bg-red-400",
  NOT_UPLOADED: "bg-muted",
};

function RowMenu({
  id,
  isSoftDeleted,
  onRunWithConfig,
  onReset,
  onDelete,
  onRestore,
}: {
  id: number;
  isSoftDeleted: boolean;
  onRunWithConfig?: (id: number) => void;
  onReset?: (id: number) => void;
  onDelete?: (id: number) => void;
  onRestore?: (id: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handler(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", handler);
    return () => document.removeEventListener("pointerdown", handler);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition-colors hover:bg-muted hover:text-secondary-foreground",
          open && "border-primary/30 bg-primary/5 text-primary"
        )}
      >
        <MoreHorizontal size={13} />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-xl border border-border bg-card shadow-lg">
          {!isSoftDeleted && onRunWithConfig && (
            <MenuBtn icon={<Settings2 size={12} />} label="Run with config" onClick={() => { setOpen(false); onRunWithConfig(id); }} />
          )}
          {!isSoftDeleted && onReset && (
            <MenuBtn icon={<RotateCcw size={12} />} label="Reset" onClick={() => { setOpen(false); onReset(id); }} />
          )}
          {isSoftDeleted && onRestore && (
            <MenuBtn icon={<ArchiveRestore size={12} />} label="Restore" onClick={() => { setOpen(false); onRestore(id); }} />
          )}
          {!isSoftDeleted && onDelete && (
            <>
              {(onRunWithConfig || onReset) && <div className="my-1 border-t border-border" />}
              <MenuBtn icon={<Trash2 size={12} />} label="Delete" onClick={() => { setOpen(false); onDelete(id); }} danger />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function MenuBtn({ icon, label, onClick, danger }: { icon: React.ReactNode; label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium transition-colors hover:bg-muted",
        danger ? "text-red-500 hover:bg-red-50 dark:bg-red-500/10" : "text-secondary-foreground"
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function InlineNameCell({ id, name, deleted, onRename }: { id: number; name: string; deleted?: boolean; onRename?: (id: number, n: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);
  const inputRef = useRef<HTMLInputElement>(null);

  const commit = useCallback(() => {
    const t = value.trim();
    if (t && t !== name) onRename?.(id, t);
    setEditing(false);
  }, [value, name, id, onRename]);

  const cancel = useCallback(() => { setValue(name); setEditing(false); }, [name]);

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); commit(); }
          if (e.key === "Escape") { e.preventDefault(); cancel(); }
        }}
        className="w-full min-w-0 rounded border border-primary/40 px-1.5 py-0.5 text-xs font-medium text-foreground outline-none ring-1 ring-primary/30"
        autoFocus
      />
    );
  }

  return (
    <div className="group flex min-w-0 items-center gap-1">
      <Link
        href={`/recordings/${id}`}
        title={name}
        className={cn(
          "min-w-0 truncate text-xs font-medium transition-colors",
          deleted ? "text-muted-foreground line-through" : "text-foreground hover:text-primary"
        )}
      >
        {name}
      </Link>
      {onRename && (
        <button
          type="button"
          onClick={() => { setValue(name); setEditing(true); setTimeout(() => inputRef.current?.select(), 0); }}
          className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-primary"
          title="Rename"
        >
          <svg width="10" height="10" viewBox="0 0 11 11" fill="none">
            <path d="M7.5 1.5L9.5 3.5L3.5 9.5H1.5V7.5L7.5 1.5Z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      )}
    </div>
  );
}

export function RecordingsTable({
  recordings,
  selected,
  onToggleSelect,
  onToggleAll,
  onRun,
  onPause,
  onRunWithConfig,
  onReset,
  onDelete,
  onRestore,
  onRename,
  loadingId,
}: RecordingsTableProps) {
  const allSelected = selected.size === recordings.length && recordings.length > 0;

  return (
    <div className="w-full overflow-x-auto rounded-2xl border border-border bg-card">
      <table className="w-full min-w-[800px] border-collapse text-xs">
        <thead>
          <tr className="border-b border-border bg-muted/60">
            <th className="w-10 px-4 py-3 text-left">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={onToggleAll}
                className="rounded accent-primary"
              />
            </th>
            <th className="px-3 py-3 text-left font-semibold text-secondary-foreground">Name</th>
            <th className="w-8 px-3 py-3 text-left font-semibold text-secondary-foreground"></th>
            <th className="w-24 px-3 py-3 text-left font-semibold text-secondary-foreground">Source</th>
            <th className="w-16 px-3 py-3 text-left font-semibold text-secondary-foreground">Duration</th>
            <th className="w-24 px-3 py-3 text-left font-semibold text-secondary-foreground">Date</th>
            <th className="w-32 px-3 py-3 text-left font-semibold text-secondary-foreground">Platforms</th>
            <th className="w-20 px-3 py-3 text-left font-semibold text-secondary-foreground">Actions</th>
          </tr>
        </thead>
        <tbody>
          {recordings.map((r, idx) => {
            const isSoftDeleted = !!r.soft_deleted_at;
            const isLoading = loadingId === r.id;
            const uploadEntries = Object.entries(r.uploads);

            return (
              <tr
                key={r.id}
                className={cn(
                  "border-b border-border transition-colors last:border-0",
                  isSoftDeleted && "opacity-60",
                  selected.has(r.id) ? "bg-primary/5" : idx % 2 === 0 ? "bg-card" : "bg-muted/40",
                  "hover:bg-primary/5"
                )}
              >
                {/* Checkbox */}
                <td className="px-4 py-2.5">
                  <input
                    type="checkbox"
                    checked={selected.has(r.id)}
                    onChange={() => onToggleSelect(r.id)}
                    className="rounded accent-primary"
                  />
                </td>

                {/* Name */}
                <td className="max-w-[200px] px-3 py-2.5">
                  <InlineNameCell id={r.id} name={r.display_name} deleted={isSoftDeleted} onRename={onRename} />
                  {r.template_id != null && (
                    <Link
                      href={`/templates/${r.template_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-0.5 block truncate text-[10px] text-primary/60 hover:text-primary"
                    >
                      {r.template_name ?? `#${r.template_id}`}
                    </Link>
                  )}
                </td>

                {/* Status dot */}
                <td className="px-3 py-2.5">
                  <StatusDot status={r.status} failed={r.failed} stages={r.processing_stages} />
                </td>

                {/* Source */}
                <td className="px-3 py-2.5 text-muted-foreground">{r.source?.type ?? "—"}</td>

                {/* Duration */}
                <td className="px-3 py-2.5 tabular-nums text-muted-foreground">{formatDuration(r.duration)}</td>

                {/* Date */}
                <td className="px-3 py-2.5 text-muted-foreground">{formatDate(r.start_time)}</td>

                {/* Platforms */}
                <td className="px-3 py-2.5">
                  {uploadEntries.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {uploadEntries.map(([platform, info]) => {
                        const dot = <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", UPLOAD_STATUS_DOT[info.status] ?? UPLOAD_STATUS_DOT["NOT_UPLOADED"])} />;
                        const label = PLATFORM_LABELS[platform] ?? platform;
                        if (info.url && info.status === "UPLOADED") {
                          return (
                            <a
                              key={platform}
                              href={info.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-1 text-[10px] font-medium text-primary hover:underline"
                            >
                              {dot}{label}<ExternalLink size={9} className="opacity-60" />
                            </a>
                          );
                        }
                        return (
                          <span key={platform} className="inline-flex items-center gap-1 text-[10px] text-secondary-foreground">
                            {dot}{label}
                          </span>
                        );
                      })}
                    </div>
                  ) : (
                    <span className="text-gray-300">—</span>
                  )}
                </td>

                {/* Actions */}
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-1">
                    {isSoftDeleted ? (
                      onRestore && (
                        <button
                          type="button"
                          onClick={() => onRestore(r.id)}
                          disabled={isLoading}
                          title="Restore"
                          className="flex h-7 w-7 items-center justify-center rounded-lg border border-green-200 text-green-600 hover:bg-green-50 dark:bg-green-500/10 disabled:opacity-50"
                        >
                          <ArchiveRestore size={13} />
                        </button>
                      )
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => onRun(r.id)}
                          disabled={!r.can_run || isLoading}
                          title="Run"
                          className="flex h-7 w-7 items-center justify-center rounded-lg border border-border text-muted-foreground hover:border-primary hover:bg-primary hover:text-white disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
                        >
                          <Play size={11} />
                        </button>
                        <button
                          type="button"
                          onClick={() => onPause(r.id)}
                          disabled={!r.can_pause || isLoading}
                          title="Pause"
                          className="flex h-7 w-7 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
                        >
                          <Pause size={11} />
                        </button>
                      </>
                    )}
                    <RowMenu
                      id={r.id}
                      isSoftDeleted={isSoftDeleted}
                      onRunWithConfig={onRunWithConfig}
                      onReset={onReset}
                      onDelete={onDelete}
                      onRestore={onRestore}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
