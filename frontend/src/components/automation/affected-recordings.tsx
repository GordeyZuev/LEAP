"use client";

import { useState } from "react";
import Link from "next/link";
import type { AffectedRecording } from "@/lib/automation-run";
import { ActionButton } from "@/components/ui/action-button";
import { Modal } from "@/components/ui/modal";

const PREVIEW_LIMIT = 5;

export function AffectedRecordingsList({
  recordings,
  emptyLabel,
  missingLabel,
}: {
  recordings: AffectedRecording[] | null | undefined;
  emptyLabel: string;
  missingLabel?: string;
}) {
  const [allOpen, setAllOpen] = useState(false);

  if (recordings == null) {
    return <p className="text-sm text-muted-foreground">{missingLabel ?? emptyLabel}</p>;
  }
  if (recordings.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyLabel}</p>;
  }

  const preview = recordings.slice(0, PREVIEW_LIMIT);
  const extra = recordings.length - preview.length;

  return (
    <div className="space-y-2">
      <RecordingRows recordings={preview} />
      {extra > 0 && (
        <div className="flex justify-end">
          <ActionButton variant="secondary" onClick={() => setAllOpen(true)}>
            Show all {recordings.length}
          </ActionButton>
        </div>
      )}
      <Modal
        open={allOpen}
        onClose={() => setAllOpen(false)}
        labelledBy="affected-all-title"
        panelClassName="max-w-3xl"
      >
        <div className="p-6 space-y-4">
          <h2 id="affected-all-title" className="text-base font-semibold text-foreground">
            Recordings ({recordings.length})
          </h2>
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Recording</th>
                  <th className="px-3 py-2 font-medium">Template</th>
                </tr>
              </thead>
              <tbody>
                {recordings.map((row) => (
                  <tr key={row.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2">
                      <Link href={`/recordings/${row.id}`} className="font-medium text-foreground hover:text-primary">
                        {row.name || `Recording ${row.id}`}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{row.template_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end">
            <ActionButton variant="secondary" onClick={() => setAllOpen(false)}>
              Close
            </ActionButton>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function RecordingRows({ recordings }: { recordings: AffectedRecording[] }) {
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
