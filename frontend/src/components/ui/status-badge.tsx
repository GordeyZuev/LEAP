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
  PENDING_SOURCE: { label: "Pending",     className: "bg-yellow-100 text-yellow-700" },
  INITIALIZED:   { label: "Initialized", className: "bg-gray-100 text-gray-500" },
  DOWNLOADING:   { label: "Downloading", className: "bg-blue-100 text-blue-700", pulse: true },
  DOWNLOADED:    { label: "Downloaded",  className: "bg-gray-100 text-gray-600" },
  PROCESSING:    { label: "Processing",  className: "bg-blue-100 text-blue-700", pulse: true },
  PROCESSED:     { label: "Processed",   className: "bg-gray-100 text-gray-600" },
  UPLOADING:     { label: "Uploading",   className: "bg-blue-100 text-blue-700", pulse: true },
  UPLOADED:      { label: "Uploaded",    className: "bg-green-100 text-green-600" },
  READY:         { label: "Ready",       className: "bg-green-100 text-green-700" },
  SKIPPED:       { label: "Skipped",     className: "bg-gray-100 text-gray-400" },
  EXPIRED:       { label: "Expired",     className: "bg-gray-100 text-gray-400" },
};

interface StatusBadgeProps {
  status: ProcessingStatus;
  failed: boolean;
  className?: string;
}

export function StatusBadge({ status, failed, className }: StatusBadgeProps) {
  if (failed) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-600", className)}>
        Failed
      </span>
    );
  }
  const cfg = STATUS_CONFIG[status] ?? { label: status, className: "bg-gray-100 text-gray-500" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium", cfg.className, className)}>
      {cfg.pulse && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
      {cfg.label}
    </span>
  );
}
