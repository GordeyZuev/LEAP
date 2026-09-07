"use client";

import Link from "next/link";
import type { AffectedRecording } from "@/lib/automation-run";

export function AffectedRecordingsList({
  recordings,
  emptyLabel,
  missingLabel,
}: {
  recordings: AffectedRecording[] | null | undefined;
  emptyLabel: string;
  missingLabel?: string;
}) {
  if (recordings == null) {
    return <p className="text-sm text-muted-foreground">{missingLabel ?? emptyLabel}</p>;
  }
  if (recordings.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <ul className="divide-y divide-border rounded-xl border border-border">
      {recordings.map((row) => (
        <li key={row.id} className="flex items-start justify-between gap-3 px-3 py-2.5">
          <Link
            href={`/recordings/${row.id}`}
            className="min-w-0 text-sm font-medium text-foreground hover:text-primary"
          >
            <span className="block truncate">{row.name || `Recording ${row.id}`}</span>
          </Link>
          <span className="shrink-0 text-xs text-muted-foreground">{row.template_name}</span>
        </li>
      ))}
    </ul>
  );
}
