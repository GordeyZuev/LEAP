import axios from "axios";

import { apiClient } from "@/api/client";
import type { ShareStatsSummary } from "@/lib/share-stats";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Absolute API origin for Next server code (generateMetadata, Open Graph). */
export function serverApiBase(): string {
  const internal = process.env.API_INTERNAL_URL?.replace(/\/$/, "");
  if (internal) return internal;
  if (API_URL) return API_URL.replace(/\/$/, "");
  return "http://localhost:8000";
}

// Public client — no cookies, no CSRF, for unauthenticated share endpoints
const publicClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

export interface ShareCreateResponse {
  share_token: string;
  share_enabled: boolean;
}

export interface PublicRecordingResponse {
  id: number;
  display_name: string;
  title?: string;
  duration: number;
  start_time: string;
  status: string;
  topic_timestamps: unknown | null;
  main_topics: unknown | null;
  summary: string | null;
  questions: string[] | null;
  description: string | null;
  available_files: string[];
  has_processed_video: boolean;
  has_original_video: boolean;
  allow_video_download?: boolean;
  allow_files_download?: boolean;
  source_extras?: {
    chat: { name: string; extension: string; size: number | null; url: string } | null;
    files: { name: string; extension: string; size: number | null; url: string }[];
    expires_in: number;
  } | null;
  play_url?: string | null;
  vtt_url?: string | null;
  media_expires_in?: number | null;
}

export interface PublicPlaylistItem {
  id: number;
  position: number;
  title: string;
  duration: number;
  start_time: string;
  playable: boolean;
  unavailable_reason: string | null;
  poster_url: string | null;
  poster_asset_key?: string | null;
}

export interface PublicPlaylistResponse {
  name: string;
  description: string | null;
  items: PublicPlaylistItem[];
}

export interface ShareMediaResponse {
  url: string;
  expires_in: number;
}

export interface ShareDailyPoint {
  date: string;
  views: number;
  downloads: number;
  opens?: number;
}

export interface ShareAnalyticsResponse {
  summary: ShareStatsSummary;
  daily: ShareDailyPoint[];
  downloads_by_type: Record<string, number>;
}

export type { ShareStatsSummary };

// --- Owner endpoints (require auth) ---

export async function enableShareLink(recordingId: number): Promise<ShareCreateResponse> {
  const res = await apiClient.post<ShareCreateResponse>(`/recordings/${recordingId}/share`);
  return res.data;
}

export async function disableShareLink(recordingId: number): Promise<void> {
  await apiClient.delete(`/recordings/${recordingId}/share`);
}

export async function rotateShareLink(recordingId: number): Promise<ShareCreateResponse> {
  const res = await apiClient.post<ShareCreateResponse>(`/recordings/${recordingId}/share/rotate`);
  return res.data;
}

export async function fetchShareAnalytics(
  recordingId: number,
  range: { from: string; to: string } | { days: 7 | 28 },
): Promise<ShareAnalyticsResponse> {
  const params = "days" in range ? { days: range.days } : { from: range.from, to: range.to };
  const res = await apiClient.get<ShareAnalyticsResponse>(`/recordings/${recordingId}/share/analytics`, {
    params,
  });
  return res.data;
}

async function sendPublicBeacon(apiPath: string): Promise<void> {
  const url = `${API_URL}/api/v1${apiPath}`;
  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    navigator.sendBeacon(url);
    return;
  }
  await publicClient.post(apiPath);
}

function fromQuery(): string {
  if (typeof window === "undefined") return "";
  const from = new URLSearchParams(window.location.search).get("from");
  return from ? `?from=${encodeURIComponent(from)}` : "";
}

export async function sendSharePageBeacon(token: string): Promise<void> {
  await sendPublicBeacon(`/share/${token}/beacon${fromQuery()}`);
}

export async function sendPlaylistSharePageBeacon(token: string, itemId: number): Promise<void> {
  await sendPublicBeacon(`/share/p/${token}/items/${itemId}/beacon${fromQuery()}`);
}

export async function sendPlaylistLandingBeacon(token: string): Promise<void> {
  await sendPublicBeacon(`/share/p/${token}/beacon`);
}

export async function sendChannelPageBeacon(slug: string): Promise<void> {
  await sendPublicBeacon(`/c/${slug}/beacon`);
}

export interface PublicChannelVideo {
  title: string;
  duration: number;
  start_time?: string | null;
  poster_url: string | null;
  poster_asset_key?: string | null;
  share_token: string;
  blurb?: string | null;
}

export interface PublicChannelPlaylist {
  name: string;
  video_count: number;
  duration_sum: number;
  poster_url: string | null;
  poster_asset_key?: string | null;
  share_token: string;
  blurb?: string | null;
}

export interface PublicChannelResponse {
  name: string;
  slug: string;
  description: string | null;
  banner_url: string | null;
  videos: PublicChannelVideo[];
  playlists: PublicChannelPlaylist[];
}

export async function getPublicChannel(slug: string): Promise<PublicChannelResponse> {
  const res = await publicClient.get<PublicChannelResponse>(`/c/${slug}`);
  return res.data;
}

export async function fetchPublicChannelForMetadata(slug: string): Promise<PublicChannelResponse | null> {
  try {
    const { data } = await axios.get<PublicChannelResponse>(`${serverApiBase()}/api/v1/c/${slug}`, {
      timeout: 4000,
    });
    return data;
  } catch {
    return null;
  }
}

// --- Public endpoints (no auth required) ---

export async function getPublicRecording(
  token: string,
  view: "full" | "player" = "full",
): Promise<PublicRecordingResponse> {
  const res = await publicClient.get<PublicRecordingResponse>(`/share/${token}`, {
    params: view === "player" ? { view: "player" } : {},
  });
  return res.data;
}

export async function getShareMedia(
  token: string,
  type: "processed" | "original" = "processed",
  download = false,
): Promise<ShareMediaResponse> {
  const res = await publicClient.get<ShareMediaResponse>(`/share/${token}/media`, {
    params: { type, ...(download ? { download: true } : {}) },
  });
  return res.data;
}

export function getShareFileUrl(token: string, fileType: string, inline = false): string {
  const url = `${API_URL}/api/v1/share/${token}/files/${fileType}`;
  return inline ? `${url}?inline=true` : url;
}

export async function getPublicPlaylist(token: string): Promise<PublicPlaylistResponse> {
  const res = await publicClient.get<PublicPlaylistResponse>(`/share/p/${token}`);
  return res.data;
}

export async function getPublicPlaylistItem(
  token: string,
  itemId: number,
  view: "full" | "player" = "full",
): Promise<PublicRecordingResponse> {
  const res = await publicClient.get<PublicRecordingResponse>(`/share/p/${token}/items/${itemId}`, {
    params: view === "player" ? { view: "player" } : {},
  });
  return res.data;
}

export async function getPlaylistShareMedia(
  token: string,
  itemId: number,
  download = false,
): Promise<ShareMediaResponse> {
  const res = await publicClient.get<ShareMediaResponse>(`/share/p/${token}/items/${itemId}/media`, {
    params: { type: "processed", ...(download ? { download: true } : {}) },
  });
  return res.data;
}

export function getPlaylistShareFileUrl(token: string, itemId: number, fileType: string, inline = false): string {
  const url = `${API_URL}/api/v1/share/p/${token}/items/${itemId}/files/${fileType}`;
  return inline ? `${url}?inline=true` : url;
}

export async function fetchPublicPlaylistForMetadata(token: string): Promise<PublicPlaylistResponse | null> {
  try {
    const res = await fetch(`${serverApiBase()}/api/v1/share/p/${token}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as PublicPlaylistResponse;
  } catch {
    return null;
  }
}

/**
 * Server-side fetch for `generateMetadata`.
 *
 * Uses `fetch` rather than the axios client so Next can cache it alongside the
 * render, and swallows every failure: a share link whose backend is briefly
 * down should still render the page, just without a rich preview.
 */
export async function fetchPublicRecordingForMetadata(
  token: string,
): Promise<PublicRecordingResponse | null> {
  try {
    const res = await fetch(`${serverApiBase()}/api/v1/share/${token}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as PublicRecordingResponse;
  } catch {
    return null;
  }
}
