import { stripLeadingTimestamp } from "./utils.ts";

/** Catalog Sort by options. `newest`/`oldest` are lecture `start_time`, not date added. */
export const PLAYLIST_VIDEO_SORT = [
  { value: "order", label: "Author order" },
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "name", label: "Name A–Z" },
  { value: "duration", label: "Longest first" },
  { value: "views", label: "Most viewed" },
] as const;

export type PlaylistVideoSort = (typeof PLAYLIST_VIDEO_SORT)[number]["value"];

export interface PlaylistCatalogItem {
  title: string;
  duration: number;
  start_time: string;
  view_count?: number;
}

export function visiblePlaylistFolderItems<T extends { group_id: number | null }>(
  items: T[],
  groupId: number | null,
  hasGroups: boolean,
  query: string,
): T[] {
  if (groupId !== null) return items.filter((item) => item.group_id === groupId);
  if (hasGroups && !query.trim()) return items.filter((item) => item.group_id === null);
  return items;
}

export function parsePlaylistVideoSort(raw: string | null): PlaylistVideoSort {
  return PLAYLIST_VIDEO_SORT.some((o) => o.value === raw) ? (raw as PlaylistVideoSort) : "order";
}

export function playlistItemSearchName(title: string): string {
  return stripLeadingTimestamp(title);
}

export function playlistItemMatchesQuery(title: string, q: string): boolean {
  if (!q.trim()) return true;
  return playlistItemSearchName(title).toLowerCase().includes(q.trim().toLowerCase());
}

export function filterPlaylistItems<T extends PlaylistCatalogItem>(items: T[], q: string): T[] {
  if (!q.trim()) return items;
  return items.filter((item) => playlistItemMatchesQuery(item.title, q));
}

/** Name and date sorts match the saved order in `backend/api/helpers/catalog_sort.py`. */
export function sortPlaylistItems<T extends PlaylistCatalogItem>(items: T[], sort: PlaylistVideoSort): T[] {
  if (sort === "order") return items;
  return [...items].sort((a, b) => {
    if (sort === "newest") return (b.start_time ?? "").localeCompare(a.start_time ?? "");
    if (sort === "oldest") return (a.start_time ?? "").localeCompare(b.start_time ?? "");
    if (sort === "name") {
      return playlistItemSearchName(a.title).localeCompare(playlistItemSearchName(b.title), undefined, {
        numeric: true,
        sensitivity: "base",
      });
    }
    if (sort === "views") return (b.view_count ?? 0) - (a.view_count ?? 0);
    return (b.duration ?? 0) - (a.duration ?? 0);
  });
}

export function catalogPlaylistItems<T extends PlaylistCatalogItem>(
  items: T[],
  q: string,
  sort: PlaylistVideoSort,
): T[] {
  return sortPlaylistItems(filterPlaylistItems(items, q), sort);
}
