"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { ExternalLink, MoreHorizontal, Pause, Play, RotateCcw, Settings2, Trash2, ArchiveRestore } from "lucide-react";
import { cn, formatDate, formatDuration, stripLeadingTimestamp } from "@/lib/utils";
import { SortableTh } from "@/components/ui/sortable-th";
import { RecordingPoster, RECORDING_TABLE_POSTER } from "@/components/recordings/recording-poster";
import { TABLE_BODY, TABLE_CARD, TABLE_HEAD_CELL, TABLE_ROW, TABLE_ROW_CORNERS } from "@/lib/table-classes";
import { type RecordingCardData } from "./recording-card";
import { PipelineStatusButton } from "@/components/recordings/pipeline-popover";
import { formatFailedStage } from "@/components/recordings/pipeline-stages";

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
  /** Current sort, shared with the toolbar's sort control (same URL params). */
  sortBy?: string;
  sortOrder?: "asc" | "desc";
  /** Sorting a column: same field toggles direction, a new field starts at desc. */
  onSort?: (field: string) => void;
}

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  vk: "VK",
  yandex_disk: "YaDisk",
};

const UPLOAD_STATUS_DOT: Record<string, string> = {
  UPLOADED: "bg-success-fg",
  UPLOADING: "bg-primary animate-pulse",
  FAILED: "bg-danger-fg",
  NOT_UPLOADED: "bg-transparent ring-1 ring-inset ring-input",
};

/** Upload state in words — the dot alone carries it by colour otherwise. */
const UPLOAD_STATE_LABEL: Record<string, string> = {
  UPLOADED: "published",
  UPLOADING: "uploading",
  FAILED: "upload failed",
  NOT_UPLOADED: "not uploaded",
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
        aria-label="More actions"
        aria-expanded={open}
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition-colors hover:bg-muted hover:text-secondary-foreground",
          open && "border-primary/30 bg-primary/5 text-primary"
        )}
      >
        <MoreHorizontal size={13} />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-xl border border-border bg-card shadow-lg animate-dropdown-in">
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
        danger ? "text-danger-fg hover:bg-danger-fg/10" : "text-secondary-foreground"
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
        // The full name stays reachable on hover; the date prefix is dropped
        // only from the visible label, where the Date column already shows it.
        title={name}
        className={cn(
          "min-w-0 truncate text-xs font-medium transition-colors",
          deleted ? "text-muted-foreground line-through" : "text-foreground hover:text-primary"
        )}
      >
        {stripLeadingTimestamp(name)}
      </Link>
      {onRename && (
        <button
          type="button"
          onClick={() => { setValue(name); setEditing(true); setTimeout(() => inputRef.current?.select(), 0); }}
          className="shrink-0 opacity-0 transition-opacity text-muted-foreground hover:text-primary group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          title="Rename"
          aria-label={`Rename ${name}`}
        >
          <svg width="10" height="10" viewBox="0 0 11 11" fill="none" aria-hidden="true" focusable="false">
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
  sortBy,
  sortOrder,
  onSort,
}: RecordingsTableProps) {
  const allSelected = selected.size === recordings.length && recordings.length > 0;
  const sortProps = { sortBy, sortOrder, onSort };

  // `overflow-x-auto` makes the wrapper a scroll container on BOTH axes, which
  // stops the sticky header from anchoring to the page. Above `xl` the table
  // fits without horizontal scrolling, so the container is dropped and the
  // header can stick; below that, horizontal scrolling wins.
  return (
    <div className={TABLE_CARD}>
      <table className="w-full min-w-[800px] border-collapse text-xs">
        <thead>
          <tr className="border-b border-border">
            <th className="sticky top-0 z-10 w-10 rounded-tl-2xl bg-muted px-4 py-3 text-left">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={onToggleAll}
                aria-label="Select all recordings on this page"
                className="rounded accent-primary"
              />
            </th>
            {/* Decorative column: not sortable, and an empty <th> would leave
                the column unnamed for screen readers. */}
            <th
              scope="col"
              className={cn(TABLE_HEAD_CELL, "sticky top-0 z-10 hidden w-20 bg-muted px-3 py-3 sm:table-cell")}
            >
              <span className="sr-only">Preview</span>
            </th>
            <SortableTh sticky className="px-3 py-3" label="Name" field="display_name" {...sortProps} />
            <SortableTh sticky className="px-3 py-3 w-24" label="Status" field="status" {...sortProps} />
            <SortableTh sticky className="px-3 py-3 w-24" label="Source" />
            <SortableTh sticky className="px-3 py-3 w-16" label="Duration" />
            <SortableTh sticky className="px-3 py-3 w-28" label="Date" field="start_time" {...sortProps} />
            <SortableTh sticky className="px-3 py-3 w-32" label="Platforms" />
            <SortableTh sticky className="px-3 py-3 w-20" label="Actions" />
          </tr>
        </thead>
        <tbody className={TABLE_BODY}>
          {recordings.map((r) => {
            const isSoftDeleted = !!r.soft_deleted_at;
            const isLoading = loadingId === r.id;
            const uploadEntries = Object.entries(r.uploads);
            const isSelected = selected.has(r.id);

            return (
              <tr
                key={r.id}
                className={cn(
                  // Hover feedback is suppressed on a selected row so the
                  // selection tint stays readable.
                  isSelected ? cn("bg-primary/5 transition-colors", TABLE_ROW_CORNERS) : TABLE_ROW,
                  isSoftDeleted && "opacity-60",
                )}
              >
                {/* Checkbox */}
                <td className="px-4 py-2.5">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleSelect(r.id)}
                    aria-label={`Select ${r.display_name}`}
                    className="rounded accent-primary"
                  />
                </td>

                {/* Name */}
                <td className="hidden px-3 py-2.5 sm:table-cell">
                  <RecordingPoster
                    recordingId={r.id}
                    posterUrl={r.poster_url}
                    posterFallbackUrl={r.poster_fallback_url}
                    duration={r.duration}
                    className={RECORDING_TABLE_POSTER}
                  />
                </td>
                <td className="max-w-[200px] px-3 py-2.5">
                  <InlineNameCell id={r.id} name={r.display_name} deleted={isSoftDeleted} onRename={onRename} />
                  {r.template_id != null && (
                    <Link
                      href={`/templates/${r.template_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-0.5 block truncate text-xs text-primary/70 hover:text-primary"
                    >
                      {r.template_name ?? `#${r.template_id}`}
                    </Link>
                  )}
                </td>

                {/* Status dot */}
                <td className="px-3 py-2.5">
                  <PipelineStatusButton status={r.status} failed={r.failed} failedStage={formatFailedStage(r.failed_at_stage)} stages={r.processing_stages} />
                </td>

                {/* Source */}
                <td className="px-3 py-2.5 text-muted-foreground">{r.source?.type ?? "—"}</td>

                {/* Duration */}
                <td className="px-3 py-2.5 tabular-nums text-muted-foreground">{formatDuration(r.duration) ?? "—"}</td>

                {/* Date */}
                <td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground">{formatDate(r.start_time)}</td>

                {/* Platforms */}
                <td className="px-3 py-2.5">
                  {uploadEntries.length > 0 || r.share_token ? (
                    <div className="flex flex-wrap gap-1.5">
                      {r.share_token && (
                        <a
                          href={`/share/${r.share_token}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                        >
                          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-success-fg">
                            <span className="sr-only">active</span>
                          </span>
                          LEAP
                          <ExternalLink size={9} className="opacity-60" />
                        </a>
                      )}
                      {uploadEntries.map(([platform, info]) => {
                        const dot = (
                          <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", UPLOAD_STATUS_DOT[info.status] ?? UPLOAD_STATUS_DOT["NOT_UPLOADED"])}>
                            <span className="sr-only">{UPLOAD_STATE_LABEL[info.status] ?? "unknown state"}</span>
                          </span>
                        );
                        const label = PLATFORM_LABELS[platform] ?? platform;
                        if (info.url && info.status === "UPLOADED") {
                          return (
                            <a
                              key={platform}
                              href={info.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                            >
                              {dot}{label}<ExternalLink size={9} className="opacity-60" />
                            </a>
                          );
                        }
                        return (
                          <span key={platform} className="inline-flex items-center gap-1 text-xs text-secondary-foreground">
                            {dot}{label}
                          </span>
                        );
                      })}
                    </div>
                  ) : (
                    <span className="text-muted-foreground">—</span>
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
                          aria-label={`Restore ${r.display_name}`}
                          className="flex h-7 w-7 items-center justify-center rounded-lg border border-success-fg/50 text-success-fg hover:bg-success-fg/10 disabled:opacity-50"
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
                          aria-label={`Run ${r.display_name}`}
                          className="flex h-7 w-7 items-center justify-center rounded-lg border border-border text-muted-foreground hover:border-primary hover:bg-primary hover:text-white disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
                        >
                          <Play size={11} />
                        </button>
                        {r.can_pause && (
                          <button
                            type="button"
                            onClick={() => onPause(r.id)}
                            disabled={isLoading}
                            title="Pause"
                            aria-label={`Pause ${r.display_name}`}
                            className="flex h-7 w-7 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            <Pause size={11} />
                          </button>
                        )}
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
