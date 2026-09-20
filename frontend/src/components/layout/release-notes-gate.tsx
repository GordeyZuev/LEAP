"use client";

import { useReleaseNotes } from "@/hooks/use-release-notes";
import { ReleaseNotesModal } from "@/components/layout/release-notes-modal";

/** Mount inside authenticated app shell — shows the latest update once per version. */
export function ReleaseNotesGate() {
  const { open, update, dismiss } = useReleaseNotes();

  if (!update) return null;

  return <ReleaseNotesModal open={open} update={update} onDismiss={dismiss} />;
}
