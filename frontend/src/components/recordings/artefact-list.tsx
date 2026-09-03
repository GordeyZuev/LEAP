"use client";

import type { ReactNode } from "react";
import {
  AlignLeft,
  ArrowDownToLine,
  FileCode,
  FileDown,
  FileText,
  MessagesSquare,
  Paperclip,
  Video,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Downloadable artifacts for a recording, shared by the authenticated detail
 * page and the public share page. Both used to hand-roll the same row markup
 * and their own label maps, which drifted.
 *
 * A row is a link when the artifact has a direct URL (the public share
 * endpoints) and a button when fetching it needs the authenticated client.
 */

export type ArtefactType =
  | "video_processed"
  | "video_original"
  | "srt"
  | "vtt"
  | "transcript_json"
  | "transcript_txt"
  | "transcript_words"
  | "description_txt"
  | "source_chat"
  | "source_file";

export const ARTEFACT_META: Record<
  ArtefactType,
  { label: string; extension: string; icon: ReactNode; accented?: boolean }
> = {
  // The player above has Processed/Original tabs, so the video rows name their
  // variant explicitly — otherwise "download" is ambiguous about which cut it saves.
  video_processed: { label: "Video – processed", extension: "mp4", icon: <Video size={13} className="shrink-0" /> },
  video_original: { label: "Video – original", extension: "mp4", icon: <Video size={13} className="shrink-0" /> },
  srt: { label: "Subtitles", extension: "srt", icon: <FileText size={13} className="shrink-0" /> },
  vtt: { label: "Subtitles", extension: "vtt", icon: <FileText size={13} className="shrink-0" /> },
  transcript_json: {
    label: "Transcript – full data",
    extension: "json",
    icon: <FileCode size={13} className="shrink-0" />,
    accented: true,
  },
  transcript_txt: {
    label: "Transcript – by segment",
    extension: "txt",
    icon: <FileText size={13} className="shrink-0" />,
    accented: true,
  },
  transcript_words: {
    label: "Transcript – by word",
    extension: "txt",
    icon: <AlignLeft size={13} className="shrink-0" />,
    accented: true,
  },
  description_txt: { label: "Description", extension: "txt", icon: <FileDown size={13} className="shrink-0" /> },
  // Companion files that came from the source, not from the pipeline. Their labels and
  // extensions are per-file, so rows override the defaults below.
  source_chat: { label: "Chat", extension: "json", icon: <MessagesSquare size={13} className="shrink-0" /> },
  source_file: { label: "Attachment", extension: "file", icon: <Paperclip size={13} className="shrink-0" /> },
};

/** Human-readable label for share analytics download breakdown keys. */
export function getShareArtifactLabel(type: string): string {
  const meta = ARTEFACT_META[type as ArtefactType];
  if (!meta) return type;
  if (type === "srt") return `${meta.label} (.srt)`;
  if (type === "vtt") return `${meta.label} (.vtt)`;
  return meta.label;
}

const ROW =
  "flex w-full items-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-medium transition-colors " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";

const ROW_DEFAULT =
  "border-border bg-background text-secondary-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-primary";

// Files worth reaching for first (full transcript exports) get a resting-state
// blue tint instead of only revealing color on hover, so they read as the
// primary action in the list rather than looking identical to every download.
const ROW_ACCENTED =
  "border-primary/30 bg-primary/5 font-semibold text-primary hover:border-primary/50 hover:bg-primary/10";

export interface ArtefactItem {
  type: ArtefactType;
  /** Direct download URL. Mutually exclusive with `onDownload`. */
  href?: string;
  /** Fetch-and-save handler for artifacts behind the authenticated API. */
  onDownload?: () => void;
  /** Overrides for files whose names come from the source rather than the pipeline. */
  label?: string;
  extension?: string;
  /** Needed when several rows share a type, e.g. multiple session materials. */
  key?: string;
}

export function ArtefactList({ items }: { items: ArtefactItem[] }) {
  if (items.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      {items.map((item) => {
        const base = ARTEFACT_META[item.type];
        if (!base) return null;
        const meta = { ...base, label: item.label ?? base.label, extension: item.extension ?? base.extension };
        const rowClass = cn(ROW, meta.accented ? ROW_ACCENTED : ROW_DEFAULT);
        const inner = (
          <>
            {meta.icon}
            <span className="flex-1 text-left">{meta.label}</span>
            <span
              className={cn(
                "shrink-0 text-[10px] font-semibold uppercase",
                meta.accented ? "text-primary/70" : "text-muted-foreground"
              )}
            >
              {meta.extension}
            </span>
            <ArrowDownToLine size={11} className={cn("shrink-0", meta.accented ? "text-primary" : "text-muted-foreground")} />
          </>
        );
        const rowKey = item.key ?? item.type;
        return item.href ? (
          <a key={rowKey} href={item.href} download className={rowClass}>
            {inner}
          </a>
        ) : (
          <button key={rowKey} type="button" onClick={item.onDownload} className={rowClass}>
            {inner}
          </button>
        );
      })}
    </div>
  );
}
