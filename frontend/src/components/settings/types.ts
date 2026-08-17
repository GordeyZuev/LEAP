import type { DisplayConfig } from "@/components/platforms/display-config-fields";

export interface UserMe {
  id: string;
  email: string;
  full_name: string | null;
  timezone: string;
  role: string;
  created_at: string;
}

export interface TrimmingConfig {
  enable_trimming: boolean;
  audio_detection: boolean;
  silence_threshold: number;
  min_silence_duration: number;
  padding_before: number;
  padding_after: number;
}

export interface TranscriptionConfig {
  enable_transcription: boolean;
  language: string;
  vocabulary: string[];
  allow_errors: boolean;
  enable_topics: boolean;
  granularity: string;
  questions_count: number;
  enable_subtitles: boolean;
  enable_translation: boolean;
  translation_language: string;
}

export interface DownloadConfig {
  auto_download: boolean;
  max_file_size_mb: number;
  quality: string;
  retry_attempts: number;
  retry_delay: number;
}

export interface UploadConfig {
  auto_upload: boolean;
  upload_captions: boolean;
}

export interface MetadataConfig {
  title_template: string;
  description_template: string;
  date_format: string;
  tags: string[];
  topics_display: DisplayConfig;
  questions_display: DisplayConfig;
}

export interface RetentionConfig {
  soft_delete_days: number;
  hard_delete_days: number;
  auto_expire_days: number;
}

export interface ConfigBundle {
  trimming: TrimmingConfig;
  transcription: TranscriptionConfig;
  download: DownloadConfig;
  upload: UploadConfig;
  metadata: MetadataConfig;
  retention: RetentionConfig;
}

export interface UserConfig {
  config_data: ConfigBundle;
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
