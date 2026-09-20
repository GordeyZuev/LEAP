"use client";

import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchLatestProductUpdate } from "@/api/product-updates";
import { markReleaseSeen, shouldShowReleaseNotes } from "@/lib/release-notes-storage";

/** Wait for the shell to settle before showing release notes. */
const SHOW_DELAY_MS = 1_500;

export function useReleaseNotes() {
  const { data: update } = useQuery({
    queryKey: ["product-updates", "latest"],
    queryFn: fetchLatestProductUpdate,
    staleTime: 5 * 60_000,
  });
  const version = update?.version ?? update?.id ?? "";
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!version || !shouldShowReleaseNotes(version)) return;

    const timer = window.setTimeout(() => setOpen(true), SHOW_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [version]);

  const dismiss = useCallback(() => {
    if (version) markReleaseSeen(version);
    setOpen(false);
  }, [version]);

  return { open, update, version, dismiss };
}
