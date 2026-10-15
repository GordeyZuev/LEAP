import { apiClient } from "@/api/client";

export interface YouTubePlaylist {
  id: string;
  title: string;
  description: string;
  privacy_status: "public" | "private" | "unlisted";
  item_count: number;
  url: string;
}

export interface YouTubePlaylistPage {
  items: YouTubePlaylist[];
  next_page_token: string | null;
  total: number;
}

export interface YouTubePlaylistInput {
  title: string;
  description: string;
  privacy_status: YouTubePlaylist["privacy_status"];
}

export async function listYouTubePlaylists(
  credentialId: number,
  params: { q?: string; page_token?: string },
  signal?: AbortSignal,
): Promise<YouTubePlaylistPage> {
  const { data } = await apiClient.get<YouTubePlaylistPage>(
    `/credentials/${credentialId}/youtube/playlists`,
    { params, signal, timeout: 60_000 },
  );
  return data;
}

export async function getYouTubePlaylist(credentialId: number, playlistId: string, signal?: AbortSignal) {
  const { data } = await apiClient.get<YouTubePlaylist>(
    `/credentials/${credentialId}/youtube/playlists/${encodeURIComponent(playlistId)}`,
    { signal, timeout: 60_000 },
  );
  return data;
}

export async function createYouTubePlaylist(credentialId: number, input: YouTubePlaylistInput) {
  const { data } = await apiClient.post<YouTubePlaylist>(
    `/credentials/${credentialId}/youtube/playlists`,
    input,
    { timeout: 60_000 },
  );
  return data;
}

export async function updateYouTubePlaylist(
  credentialId: number,
  playlistId: string,
  input: YouTubePlaylistInput,
) {
  const { data } = await apiClient.patch<YouTubePlaylist>(
    `/credentials/${credentialId}/youtube/playlists/${encodeURIComponent(playlistId)}`,
    input,
    { timeout: 60_000 },
  );
  return data;
}
