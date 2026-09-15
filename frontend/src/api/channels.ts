import { apiClient } from "@/api/client";
import type { ShareAnalyticsResponse } from "@/api/share";

export interface ChannelListItem {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  share_enabled: boolean;
  video_count: number;
  playlist_count: number;
  banner_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelListResponse {
  items: ChannelListItem[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export type ChannelDetail = ChannelListItem;

export interface ChannelShareResponse {
  slug: string;
  share_enabled: boolean;
}

export interface ChannelSummary {
  id: number;
  name: string;
  slug: string;
  membership_id: number;
}

export interface ChannelVideoRow {
  recording_id: number;
  position: number;
  title: string;
  duration: number;
  share_enabled: boolean;
  playable: boolean;
  public_visible: boolean;
  hidden_reason: string | null;
  poster_url: string | null;
  poster_asset_key?: string | null;
  share_token: string | null;
}

export interface ChannelPlaylistRow {
  playlist_id: number;
  position: number;
  name: string;
  video_count: number;
  duration_sum: number;
  share_enabled: boolean;
  public_visible: boolean;
  hidden_reason: string | null;
  poster_url: string | null;
  poster_asset_key?: string | null;
  share_token: string | null;
  has_custom_cover: boolean;
}

export interface ChannelMembershipListResponse<T> {
  items: T[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export async function listChannels(params: {
  q?: string;
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}): Promise<ChannelListResponse> {
  const res = await apiClient.get<ChannelListResponse>("/channels", { params });
  return res.data;
}

export async function createChannel(body: { name: string; slug?: string; description?: string | null }): Promise<ChannelDetail> {
  const res = await apiClient.post<ChannelDetail>("/channels", body);
  return res.data;
}

export async function getChannel(id: number): Promise<ChannelDetail> {
  const res = await apiClient.get<ChannelDetail>(`/channels/${id}`);
  return res.data;
}

export async function updateChannel(
  id: number,
  body: { name?: string; slug?: string; description?: string | null },
): Promise<ChannelDetail> {
  const res = await apiClient.patch<ChannelDetail>(`/channels/${id}`, body);
  return res.data;
}

export async function deleteChannel(id: number): Promise<void> {
  await apiClient.delete(`/channels/${id}`);
}

export async function enableChannelShare(id: number): Promise<ChannelShareResponse> {
  const res = await apiClient.post<ChannelShareResponse>(`/channels/${id}/share`);
  return res.data;
}

export async function disableChannelShare(id: number): Promise<void> {
  await apiClient.delete(`/channels/${id}/share`);
}

export async function uploadChannelBanner(id: number, file: File): Promise<ChannelDetail> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiClient.post<ChannelDetail>(`/channels/${id}/banner`, form);
  return res.data;
}

export async function deleteChannelBanner(id: number): Promise<ChannelDetail> {
  const res = await apiClient.delete<ChannelDetail>(`/channels/${id}/banner`);
  return res.data;
}

export async function listChannelVideos(
  id: number,
  params?: { page?: number; per_page?: number },
): Promise<ChannelMembershipListResponse<ChannelVideoRow>> {
  const res = await apiClient.get<ChannelMembershipListResponse<ChannelVideoRow>>(`/channels/${id}/videos`, { params });
  return res.data;
}

export async function addChannelVideos(id: number, ids: number[]): Promise<void> {
  await apiClient.post(`/channels/${id}/videos`, { ids });
}

export async function removeChannelVideo(channelId: number, recordingId: number): Promise<void> {
  await apiClient.delete(`/channels/${channelId}/videos/${recordingId}`);
}

export async function reorderChannelVideos(id: number, ids: number[]): Promise<void> {
  await apiClient.put(`/channels/${id}/videos/order`, { ids });
}

export async function listChannelPlaylists(
  id: number,
  params?: { page?: number; per_page?: number },
): Promise<ChannelMembershipListResponse<ChannelPlaylistRow>> {
  const res = await apiClient.get<ChannelMembershipListResponse<ChannelPlaylistRow>>(`/channels/${id}/playlists`, {
    params,
  });
  return res.data;
}

export async function addChannelPlaylists(id: number, ids: number[]): Promise<void> {
  await apiClient.post(`/channels/${id}/playlists`, { ids });
}

export async function removeChannelPlaylist(channelId: number, playlistId: number): Promise<void> {
  await apiClient.delete(`/channels/${channelId}/playlists/${playlistId}`);
}

export async function reorderChannelPlaylists(id: number, ids: number[]): Promise<void> {
  await apiClient.put(`/channels/${id}/playlists/order`, { ids });
}

export async function fetchChannelShareAnalytics(
  channelId: number,
  range: { from: string; to: string },
): Promise<ShareAnalyticsResponse> {
  const res = await apiClient.get<ShareAnalyticsResponse>(`/channels/${channelId}/share/analytics`, { params: range });
  return res.data;
}
