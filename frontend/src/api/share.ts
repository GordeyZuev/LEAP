import axios from "axios";

import { apiClient } from "@/api/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Public client — no cookies, no CSRF, for unauthenticated share endpoints
const publicClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

export interface ShareCreateResponse {
  share_token: string;
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
}

export interface ShareMediaResponse {
  url: string;
  expires_in: number;
}

// --- Owner endpoints (require auth) ---

export async function createShareLink(recordingId: number): Promise<ShareCreateResponse> {
  const res = await apiClient.post<ShareCreateResponse>(`/recordings/${recordingId}/share`);
  return res.data;
}

export async function revokeShareLink(recordingId: number): Promise<void> {
  await apiClient.delete(`/recordings/${recordingId}/share`);
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

export function getShareFileUrl(token: string, fileType: string): string {
  return `${API_URL}/api/v1/share/${token}/files/${fileType}`;
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
    const res = await fetch(`${API_URL}/api/v1/share/${token}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as PublicRecordingResponse;
  } catch {
    return null;
  }
}
