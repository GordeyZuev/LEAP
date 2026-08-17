"use client";

import { useCallback, useState } from "react";

/**
 * Page size for a list, remembered per list in localStorage.
 *
 * Deliberately not part of the URL: unlike a filter, it does not change which
 * rows match, so it belongs with the user's display preferences (the same place
 * the grid/table toggle lives) rather than in a shareable link.
 */
export function usePageSize(storageKey: string, options: number[], fallback: number) {
  const [perPage, setPerPageState] = useState<number>(() => {
    if (typeof window === "undefined") return fallback;
    const stored = Number(localStorage.getItem(storageKey));
    return options.includes(stored) ? stored : fallback;
  });

  const setPerPage = useCallback(
    (next: number) => {
      setPerPageState(next);
      localStorage.setItem(storageKey, String(next));
    },
    [storageKey],
  );

  return { perPage, setPerPage };
}
