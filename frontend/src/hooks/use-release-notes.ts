"use client";

import { useCallback, useEffect, useState } from "react";

import { APP_VERSION } from "@/lib/app-version";
import { getReleaseNotesForVersion } from "@/content/release-notes";
import { markReleaseSeen, shouldShowReleaseNotes } from "@/lib/release-notes-storage";

/** Wait for the shell to settle before showing release notes. */
const SHOW_DELAY_MS = 1_500;

export function useReleaseNotes() {
  const content = getReleaseNotesForVersion(APP_VERSION);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!content || !shouldShowReleaseNotes(APP_VERSION)) return;

    const timer = window.setTimeout(() => setOpen(true), SHOW_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [content]);

  const dismiss = useCallback(() => {
    markReleaseSeen(APP_VERSION);
    setOpen(false);
  }, []);

  return { open, version: APP_VERSION, content, dismiss };
}
