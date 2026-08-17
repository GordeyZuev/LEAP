"use client";

import { CheckCircle2, Clock, Loader2, SkipForward, XCircle } from "lucide-react";
import type { ComponentType } from "react";
import { cn } from "@/lib/utils";
import { ProgressBar } from "@/components/ui/progress-bar";

export interface PipelineStage {
  stage_type: string;
  status: string;
  failed: boolean;
  failed_reason?: string | null;
  retry_count?: number;
  started_at?: string | null;
  completed_at?: string | null;
  failed_at?: string | null;
  duration_seconds?: number | null;
}

export const CANONICAL_STAGE_ORDER = [
  "DOWNLOAD",
  "TRIM",
  "TRANSCRIBE",
  "EXTRACT_TOPICS",
  "GENERATE_SUBTITLES",
] as const;

// `failed_at_stage` has been written by several code paths over time, in the
// enum's own casing, in lowercase, and once as a present participle. Every
// spelling has to resolve to the same stage here.
const STAGE_TYPE_ALIASES: Record<string, string> = {
  TRANSCRIPTION: "TRANSCRIBE",
  SUBTITLES: "GENERATE_SUBTITLES",
  DOWNLOADING: "DOWNLOAD",
  TOPICS: "EXTRACT_TOPICS",
  UPLOADING: "UPLOAD",
};

export function normalizeStageType(stageType: string): string {
  return STAGE_TYPE_ALIASES[stageType] ?? stageType;
}

/**
 * Human label for the stage a recording failed at, e.g. `"Transcription"`.
 *
 * Returns null when there is nothing to show, so callers can render the plain
 * "Failed" badge. Unknown values fall back to the raw string rather than
 * disappearing — an unlabelled stage is still better than none.
 */
export function formatFailedStage(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const key = normalizeStageType(raw.toUpperCase());
  return STAGE_LABEL[key] ?? raw;
}

export const STAGE_LABEL: Record<string, string> = {
  DOWNLOAD: "Download",
  TRIM: "Trim",
  TRANSCRIBE: "Transcription",
  EXTRACT_TOPICS: "Topics",
  GENERATE_SUBTITLES: "Subtitles",
  UPLOAD: "Upload",
};

type StageState = "COMPLETED" | "FAILED" | "IN_PROGRESS" | "SKIPPED" | "PENDING";

export function stageState(stage: PipelineStage | undefined): StageState {
  if (!stage) return "PENDING";
  if (stage.failed) return "FAILED";
  const s = stage.status?.toUpperCase();
  return s === "COMPLETED" || s === "FAILED" || s === "IN_PROGRESS" || s === "SKIPPED"
    ? (s as StageState)
    : "PENDING";
}

const STATE_META: Record<
  StageState,
  { icon: ComponentType<{ size?: number; className?: string }>; color: string; label: string }
> = {
  COMPLETED:   { icon: CheckCircle2, color: "text-success-fg",     label: "Completed" },
  FAILED:      { icon: XCircle,      color: "text-danger-fg",      label: "Failed" },
  IN_PROGRESS: { icon: Loader2,      color: "text-primary",        label: "In progress" },
  SKIPPED:     { icon: SkipForward,  color: "text-muted-foreground",        label: "Skipped" },
  PENDING:     { icon: Clock,        color: "text-muted-foreground",        label: "Pending" },
};

function formatStageDuration(stage: PipelineStage): string {
  const secTotal =
    stage.duration_seconds != null
      ? Math.floor(stage.duration_seconds)
      : stage.started_at && (stage.completed_at ?? stage.failed_at)
        ? Math.floor(
            (new Date((stage.completed_at ?? stage.failed_at)!).getTime() -
              new Date(stage.started_at).getTime()) / 1000,
          )
        : NaN;
  if (!Number.isFinite(secTotal) || secTotal < 0) return "";
  const h = Math.floor(secTotal / 3600);
  const m = Math.floor((secTotal % 3600) / 60);
  const s = secTotal % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

const STAGE_TIME_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** Orders raw stages canonically, keeping any unknown ones at the end. */
export function orderStages(stages: PipelineStage[]): PipelineStage[] {
  const known = CANONICAL_STAGE_ORDER.map((t) =>
    stages.find((s) => normalizeStageType(s.stage_type) === t),
  ).filter(Boolean) as PipelineStage[];
  const extra = stages.filter(
    (s) => !(CANONICAL_STAGE_ORDER as readonly string[]).includes(normalizeStageType(s.stage_type)),
  );
  return [...known, ...extra];
}

/** One-line summary, used as the accessible name of the pipeline trigger. */
export function pipelineSummary(stages: PipelineStage[]): string {
  if (!stages.length) return "Pipeline: no stages recorded";
  const failed = stages.find((s) => stageState(s) === "FAILED");
  const done = stages.filter((s) => ["COMPLETED", "SKIPPED"].includes(stageState(s))).length;
  const base = `Pipeline: ${done} of ${stages.length} stages complete`;
  if (failed) {
    const name = STAGE_LABEL[normalizeStageType(failed.stage_type)] ?? failed.stage_type;
    return `${base}, ${name.toLowerCase()} failed`;
  }
  const active = stages.find((s) => stageState(s) === "IN_PROGRESS");
  if (active) {
    const name = STAGE_LABEL[normalizeStageType(active.stage_type)] ?? active.stage_type;
    return `${base}, ${name.toLowerCase()} in progress`;
  }
  return base;
}

// ---------------------------------------------------------------------------
// PipelineStageList — the full audit view
// ---------------------------------------------------------------------------

export function PipelineStageList({
  stages,
  showTimes = true,
  className,
}: {
  stages: PipelineStage[];
  /** Completion timestamps — useful on the detail page, noise in a popover. */
  showTimes?: boolean;
  className?: string;
}) {
  if (!stages.length) {
    return <p className={cn("text-xs text-muted-foreground", className)}>No pipeline data yet.</p>;
  }

  return (
    <ul className={cn("divide-y divide-border", className)}>
      {stages.map((stage) => {
        const state = stageState(stage);
        const meta = STATE_META[state];
        const Icon = meta.icon;
        const name = STAGE_LABEL[normalizeStageType(stage.stage_type)] ?? stage.stage_type;
        const dur = formatStageDuration(stage);
        const retries = stage.retry_count ?? 0;
        // A failed stage never gets completed_at, so without failed_at it showed
        // neither a duration nor a time.
        const endedAt = stage.completed_at ?? stage.failed_at;
        const time = showTimes && endedAt ? STAGE_TIME_FORMATTER.format(new Date(endedAt)) : "";

        return (
          <li key={normalizeStageType(stage.stage_type)} className="py-2 first:pt-0 last:pb-0">
            <div className="flex items-center gap-2">
              <Icon
                size={14}
                aria-hidden="true"
                className={cn("shrink-0", meta.color, state === "IN_PROGRESS" && "animate-spin")}
              />
              <span className="flex-1 truncate text-xs font-medium text-secondary-foreground">{name}</span>
              {retries > 0 && (
                <span className="shrink-0 text-xs tabular-nums text-warning-fg" title={`${retries} retries`}>
                  ×{retries}
                </span>
              )}
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                {dur || meta.label}
              </span>
            </div>

            {state === "IN_PROGRESS" && <ProgressBar variant="indeterminate" className="ms-[22px] mt-1 h-0.5" />}

            {time && <p className="ms-[22px] mt-0.5 text-xs text-muted-foreground">{time}</p>}

            {/* The reason a stage failed is the whole point of this view; it is
                shown in full and stays selectable so it can be copied. */}
            {/* Say so explicitly when no reason was recorded — otherwise a bare
                failed row looks like the UI is withholding one. */}
            {stage.failed && (
              <p
                className={cn(
                  "ms-[22px] mt-1 break-words rounded-lg px-2 py-1 text-xs",
                  stage.failed_reason?.trim()
                    ? "bg-danger-fg/10 text-danger-fg"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {stage.failed_reason?.trim() || "Failed without an error message."}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
