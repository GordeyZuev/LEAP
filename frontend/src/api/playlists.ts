import { apiClient } from "@/api/client";

export interface PlaylistSummary {
  id: number;
  name: string;
  item_id: number;
}

export interface PlaylistListItem {
  id: number;
  name: string;
  description: string | null;
  video_count: number;
  duration_sum: number;
  share_enabled: boolean;
  poster_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlaylistListResponse {
  items: PlaylistListItem[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface PlaylistDetail {
  id: number;
  name: string;
  description: string | null;
  video_count: number;
  duration_sum: number;
  share_token: string | null;
  share_enabled: boolean;
  share_created_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlaylistItem {
  id: number;
  recording_id: number;
  position: number;
  display_name: string;
  start_time: string;
  duration: number;
  playable: boolean;
  unavailable_reason: string | null;
  poster_url: string | null;
  deleted: boolean;
  blank_record: boolean;
}

export interface PlaylistItemsResponse {
  items: PlaylistItem[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface PlaylistShareResponse {
  share_token: string;
  share_enabled: boolean;
}

export async function listPlaylists(params: {
  q?: string;
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}): Promise<PlaylistListResponse> {
  const res = await apiClient.get<PlaylistListResponse>("/playlists", { params });
  return res.data;
}

export async function getPlaylist(id: number): Promise<PlaylistDetail> {
  const res = await apiClient.get<PlaylistDetail>(`/playlists/${id}`);
  return res.data;
}

export async function createPlaylist(body: { name: string; description?: string | null }): Promise<PlaylistDetail> {
  const res = await apiClient.post<PlaylistDetail>("/playlists", body);
  return res.data;
}

export async function updatePlaylist(
  id: number,
  body: { name?: string; description?: string | null },
): Promise<PlaylistDetail> {
  const res = await apiClient.patch<PlaylistDetail>(`/playlists/${id}`, body);
  return res.data;
}

export async function deletePlaylist(id: number): Promise<void> {
  await apiClient.delete(`/playlists/${id}`);
}

export async function listPlaylistItems(
  id: number,
  params?: { q?: string; from_date?: string; to_date?: string; page?: number; per_page?: number },
): Promise<PlaylistItemsResponse> {
  const res = await apiClient.get<PlaylistItemsResponse>(`/playlists/${id}/items`, { params });
  return res.data;
}

export async function addPlaylistItems(id: number, recordingIds: number[]): Promise<PlaylistItem[]> {
  const res = await apiClient.post<PlaylistItem[]>(`/playlists/${id}/items`, { recording_ids: recordingIds });
  return res.data;
}

export async function removePlaylistItem(playlistId: number, itemId: number): Promise<void> {
  await apiClient.delete(`/playlists/${playlistId}/items/${itemId}`);
}

export async function reorderPlaylistItems(playlistId: number, itemIds: number[]): Promise<void> {
  await apiClient.put(`/playlists/${playlistId}/items/order`, { item_ids: itemIds });
}

export async function enablePlaylistShare(id: number): Promise<PlaylistShareResponse> {
  const res = await apiClient.post<PlaylistShareResponse>(`/playlists/${id}/share`);
  return res.data;
}

export async function disablePlaylistShare(id: number): Promise<void> {
  await apiClient.delete(`/playlists/${id}/share`);
}

export async function rotatePlaylistShare(id: number): Promise<PlaylistShareResponse> {
  const res = await apiClient.post<PlaylistShareResponse>(`/playlists/${id}/share/rotate`);
  return res.data;
}
