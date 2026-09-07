"use client";

import type { AutomationPreviewResult } from "@/lib/automation-run";
import { AffectedRecordingsList } from "@/components/automation/affected-recordings";

export function AutomationPreviewPanel({ preview }: { preview: AutomationPreviewResult }) {
  const recordings = preview.would_process ?? [];
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-sm space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-secondary-foreground">Preview</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Sources were synced. Matching recordings are listed below. Processing was not started.
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-sm">
        <PreviewStat label="Synced" value={preview.synced_count ?? 0} />
        <PreviewStat label="In window" value={preview.recordings_found ?? 0} />
        <PreviewStat label="Would process" value={preview.matched_count ?? recordings.length} />
        <PreviewStat label="Unmatched" value={preview.unmatched_count ?? 0} />
      </dl>
      <AffectedRecordingsList
        recordings={recordings}
        emptyLabel="No recordings would start"
      />
    </div>
  );
}

function PreviewStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-muted/60 px-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="tabular-nums font-medium text-secondary-foreground">{value}</dd>
    </div>
  );
}
