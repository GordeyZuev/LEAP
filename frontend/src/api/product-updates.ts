import { apiClient } from "@/api/client";

export type ProductInterest = "viewers" | "course_publishing" | "video_processing";
export type FeedbackKind = "idea" | "problem" | "question" | "other";

export interface ProductUpdate {
  id: string;
  version: string | null;
  title: string;
  summary: string;
  audience_bullets: string[];
  creator_bullets: string[];
  release_date: string | null;
  published_at: string | null;
}

export interface AdminProductUpdate extends ProductUpdate {
  audiences: ProductInterest[];
  is_published: boolean;
  newsletter_enabled: boolean;
  created_at: string;
  updated_at: string;
  email_requested_at: string | null;
  delivery_counts: Record<string, number>;
}

export interface ProductUpdateWrite {
  version: string | null;
  title: string;
  summary: string;
  audience_bullets: string[];
  creator_bullets: string[];
  audiences: ProductInterest[];
  newsletter_enabled: boolean;
}

export interface ProductNewsStats {
  subscriptions_total: number;
  subscriptions_pending: number;
  subscriptions_confirmed: number;
  subscriptions_unsubscribed: number;
  interests: Record<ProductInterest, number>;
  feedback_total: number;
  feedback_by_kind: Record<string, number>;
  feedback_by_interest: Record<ProductInterest, number>;
  delivery_by_status: Record<string, number>;
}

export interface ProductFeedback {
  id: string;
  interests: ProductInterest[];
  kind: FeedbackKind;
  message: string;
  reply_email: string | null;
  created_at: string;
}

export const INTEREST_OPTIONS: { value: ProductInterest; label: string }[] = [
  { value: "viewers", label: "Watching materials" },
  { value: "course_publishing", label: "Publishing courses" },
  { value: "video_processing", label: "Video processing" },
];

export async function fetchProductUpdates(limit = 100): Promise<ProductUpdate[]> {
  const { data } = await apiClient.get<ProductUpdate[]>(`/product-updates?limit=${limit}`);
  return data;
}

export async function fetchLatestProductUpdate(): Promise<ProductUpdate | null> {
  const updates = await fetchProductUpdates(1);
  return updates[0] ?? null;
}

export async function subscribeProductNews(email: string, interests: ProductInterest[]) {
  const { data } = await apiClient.post<{ message: string }>("/product-news/subscribe", { email, interests });
  return data;
}

export async function confirmProductNews(token: string) {
  const { data } = await apiClient.post<{ message: string }>("/product-news/confirm", { token });
  return data;
}

export async function unsubscribeProductNews(token: string) {
  const { data } = await apiClient.post<{ message: string }>("/product-news/unsubscribe", { token });
  return data;
}

export async function fetchProductNewsPreferences(token: string) {
  const { data } = await apiClient.post<{ interests: ProductInterest[] }>("/product-news/preferences/validate", { token });
  return data.interests;
}

export async function updateProductNewsPreferences(token: string, interests: ProductInterest[]) {
  const { data } = await apiClient.put<{ message: string }>("/product-news/preferences", { token, interests });
  return data;
}

export async function submitProductFeedback(payload: {
  interests: ProductInterest[];
  kind: FeedbackKind;
  message: string;
  reply_email: string | null;
}) {
  await apiClient.post("/product-feedback", payload);
}

export async function fetchAdminProductUpdates() {
  const { data } = await apiClient.get<AdminProductUpdate[]>("/admin/product-updates");
  return data;
}

export async function saveAdminProductUpdate(payload: ProductUpdateWrite, id?: string) {
  const { data } = id
    ? await apiClient.patch<AdminProductUpdate>(`/admin/product-updates/${id}`, payload)
    : await apiClient.post<AdminProductUpdate>("/admin/product-updates", payload);
  return data;
}

export async function publishAdminProductUpdate(id: string) {
  const { data } = await apiClient.post<AdminProductUpdate>(`/admin/product-updates/${id}/publish`);
  return data;
}

export async function sendAdminProductUpdate(id: string) {
  const { data } = await apiClient.post<AdminProductUpdate>(`/admin/product-updates/${id}/send`);
  return data;
}

export async function retryAdminProductUpdate(id: string) {
  const { data } = await apiClient.post<AdminProductUpdate>(`/admin/product-updates/${id}/retry`);
  return data;
}

export async function deleteAdminProductUpdate(id: string) {
  await apiClient.delete(`/admin/product-updates/${id}`);
}

export async function fetchProductNewsStats() {
  const { data } = await apiClient.get<ProductNewsStats>("/admin/product-news/stats");
  return data;
}

export async function fetchProductNewsAudienceCount(interests: ProductInterest[]) {
  const params = new URLSearchParams();
  for (const interest of interests) params.append("interests", interest);
  const { data } = await apiClient.get<{ count: number }>(`/admin/product-news/audience-count?${params.toString()}`);
  return data.count;
}

export async function fetchProductFeedback() {
  const { data } = await apiClient.get<ProductFeedback[]>("/admin/product-feedback");
  return data;
}
