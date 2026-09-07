import {
  keepPreviousData,
  QueryClient,
  useQuery,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { listPlaylists } from "@/api/playlists";
import { apiClient } from "@/api/client";
import type { UserMe } from "@/components/settings/types";
import {
  PER_PAGE_AUTOMATION,
  PER_PAGE_CREDENTIALS,
  PER_PAGE_PLAYLISTS,
  PER_PAGE_PRESETS,
  PER_PAGE_SOURCES,
  PER_PAGE_TEMPLATES,
  PER_PAGE_TEMPLATES_OPTIONS,
} from "@/lib/constants";

export const ME_QUERY_KEY = ["me"] as const;

export const STALE_TIME = {
  session: 5 * 60 * 1000,
  catalog: 5 * 60 * 1000,
  recordings: 30_000,
} as const;

export const listQueryOptions = {
  placeholderData: keepPreviousData,
} as const;

export function isInitialLoad(isPending: boolean, data: unknown): boolean {
  return isPending && data === undefined;
}

export async function fetchMe(): Promise<UserMe> {
  const { data } = await apiClient.get<UserMe>("/users/me");
  return data;
}

export function useMe(options?: Pick<UseQueryOptions<UserMe>, "enabled">) {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: fetchMe,
    staleTime: STALE_TIME.session,
    ...options,
  });
}

const catalogPrefetch = {
  staleTime: STALE_TIME.catalog,
} as const;

function readStoredPageSize(storageKey: string, allowed: readonly number[], fallback: number): number {
  if (typeof window === "undefined") return fallback;
  const stored = Number(window.localStorage.getItem(storageKey));
  return allowed.includes(stored) ? stored : fallback;
}

/** Prefetch the default first-page list for a sidebar route (hover/focus). */
export function prefetchNavList(qc: QueryClient, href: string): void {
  switch (href) {
    case "/playlists":
      void qc.prefetchQuery({
        queryKey: ["playlists", ""],
        queryFn: () =>
          listPlaylists({
            page: 1,
            per_page: PER_PAGE_PLAYLISTS,
            sort_by: "updated_at",
            sort_order: "desc",
          }),
        ...catalogPrefetch,
      });
      break;
    case "/templates": {
      const perPage = readStoredPageSize("templates-per-page", PER_PAGE_TEMPLATES_OPTIONS, PER_PAGE_TEMPLATES);
      void qc.prefetchQuery({
        queryKey: ["templates", "", perPage],
        queryFn: async () => {
          const p = new URLSearchParams();
          p.set("sort_by", "created_at");
          p.set("sort_order", "desc");
          p.set("page", "1");
          p.set("per_page", String(perPage));
          const res = await apiClient.get(`/templates?${p.toString()}`);
          return res.data;
        },
        ...catalogPrefetch,
      });
      break;
    }
    case "/presets":
      void qc.prefetchQuery({
        queryKey: ["presets", ""],
        queryFn: async () => {
          const p = new URLSearchParams();
          p.set("sort_by", "created_at");
          p.set("sort_order", "desc");
          p.set("page", "1");
          p.set("per_page", String(PER_PAGE_PRESETS));
          const res = await apiClient.get(`/presets?${p.toString()}`);
          return res.data;
        },
        ...catalogPrefetch,
      });
      break;
    case "/sources":
      void qc.prefetchQuery({
        queryKey: ["sources", ""],
        queryFn: async () => {
          const p = new URLSearchParams();
          p.set("sort_by", "name");
          p.set("sort_order", "asc");
          p.set("page", "1");
          p.set("per_page", String(PER_PAGE_SOURCES));
          const res = await apiClient.get(`/sources?${p.toString()}`);
          return res.data;
        },
        ...catalogPrefetch,
      });
      break;
    case "/credentials":
      void qc.prefetchQuery({
        queryKey: ["credentials-page", ""],
        queryFn: async () => {
          const p = new URLSearchParams();
          p.set("sort_by", "created_at");
          p.set("sort_order", "desc");
          p.set("page", "1");
          p.set("per_page", String(PER_PAGE_CREDENTIALS));
          const res = await apiClient.get(`/credentials?${p.toString()}`);
          return res.data;
        },
        ...catalogPrefetch,
      });
      break;
    case "/automation":
      void qc.prefetchQuery({
        queryKey: ["automation-jobs", ""],
        queryFn: async () => {
          const p = new URLSearchParams();
          p.set("sort_by", "next_run_at");
          p.set("sort_order", "asc");
          p.set("page", "1");
          p.set("per_page", String(PER_PAGE_AUTOMATION));
          const res = await apiClient.get(`/automation/jobs?${p.toString()}`);
          return res.data;
        },
        ...catalogPrefetch,
      });
      break;
    default:
      break;
  }
}
