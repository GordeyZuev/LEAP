"use client";

import { useReleaseNotes } from "@/hooks/use-release-notes";
import { ReleaseNotesModal } from "@/components/layout/release-notes-modal";

/** Mount inside authenticated app shell — shows release notes once per version. */
export function ReleaseNotesGate() {
  const { open, version, content, dismiss } = useReleaseNotes();

  if (!content) return null;

  return <ReleaseNotesModal open={open} version={version} content={content} onDismiss={dismiss} />;
}
