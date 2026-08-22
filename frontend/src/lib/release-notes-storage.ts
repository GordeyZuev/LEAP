const LAST_SEEN_RELEASE_KEY = "leap:lastSeenRelease";

export function getLastSeenRelease(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(LAST_SEEN_RELEASE_KEY);
}

export function markReleaseSeen(version: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LAST_SEEN_RELEASE_KEY, version);
}

/** True when the user has not dismissed release notes for this app version. */
export function shouldShowReleaseNotes(version: string): boolean {
  return getLastSeenRelease() !== version;
}
