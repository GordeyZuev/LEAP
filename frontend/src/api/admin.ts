import { apiClient } from "@/api/client";

// The five capability gates that survived the permissions→limits refactor.
// Count-based caps (templates, credentials) live in the subscription instead.
export const PERMISSION_FLAGS = [
  { key: "can_transcribe", label: "Transcribe" },
  { key: "can_process_video", label: "Process video" },
  { key: "can_upload", label: "Upload" },
  { key: "can_update_uploaded_videos", label: "Update uploaded videos" },
  { key: "can_export_data", label: "Export data" },
] as const;

export type PermissionKey = (typeof PERMISSION_FLAGS)[number]["key"];

export interface AdminUserProfile {
  id: string;
  email: string;
  user_slug: number;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  can_transcribe: boolean;
  can_process_video: boolean;
  can_upload: boolean;
  can_update_uploaded_videos: boolean;
  can_export_data: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AdminUserListResponse {
  total_count: number;
  users: AdminUserProfile[];
  page: number;
  page_size: number;
}

// Full plan object — matches SubscriptionPlanInDB from backend.
export interface AdminPlan {
  id: number;
  name: string;
  display_name: string;
  description: string | null;
  is_active: boolean;
  sort_order: number;
  // Quotas (null = unlimited)
  included_recordings_per_month: number | null;
  included_storage_gb: number | null;
  max_concurrent_tasks: number | null;
  max_automation_jobs: number | null;
  min_automation_interval_hours: number | null;
  max_transcriptions_per_month: number | null;
  max_processing_per_month: number | null;
  max_templates: number | null;
  max_credentials: number | null;
  // Pricing
  price_monthly: string; // Decimal serialised as string by FastAPI
  price_yearly: string;
}

export interface AdminPlanCreate {
  name: string;
  display_name: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number;
  included_recordings_per_month?: number | null;
  included_storage_gb?: number | null;
  max_concurrent_tasks?: number | null;
  max_automation_jobs?: number | null;
  min_automation_interval_hours?: number | null;
  max_transcriptions_per_month?: number | null;
  max_processing_per_month?: number | null;
  max_templates?: number | null;
  max_credentials?: number | null;
  price_monthly?: string;
  price_yearly?: string;
}

export type AdminPlanUpdate = Partial<Omit<AdminPlanCreate, "name">>;

// Custom per-user overrides. null = inherit plan / unlimited.
export interface SubscriptionOverrides {
  custom_max_recordings_per_month: number | null;
  custom_max_storage_gb: number | null;
  custom_max_concurrent_tasks: number | null;
  custom_max_automation_jobs: number | null;
  custom_min_automation_interval_hours: number | null;
  custom_max_templates: number | null;
  custom_max_credentials: number | null;
}

export interface AdminSubscriptionInfo {
  user_id: string;
  // Matches UserSubscriptionInDB: flat plan_id, no nested plan object.
  subscription: (SubscriptionOverrides & { id: number; plan_id: number }) | null;
  effective_quotas: Record<string, number | null>;
}

export interface AdminUserUpdate {
  role?: string;
  is_active?: boolean;
  is_verified?: boolean;
  can_transcribe?: boolean;
  can_process_video?: boolean;
  can_upload?: boolean;
  can_update_uploaded_videos?: boolean;
  can_export_data?: boolean;
}

export interface UserQuotaDetails {
  user_id: string;
  email: string;
  plan_name: string;
  recordings_used: number;
  recordings_limit: number | null;
  storage_used_gb: number;
  storage_limit_gb: number | null;
  is_exceeding: boolean;
  overage_enabled: boolean;
  overage_cost: string;
}

export interface AdminUserStatsResponse {
  total_count: number;
  users: UserQuotaDetails[];
  page: number;
  page_size: number;
}

// Users
export async function fetchAdminUsers(params: {
  page: number;
  page_size: number;
  search?: string;
  role?: string;
  exceeded_only?: boolean;
}): Promise<AdminUserListResponse> {
  const { data } = await apiClient.get("/admin/users", { params });
  return data;
}

export async function fetchAdminUserStats(params: {
  page: number;
  page_size: number;
  exceeded_only?: boolean;
}): Promise<AdminUserStatsResponse> {
  const { data } = await apiClient.get("/admin/stats/users", { params });
  return data;
}

export async function updateAdminUser(id: string, body: AdminUserUpdate): Promise<AdminUserProfile> {
  const { data } = await apiClient.patch(`/admin/users/${id}`, body);
  return data;
}

// Plans
export async function fetchAdminPlans(): Promise<AdminPlan[]> {
  const { data } = await apiClient.get("/admin/plans", { params: { active_only: false } });
  return data.plans ?? [];
}

export async function createAdminPlan(body: AdminPlanCreate): Promise<AdminPlan> {
  const { data } = await apiClient.post("/admin/plans", body);
  return data.plan;
}

export async function updateAdminPlan(id: number, body: AdminPlanUpdate): Promise<AdminPlan> {
  const { data } = await apiClient.patch(`/admin/plans/${id}`, body);
  return data.plan;
}

// Subscriptions
export async function fetchUserSubscription(id: string): Promise<AdminSubscriptionInfo> {
  const { data } = await apiClient.get(`/admin/users/${id}/subscription`);
  return data;
}

export interface SubscriptionSetBody extends Partial<SubscriptionOverrides> {
  plan_id: number;
}

export async function setUserSubscription(id: string, body: SubscriptionSetBody): Promise<void> {
  await apiClient.post(`/admin/users/${id}/subscription`, body);
}

export async function deleteUserSubscription(id: string): Promise<void> {
  await apiClient.delete(`/admin/users/${id}/subscription`);
}
