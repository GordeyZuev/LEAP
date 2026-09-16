import { stripLeadingTimestamp } from "./utils.ts";

/** Catalog Sort by options. Video newest/oldest are lecture `start_time`, not date added. */
export const CHANNEL_VIDEO_SORT = [
  { value: "order", label: "Channel order" },
  { value: "newest", label: "Newest lecture" },
  { value: "oldest", label: "Oldest lecture" },
  { value: "name", label: "Name A–Z" },
  { value: "duration", label: "Longest first" },
] as const;

export const CHANNEL_PLAYLIST_SORT = [
  { value: "order", label: "Channel order" },
  { value: "name", label: "Name A–Z" },
  { value: "videos", label: "Most videos" },
  { value: "duration", label: "Longest first" },
] as const;

export type ChannelVideoSort = (typeof CHANNEL_VIDEO_SORT)[number]["value"];
export type ChannelPlaylistSort = (typeof CHANNEL_PLAYLIST_SORT)[number]["value"];

export interface ChannelVideoSortable {
  title: string;
  duration: number;
  start_time?: string | null;
}

export interface ChannelPlaylistSortable {
  name: string;
  video_count: number;
  duration_sum: number;
}

export function parseChannelVideoSort(raw: string | null): ChannelVideoSort {
  return CHANNEL_VIDEO_SORT.some((o) => o.value === raw) ? (raw as ChannelVideoSort) : "order";
}

export function parseChannelPlaylistSort(raw: string | null): ChannelPlaylistSort {
  return CHANNEL_PLAYLIST_SORT.some((o) => o.value === raw) ? (raw as ChannelPlaylistSort) : "order";
}

export function channelVideoSearchName(title: string): string {
  return stripLeadingTimestamp(title);
}

export function sortChannelVideos<T extends ChannelVideoSortable>(items: T[], sort: ChannelVideoSort): T[] {
  if (sort === "order") return items;
  const copy = [...items];
  copy.sort((a, b) => {
    if (sort === "newest") return (b.start_time ?? "").localeCompare(a.start_time ?? "");
    if (sort === "oldest") return (a.start_time ?? "").localeCompare(b.start_time ?? "");
    if (sort === "name") {
      return channelVideoSearchName(a.title).localeCompare(channelVideoSearchName(b.title), undefined, {
        sensitivity: "base",
      });
    }
    return (b.duration ?? 0) - (a.duration ?? 0);
  });
  return copy;
}

export function sortChannelPlaylists<T extends ChannelPlaylistSortable>(
  items: T[],
  sort: ChannelPlaylistSort,
): T[] {
  if (sort === "order") return items;
  const copy = [...items];
  copy.sort((a, b) => {
    if (sort === "name") return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    if (sort === "videos") return b.video_count - a.video_count;
    return (b.duration_sum ?? 0) - (a.duration_sum ?? 0);
  });
  return copy;
}
