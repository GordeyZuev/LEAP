"use client";

import type { AutomationPreviewResult } from "@/lib/automation-run";
import { AffectedRecordingsList } from "@/components/automation/affected-recordings";
import { ProgressBar } from "@/components/ui/progress-bar";
import { CARD_SHELL } from "@/components/ui/section-card";
import { cn } from "@/lib/utils";

export function AutomationPreviewPanel({
  preview,
  pending,
  statusLabel,
  progress,
}: {
  preview: AutomationPreviewResult | null;
  pending?: boolean;
  statusLabel?: string;
  progress?: number;
}) {
  return (
    <div className={cn(CARD_SHELL, "p-5 space-y-3")}>
      <div>
        <h2 className="text-sm font-semibold text-secondary-foreground">Preview</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Processing is not started. Refresh sources only if you turned that on in Matching.
        </p>
      </div>
      {pending && (
        <div className="space-y-2" aria-live="polite">
          <p className="text-sm text-secondary-foreground">{statusLabel || "Matching recordings…"}</p>
          {progress != null && progress > 0 ? (
            <ProgressBar variant="determinate" value={progress} />
          ) : (
            <ProgressBar variant="indeterminate" />
          )}
        </div>
      )}
      {preview && (
        <>
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-sm">
            <PreviewStat label="Synced" value={preview.synced_count ?? 0} />
            <PreviewStat label="In window" value={preview.recordings_found ?? 0} />
            <PreviewStat label="Would process" value={preview.matched_count ?? (preview.would_process ?? []).length} />
            <PreviewStat label="Unmatched" value={preview.unmatched_count ?? 0} />
          </dl>
          <AffectedRecordingsList
            recordings={preview.would_process ?? []}
            emptyLabel="No recordings would start"
          />
        </>
      )}
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
