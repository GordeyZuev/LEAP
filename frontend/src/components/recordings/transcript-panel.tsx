"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { cn, scrollIntoViewWithin } from "@/lib/utils";

/**
 * A readable, seekable transcript built from the recording's WebVTT track.
 *
 * The VTT is already fetched to attach subtitles to the player, so this reuses
 * that blob rather than adding an endpoint: no new API surface, and the reader
 * gets the transcript the share page previously offered only as a download.
 */

export interface TranscriptCue {
  start: number;
  end: number;
  text: string;
}

function parseTimestamp(value: string): number | null {
  // hh:mm:ss.mmm or mm:ss.mmm
  const m = value.trim().match(/^(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})$/);
  if (!m) return null;
  const [, h, mm, ss, ms] = m;
  return Number(h ?? 0) * 3600 + Number(mm) * 60 + Number(ss) + Number(ms.padEnd(3, "0")) / 1000;
}

/** Parse WebVTT into cues, ignoring NOTE/STYLE/REGION blocks and cue settings. */
export function parseVtt(source: string): TranscriptCue[] {
  const cues: TranscriptCue[] = [];
  const blocks = source.replace(/\r\n?/g, "\n").split(/\n{2,}/);

  for (const block of blocks) {
    const lines = block.split("\n").filter((l) => l.trim() !== "");
    if (lines.length === 0) continue;
    // NOTE bodies are free text and may themselves contain "-->", so these
    // blocks have to be dropped outright. The WEBVTT header needs no such
    // rule: a header-only block has no arrow and falls out below, while a
    // file whose first cue follows the header with no blank line — which
    // does occur — would lose that cue if the whole block were skipped.
    if (/^(NOTE|STYLE|REGION)\b/.test(lines[0])) continue;

    const arrowIdx = lines.findIndex((l) => l.includes("-->"));
    if (arrowIdx === -1) continue;

    const [rawStart, rawRest] = lines[arrowIdx].split("-->");
    const start = parseTimestamp(rawStart);
    // Cue settings (align, line, position) trail the end timestamp.
    const end = parseTimestamp((rawRest ?? "").trim().split(/\s+/)[0] ?? "");
    if (start === null || end === null) continue;

    const text = lines
      .slice(arrowIdx + 1)
      .join(" ")
      .replace(/<[^>]+>/g, "")
      .trim();
    if (text) cues.push({ start, end, text });
  }

  return cues;
}

function formatTimecode(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function TranscriptPanel({
  cues,
  activeIdx,
  onSeek,
}: {
  cues: TranscriptCue[];
  /** Index of the cue playing now, or -1. Resolved by the owner so playback
      re-renders this tree only when the line actually changes, not on every
      `timeupdate` tick. */
  activeIdx: number;
  onSeek: (time: number) => void;
}) {
  const [query, setQuery] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return cues.map((cue, i) => ({ cue, i }));
    return cues.map((cue, i) => ({ cue, i })).filter(({ cue }) => cue.text.toLowerCase().includes(q));
  }, [cues, query]);

  // Follow playback inside the list only. Two things this must not do: scroll
  // the page (`scrollIntoView` would, dragging the reader back here every few
  // seconds), and move the list while someone is reading search results.
  useEffect(() => {
    if (query.trim()) return;
    scrollIntoViewWithin(listRef.current, activeRef.current);
  }, [activeIdx, query]);

  if (cues.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          aria-label="Search transcript"
          placeholder="Search transcript…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-xl border border-input bg-card py-2 pl-8 pr-8 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
        />
        {query && (
          <button
            type="button"
            onClick={() => setQuery("")}
            aria-label="Clear transcript search"
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {query.trim() && (
        <p role="status" className="text-xs text-muted-foreground">
          {filtered.length === 0
            ? `No lines match “${query.trim()}”.`
            : `${filtered.length} of ${cues.length} lines match “${query.trim()}”.`}
        </p>
      )}

      <div ref={listRef} className="max-h-[28rem] overflow-y-auto">
        {filtered.map(({ cue, i }) => {
          const isActive = i === activeIdx && !query.trim();
          return (
            <button
              key={i}
              ref={isActive ? activeRef : undefined}
              type="button"
              onClick={() => onSeek(cue.start)}
              className={cn(
                "group flex w-full items-start gap-3 rounded-lg px-2 py-1.5 text-left transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                isActive ? "bg-primary/6" : "hover:bg-muted/30"
              )}
            >
              <span
                className={cn(
                  "w-11 shrink-0 pt-0.5 font-mono text-xs tabular-nums transition-colors group-hover:text-primary",
                  isActive ? "font-semibold text-primary" : "text-muted-foreground"
                )}
              >
                {formatTimecode(cue.start)}
              </span>
              <span
                className={cn(
                  "min-w-0 flex-1 text-sm leading-relaxed",
                  isActive ? "font-medium text-foreground" : "text-secondary-foreground"
                )}
              >
                {cue.text}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
