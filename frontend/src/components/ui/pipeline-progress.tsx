"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

export interface PipelineStage {
  stage_type: string;
  status: string;
  failed: boolean;
  failed_reason?: string | null;
  duration_seconds?: number | null;
}

const STAGE_ORDER = ["DOWNLOAD", "TRIM", "TRANSCRIBE", "EXTRACT_TOPICS", "GENERATE_SUBTITLES"] as const;
const STAGE_FULL_LABEL: Record<string, string> = {
  DOWNLOAD: "Download",
  TRIM: "Trim",
  TRANSCRIBE: "Transcription",
  EXTRACT_TOPICS: "Topics",
  GENERATE_SUBTITLES: "Subtitles",
};

function formatDur(sec: number) {
  if (sec < 60) return `${Math.round(sec)}s`;
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
}

interface StageNodeProps {
  stageType: string;
  stage: PipelineStage | undefined;
}

function StageNode({ stageType, stage }: StageNodeProps) {
  const status = stage?.status ?? "PENDING";
  const failed = stage?.failed ?? false;

  const [hovered, setHovered] = useState(false);

  const dotClass = cn(
    "relative flex h-4 w-4 items-center justify-center rounded-full border text-[9px] font-bold transition-colors",
    status === "COMPLETED" && "border-green-500 bg-green-500 text-white",
    status === "IN_PROGRESS" && "border-blue-500 bg-blue-500 text-white animate-pulse",
    status === "FAILED" && "border-red-500 bg-red-500 text-white",
    status === "SKIPPED" && "border-border bg-muted text-muted-foreground",
    status === "PENDING" && "border-border bg-card text-gray-300"
  );

  const tooltip = (
    <div className="absolute bottom-full left-1/2 z-30 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg border border-border bg-card px-2.5 py-1.5 shadow-md text-xs">
      <p className="font-semibold text-foreground">{STAGE_FULL_LABEL[stageType] ?? stageType}</p>
      <p className={cn(
        "text-[10px]",
        status === "COMPLETED" && "text-green-600",
        status === "IN_PROGRESS" && "text-blue-600",
        status === "FAILED" && "text-red-500",
        (status === "SKIPPED" || status === "PENDING") && "text-muted-foreground"
      )}>
        {status === "SKIPPED" ? "Skipped" : status.charAt(0) + status.slice(1).toLowerCase().replace("_", " ")}
      </p>
      {stage?.duration_seconds != null && (
        <p className="text-[10px] text-muted-foreground">{formatDur(stage.duration_seconds)}</p>
      )}
      {failed && stage?.failed_reason && (
        <p className="mt-0.5 max-w-[180px] text-[10px] text-red-500 whitespace-normal">{stage.failed_reason}</p>
      )}
    </div>
  );

  return (
    <div
      className="relative flex flex-col items-center gap-0.5"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {hovered && tooltip}
      <div className={dotClass}>
        {status === "COMPLETED" && <CheckMark />}
        {status === "FAILED" && "✕"}
        {status === "SKIPPED" && "–"}
      </div>
    </div>
  );
}

function CheckMark() {
  return (
    <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
      <path d="M1.5 4L3 5.5L6.5 2" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Connector({ active }: { active: boolean }) {
  return (
    <div className={cn("mb-3 h-px w-3 shrink-0", active ? "bg-green-400" : "bg-muted")} />
  );
}

interface PipelineProgressProps {
  stages: PipelineStage[];
  className?: string;
}

export function PipelineProgress({ stages, className }: PipelineProgressProps) {
  const stageMap = new Map(stages.map((s) => [s.stage_type, s]));

  return (
    <div className={cn("flex items-center", className)}>
      {STAGE_ORDER.map((stageType, i) => (
        <div key={stageType} className="flex items-center">
          <StageNode stageType={stageType} stage={stageMap.get(stageType)} />
          {i < STAGE_ORDER.length - 1 && (
            <Connector active={stageMap.get(stageType)?.status === "COMPLETED"} />
          )}
        </div>
      ))}
    </div>
  );
}
