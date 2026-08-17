"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useDebounce } from "@/hooks/use-debounce";
import { DEBOUNCE_SEARCH } from "@/lib/constants";

interface UrlListStateOptions {
  /** Sort field used when the URL says nothing — kept out of the URL. */
  defaultSortBy: string;
  /** Sort direction used when the URL says nothing. */
  defaultSortOrder?: "asc" | "desc";
  /** Sort fields the API accepts; anything else falls back to the default. */
  allowedSortFields: readonly string[];
}

/**
 * URL-backed state for a filtered, sorted, paginated list.
 *
 * Every list page needs the same things: a debounced search box that writes to
 * the query string, a sort field/direction, a page number that resets whenever
 * the result set changes, and a way to clear it all. Keeping that state in the
 * URL is what makes a filtered view shareable and survive a reload.
 *
 * Filters beyond search/sort/page differ per page, so they are handled through
 * the generic `getParam` / `setParam` pair rather than being modelled here.
 */
export function useUrlListState({
  defaultSortBy,
  defaultSortOrder = "desc",
  allowedSortFields,
}: UrlListStateOptions) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlKey = searchParams.toString();

  const urlSearch = searchParams.get("search") ?? "";
  const rawSortBy = searchParams.get("sort_by") ?? defaultSortBy;
  const sortBy = allowedSortFields.includes(rawSortBy) ? rawSortBy : defaultSortBy;
  const sortOrderParam = searchParams.get("sort_order");
  const sortOrder: "asc" | "desc" =
    sortOrderParam === "asc" || sortOrderParam === "desc" ? sortOrderParam : defaultSortOrder;
  const page = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);

  // The search box is local so typing stays responsive; the URL catches up.
  const [searchInput, setSearchInput] = useState(urlSearch);
  const debouncedSearch = useDebounce(searchInput, DEBOUNCE_SEARCH);

  // Re-sync the box when the URL changes from the outside (back/forward, reset).
  const [prevUrlKey, setPrevUrlKey] = useState(urlKey);
  if (urlKey !== prevUrlKey) {
    setPrevUrlKey(urlKey);
    setSearchInput(searchParams.get("search") ?? "");
  }

  const commit = useCallback(
    (mutate: (p: URLSearchParams) => void, { keepPage = false } = {}) => {
      const p = new URLSearchParams(window.location.search);
      mutate(p);
      // Any change to the result set invalidates the current page number.
      if (!keepPage) p.delete("page");
      router.replace(`?${p.toString()}`);
    },
    [router],
  );

  // Debounced search → URL. Guarded so it does not re-apply its own write.
  const lastAppliedSearch = useRef(urlSearch);
  useEffect(() => {
    const trimmed = debouncedSearch.trim();
    if (trimmed === lastAppliedSearch.current) return;
    lastAppliedSearch.current = trimmed;
    commit((p) => {
      if (trimmed) p.set("search", trimmed);
      else p.delete("search");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const setParam = useCallback(
    (key: string, value: string | null) => {
      commit((p) => {
        if (value === null || value === "") p.delete(key);
        else p.set(key, value);
      });
    },
    [commit],
  );

  const setMultiParam = useCallback(
    (key: string, values: (string | number)[]) => {
      commit((p) => {
        p.delete(key);
        values.forEach((v) => p.append(key, String(v)));
      });
    },
    [commit],
  );

  const setPage = useCallback(
    (next: number) => {
      commit(
        (p) => {
          if (next <= 1) p.delete("page");
          else p.set("page", String(next));
        },
        { keepPage: true },
      );
    },
    [commit],
  );

  /** Same field flips direction; a new field starts at the default direction. */
  const setSort = useCallback(
    (field: string) => {
      commit((p) => {
        const nextOrder =
          field === sortBy ? (sortOrder === "desc" ? "asc" : "desc") : defaultSortOrder;
        if (field === defaultSortBy) p.delete("sort_by");
        else p.set("sort_by", field);
        if (nextOrder === defaultSortOrder) p.delete("sort_order");
        else p.set("sort_order", nextOrder);
      });
    },
    [commit, sortBy, sortOrder, defaultSortBy, defaultSortOrder],
  );

  const toggleSortOrder = useCallback(() => {
    commit((p) => {
      const next = sortOrder === "desc" ? "asc" : "desc";
      if (next === defaultSortOrder) p.delete("sort_order");
      else p.set("sort_order", next);
    });
  }, [commit, sortOrder, defaultSortOrder]);

  const resetAll = useCallback(() => {
    setSearchInput("");
    lastAppliedSearch.current = "";
    router.replace("?");
  }, [router]);

  const getParam = useCallback((key: string) => searchParams.get(key), [searchParams]);
  const getAllParams = useCallback((key: string) => searchParams.getAll(key), [searchParams]);

  /** True when anything narrowing the result set is set. Sort is excluded on
   *  purpose — it reorders rows but never changes which rows match. */
  const hasActiveFilters = useMemo(() => {
    const p = new URLSearchParams(urlKey);
    p.delete("sort_by");
    p.delete("sort_order");
    p.delete("page");
    return Array.from(p.keys()).length > 0;
  }, [urlKey]);

  const hasNonDefaultSort = sortBy !== defaultSortBy || sortOrder !== defaultSortOrder;

  return {
    urlKey,
    search: urlSearch,
    searchInput,
    setSearchInput,
    sortBy,
    sortOrder,
    setSort,
    toggleSortOrder,
    page,
    setPage,
    getParam,
    getAllParams,
    setParam,
    setMultiParam,
    resetAll,
    hasActiveFilters,
    hasNonDefaultSort,
  };
}
