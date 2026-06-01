import { apiClient } from "./client";

export interface SessionInfo {
  id: number;
  device_label: string | null;
  user_agent: string | null;
  last_used_at: string | null;
  created_at: string;
  is_current: boolean;
}

export interface SessionListResponse {
  sessions: SessionInfo[];
}

export async function fetchSessions(): Promise<SessionInfo[]> {
  const { data } = await apiClient.get<SessionListResponse>("/auth/sessions");
  return data.sessions;
}

export async function revokeSession(sessionId: number): Promise<void> {
  await apiClient.delete(`/auth/sessions/${sessionId}`);
}

export async function logoutOtherDevices(): Promise<void> {
  await apiClient.post("/auth/logout-others");
}

export async function logoutAllDevices(): Promise<void> {
  await apiClient.post("/auth/logout-all");
}
