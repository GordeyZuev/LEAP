import { stripLeadingTimestamp } from "./utils.ts";

/** Catalog Sort by options. `newest`/`oldest` are lecture `start_time`, not date added. */
export const PLAYLIST_VIDEO_SORT = [
  { value: "order", label: "Playlist order" },
  { value: "newest", label: "Newest lecture" },
  { value: "oldest", label: "Oldest lecture" },
  { value: "name", label: "Name A–Z" },
  { value: "duration", label: "Longest first" },
] as const;

export type PlaylistVideoSort = (typeof PLAYLIST_VIDEO_SORT)[number]["value"];

export interface PlaylistCatalogItem {
  title: string;
  duration: number;
  start_time: string;
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

export function sortPlaylistItems<T extends PlaylistCatalogItem>(items: T[], sort: PlaylistVideoSort): T[] {
  if (sort === "order") return items;
  const copy = [...items];
  copy.sort((a, b) => {
    if (sort === "newest") return (b.start_time ?? "").localeCompare(a.start_time ?? "");
    if (sort === "oldest") return (a.start_time ?? "").localeCompare(b.start_time ?? "");
    if (sort === "name") {
      return playlistItemSearchName(a.title).localeCompare(playlistItemSearchName(b.title), undefined, {
        sensitivity: "base",
      });
    }
    return (b.duration ?? 0) - (a.duration ?? 0);
  });
  return copy;
}

export function catalogPlaylistItems<T extends PlaylistCatalogItem>(
  items: T[],
  q: string,
  sort: PlaylistVideoSort,
): T[] {
  return sortPlaylistItems(filterPlaylistItems(items, q), sort);
}
