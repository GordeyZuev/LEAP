// Auth helpers for the cookie-based session flow.
// Access/refresh tokens live in httpOnly cookies. The csrf_token cookie is
// readable so JS can echo it back in X-CSRF-Token on mutating requests.

export const CSRF_COOKIE_NAME = "csrf_token";
export const CSRF_HEADER_NAME = "X-CSRF-Token";

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  for (const raw of document.cookie.split(";")) {
    const trimmed = raw.trim();
    if (trimmed.startsWith(`${CSRF_COOKIE_NAME}=`)) {
      return decodeURIComponent(trimmed.slice(CSRF_COOKIE_NAME.length + 1));
    }
  }
  return null;
}

// Proxy for "logged in" — the access cookie itself is httpOnly so JS can't see it.
export function hasSessionCookie(): boolean {
  return getCsrfToken() !== null;
}

// Allowlist guards against a tainted authorization_url from the backend turning
// the OAuth redirect into an open-redirect.
const OAUTH_ALLOWED_HOSTS: ReadonlySet<string> = new Set([
  "accounts.google.com",
  "oauth.vk.com",
  "id.vk.com",
  "oauth.vk.ru",
  "id.vk.ru",
  "zoom.us",
  "oauth.yandex.ru",
  "oauth.yandex.com",
]);

export function isAllowedOAuthUrl(raw: string): boolean {
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:") return false;
    return OAUTH_ALLOWED_HOSTS.has(url.hostname);
  } catch {
    return false;
  }
}
