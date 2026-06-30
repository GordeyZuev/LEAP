"use client";

import { cn } from "@/lib/utils";

export type ProcessingStatus =
  | "PENDING_SOURCE"
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

const STATUS_CONFIG: Record<ProcessingStatus, { label: string; className: string; pulse?: boolean }> = {
  PENDING_SOURCE: { label: "Pending",     className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-300" },
  INITIALIZED:   { label: "Initialized", className: "bg-muted text-muted-foreground" },
  DOWNLOADING:   { label: "Downloading", className: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300", pulse: true },
  DOWNLOADED:    { label: "Downloaded",  className: "bg-muted text-secondary-foreground" },
  PROCESSING:    { label: "Processing",  className: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300", pulse: true },
  PROCESSED:     { label: "Processed",   className: "bg-muted text-secondary-foreground" },
  UPLOADING:     { label: "Uploading",   className: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300", pulse: true },
  UPLOADED:      { label: "Uploaded",    className: "bg-green-100 text-green-600 dark:bg-green-500/15 dark:text-green-300" },
  READY:         { label: "Ready",       className: "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300" },
  SKIPPED:       { label: "Skipped",     className: "bg-muted text-muted-foreground" },
  EXPIRED:       { label: "Expired",     className: "bg-muted text-muted-foreground" },
};

interface StatusBadgeProps {
  status: ProcessingStatus;
  failed: boolean;
  className?: string;
}

export function StatusBadge({ status, failed, className }: StatusBadgeProps) {
  if (failed) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-600 dark:bg-red-500/15 dark:text-red-300", className)}>
        Failed
      </span>
    );
  }
  const cfg = STATUS_CONFIG[status] ?? { label: status, className: "bg-muted text-muted-foreground" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium", cfg.className, className)}>
      {cfg.pulse && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
      {cfg.label}
    </span>
  );
}
