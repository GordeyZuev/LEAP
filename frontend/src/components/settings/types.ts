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

export interface SubscriptionPlanQuotas {
  display_name: string;
  included_recordings_per_month?: number | null;
  included_storage_gb?: number | null;
  max_concurrent_tasks?: number | null;
  max_automation_jobs?: number | null;
  max_transcriptions_per_month?: number | null;
  max_processing_per_month?: number | null;
  max_templates?: number | null;
  max_credentials?: number | null;
}

export interface QuotaStatus {
  subscription?: {
    plan: SubscriptionPlanQuotas;
    expires_at?: string | null;
    effective_max_recordings_per_month?: number | null;
    effective_max_storage_gb?: number | null;
    effective_max_concurrent_tasks?: number | null;
    effective_max_automation_jobs?: number | null;
    effective_max_templates?: number | null;
    effective_max_credentials?: number | null;
  } | null;
  recordings: { used?: number | null; limit?: number | null; available?: number | null };
  storage: { used_gb?: number | null; limit_gb?: number | null; available_gb?: number | null };
  concurrent_tasks: { used?: number | null; limit?: number | null; available?: number | null };
  automation_jobs: { used?: number | null; limit?: number | null; available?: number | null };
  transcriptions?: { used?: number | null; limit?: number | null; available?: number | null };
  processing?: { used?: number | null; limit?: number | null; available?: number | null };
  templates?: { used?: number | null; limit?: number | null; available?: number | null };
  credentials?: { used?: number | null; limit?: number | null; available?: number | null };
  is_overage_enabled: boolean;
}
