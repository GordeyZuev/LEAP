export interface UserMe {
  id: string;
  email: string;
  full_name: string | null;
  timezone: string;
  role: string;
  created_at: string;
}

export interface RetentionConfig {
  soft_delete_days: number;
  hard_delete_days: number;
  auto_expire_days: number;
}

export interface UserConfig {
  config_data: {
    retention?: RetentionConfig;
  };
}

export interface QuotaStatus {
  subscription?: {
    plan: { display_name: string };
    expires_at?: string | null;
  } | null;
  recordings: { used?: number | null; limit?: number | null; available?: number | null };
  storage: { used_gb?: number | null; limit_gb?: number | null; available_gb?: number | null };
  concurrent_tasks: { used?: number | null; limit?: number | null };
  automation_jobs: { used?: number | null; limit?: number | null };
  is_overage_enabled: boolean;
}

export interface UserStats {
  recordings_total: number;
  recordings_by_status: Record<string, number>;
  transcription_total_seconds: number;
  storage_gb: number;
}
