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
  days: 7 | 28 = 28,
): Promise<ShareAnalyticsResponse> {
  const res = await apiClient.get<ShareAnalyticsResponse>(`/recordings/${recordingId}/share/analytics`, {
    params: { days },
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

export async function sendSharePageBeacon(token: string): Promise<void> {
  await sendPublicBeacon(`/share/${token}/beacon`);
}

export async function sendPlaylistSharePageBeacon(token: string, itemId: number): Promise<void> {
  await sendPublicBeacon(`/share/p/${token}/items/${itemId}/beacon`);
}

// --- Public endpoints (no auth required) ---

export async function getPublicRecording(token: string): Promise<PublicRecordingResponse> {
  const res = await publicClient.get<PublicRecordingResponse>(`/share/${token}`);
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

export async function getPublicPlaylistItem(token: string, itemId: number): Promise<PublicRecordingResponse> {
  const res = await publicClient.get<PublicRecordingResponse>(`/share/p/${token}/items/${itemId}`);
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
