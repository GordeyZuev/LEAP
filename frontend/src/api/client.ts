import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

import { CSRF_HEADER_NAME, getCsrfToken } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
  // Cookies hold the session; CORS on the backend is configured with
  // allow_credentials=true to match.
  withCredentials: true,
});

const MUTATING_METHODS = new Set(["post", "put", "patch", "delete"]);

apiClient.interceptors.request.use((config) => {
  // Mutating requests need the CSRF header for the double-submit defence.
  // The backend ignores the header on Bearer-authenticated requests, so it's
  // safe to always attach when we have one.
  const method = (config.method ?? "get").toLowerCase();
  if (MUTATING_METHODS.has(method)) {
    const csrf = getCsrfToken();
    if (csrf) config.headers.set(CSRF_HEADER_NAME, csrf);
  }
  return config;
});

// Per-request retry guard — WeakMap so we don't mutate shared config objects.
const retriedRequests = new WeakMap<InternalAxiosRequestConfig, true>();

// Dedupe parallel refreshes: many concurrent 401s share one /auth/refresh call.
let refreshInflight: Promise<unknown> | null = null;

function refreshSession() {
  if (!refreshInflight) {
    const csrf = getCsrfToken();
    refreshInflight = axios
      .post(`${API_URL}/api/v1/auth/refresh`, {}, {
        withCredentials: true,
        headers: csrf ? { [CSRF_HEADER_NAME]: csrf } : {},
      })
      .finally(() => {
        refreshInflight = null;
      });
  }
  return refreshInflight;
}

function redirectToLogin() {
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

apiClient.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig | undefined;
    if (!original || error.response?.status !== 401 || retriedRequests.has(original)) {
      if (error.response?.status === 401) redirectToLogin();
      return Promise.reject(error);
    }

    // Refresh itself failed → kick to login; never recurse.
    if (original.url?.includes("/auth/refresh")) {
      redirectToLogin();
      return Promise.reject(error);
    }

    retriedRequests.set(original, true);

    try {
      await refreshSession();
      return apiClient(original);
    } catch (refreshErr) {
      redirectToLogin();
      return Promise.reject(refreshErr);
    }
  },
);
