"use client";

import { useLocalStorageState } from "@/hooks/use-local-storage-state";

/**
 * Page size for a list, remembered per list in localStorage.
 *
 * Deliberately not part of the URL: unlike a filter, it does not change which
 * rows match, so it belongs with the user's display preferences (the same place
 * the grid/table toggle lives) rather than in a shareable link.
 */
export function usePageSize(storageKey: string, options: number[], fallback: number) {
  const [perPage, setPerPage] = useLocalStorageState(storageKey, fallback, (raw) => {
    const stored = Number(raw);
    return options.includes(stored) ? stored : undefined;
  });
  return { perPage, setPerPage };
}
