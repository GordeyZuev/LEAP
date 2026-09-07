import { apiClient } from "@/api/client";

export interface DailyPoint {
  date: string;
  recordings_created: number;
  transcription_minutes: number;
  transcription_jobs: number;
  share_views: number;
  share_downloads: number;
  failed_recordings: number;
  active_users?: number | null;
}

export interface DailyUploadPoint {
  date: string;
  by_platform: Record<string, number>;
}

export interface AnalyticsSummary {
  recordings_created: number;
  transcription_minutes: number;
  transcription_jobs: number;
  share_views: number;
  share_downloads: number;
  failed_recordings: number;
  active_users_unique?: number | null;
  uploads_total: number;
}

export interface TemplateBreakdown {
  template_id: number;
  template_name: string | null;
  count: number;
}

export interface AnalyticsBreakdown {
  uploads_by_platform: Record<string, number>;
  recordings_by_status: Record<string, number>;
  top_templates: TemplateBreakdown[];
  downloads_by_type: Record<string, number>;
}

export interface UserAnalyticsResponse {
  period: { from: string; to: string };
  daily: DailyPoint[];
  daily_uploads: DailyUploadPoint[];
  summary: AnalyticsSummary;
  breakdown: AnalyticsBreakdown;
}

export interface UsageEventItem {
  id: string;
  event_type: string;
  recording_id: number | null;
  duration_seconds: number | null;
  created_at: string;
}

export async function fetchUserAnalytics(from: string, to: string): Promise<UserAnalyticsResponse> {
  const { data } = await apiClient.get<UserAnalyticsResponse>("/users/me/analytics", {
    params: { from, to },
  });
  return data;
}

export async function fetchPlatformAnalytics(from: string, to: string): Promise<UserAnalyticsResponse> {
  const { data } = await apiClient.get<UserAnalyticsResponse>("/admin/stats/analytics", {
    params: { from, to },
  });
  return data;
}

export async function fetchAdminUserAnalytics(
  userId: string,
  from: string,
  to: string,
): Promise<UserAnalyticsResponse> {
  const { data } = await apiClient.get<UserAnalyticsResponse>(`/admin/users/${userId}/analytics`, {
    params: { from, to },
  });
  return data;
}

export async function fetchAdminUserEvents(
  userId: string,
  from: string,
  to: string,
  limit = 20,
): Promise<UsageEventItem[]> {
  const { data } = await apiClient.get<UsageEventItem[]>(`/admin/users/${userId}/events`, {
    params: { from, to, limit },
  });
  return data;
}

import type { DailyStackedRow } from "@/components/charts/daily-stacked-bar-chart";

/** Merge daily_uploads into stacked chart rows. */
export function buildStackedUploadRows(dailyUploads: DailyUploadPoint[]): {
  rows: DailyStackedRow[];
  seriesKeys: string[];
} {
  const keys = new Set<string>();
  for (const day of dailyUploads) {
    for (const platform of Object.keys(day.by_platform)) {
      if (day.by_platform[platform] > 0) keys.add(platform);
    }
  }
  const seriesKeys = [...keys].sort();
  const rows: DailyStackedRow[] = dailyUploads.map((day) => {
    const row: DailyStackedRow = { date: day.date };
    for (const key of seriesKeys) {
      row[key] = day.by_platform[key] ?? 0;
    }
    return row;
  });
  return { rows, seriesKeys };
}

export function dailyMetric(data: DailyPoint[], key: keyof DailyPoint): { date: string; value: number }[] {
  return data.map((point) => ({
    date: point.date,
    value: Number(point[key] ?? 0),
  }));
}
