"use client";

import { cn } from "@/lib/utils";

export type ProcessingStatus =
  | "PENDING_SOURCE"
  | "PENDING_CONVERSION"
  | "INITIALIZED"
  | "DOWNLOADING"
  | "DOWNLOADED"
  | "PROCESSING"
  | "PROCESSED"
  | "UPLOADING"
  | "UPLOADED"
  | "READY"
  | "SKIPPED"
  | "EXPIRED";

export const PROCESSING_STATUS_LABEL: Record<ProcessingStatus, string> = {
  PENDING_SOURCE: "Pending",
  PENDING_CONVERSION: "Converting",
  INITIALIZED: "Initialized",
  DOWNLOADING: "Downloading",
  DOWNLOADED: "Downloaded",
  PROCESSING: "Processing",
  PROCESSED: "Processed",
  UPLOADING: "Uploading",
  UPLOADED: "Uploaded",
  READY: "Ready",
  SKIPPED: "Skipped",
  EXPIRED: "Expired",
};

const STATUS_CONFIG: Record<ProcessingStatus, { label: string; className: string; pulse?: boolean }> = {
  PENDING_SOURCE: { label: PROCESSING_STATUS_LABEL.PENDING_SOURCE, className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-300" },
  PENDING_CONVERSION: { label: PROCESSING_STATUS_LABEL.PENDING_CONVERSION, className: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200", pulse: true },
  INITIALIZED:   { label: PROCESSING_STATUS_LABEL.INITIALIZED, className: "bg-muted text-muted-foreground" },
  DOWNLOADING:   { label: PROCESSING_STATUS_LABEL.DOWNLOADING, className: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300", pulse: true },
  DOWNLOADED:    { label: PROCESSING_STATUS_LABEL.DOWNLOADED,  className: "bg-muted text-secondary-foreground" },
  PROCESSING:    { label: PROCESSING_STATUS_LABEL.PROCESSING,  className: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300", pulse: true },
  PROCESSED:     { label: PROCESSING_STATUS_LABEL.PROCESSED,   className: "bg-muted text-secondary-foreground" },
  UPLOADING:     { label: PROCESSING_STATUS_LABEL.UPLOADING,  className: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300", pulse: true },
  UPLOADED:      { label: PROCESSING_STATUS_LABEL.UPLOADED,    className: "bg-green-100 text-green-600 dark:bg-green-500/15 dark:text-green-300" },
  READY:         { label: PROCESSING_STATUS_LABEL.READY,       className: "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300" },
  SKIPPED:       { label: PROCESSING_STATUS_LABEL.SKIPPED,     className: "bg-muted text-muted-foreground" },
  EXPIRED:       { label: PROCESSING_STATUS_LABEL.EXPIRED,     className: "bg-muted text-muted-foreground" },
};

interface StatusBadgeProps {
  status: ProcessingStatus;
  failed: boolean;
  /**
   * Human label of the stage that broke, e.g. "Download". Rendered inside the
   * badge so the failure stays one element: it used to sit on its own red line
   * underneath, repeating the word "Failed" in a second, mismatched red.
   * Resolve it with `formatFailedStage` — this primitive stays presentational.
   */
  failedStage?: string | null;
  /** `control` matches h-7 action buttons (e.g. recording card footer). */
  size?: "default" | "control";
  className?: string;
}

const BADGE_SIZE: Record<NonNullable<StatusBadgeProps["size"]>, string> = {
  default: "px-2.5 py-1",
  control: "h-7 px-2.5 py-0",
};

export function StatusBadge({ status, failed, failedStage, size = "default", className }: StatusBadgeProps) {
  const sizeCls = BADGE_SIZE[size];
  if (failed) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-danger-fg/10 text-xs font-medium text-danger-fg", sizeCls, className)}>
        {failedStage ? `Failed · ${failedStage}` : "Failed"}
      </span>
    );
  }
  const cfg = STATUS_CONFIG[status] ?? { label: status, className: "bg-muted text-muted-foreground" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full text-xs font-medium", sizeCls, cfg.className, className)}>
      {cfg.pulse && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
      {cfg.label}
    </span>
  );
}
