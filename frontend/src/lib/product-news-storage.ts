const LAST_SEEN_KEY = "leap:lastSeenProductNews";

export function hasSeenProductNews(id: string | null | undefined): boolean {
  if (!id || typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(LAST_SEEN_KEY) === id;
  } catch {
    return true;
  }
}

export function markProductNewsSeen(id: string): void {
  try {
    if (typeof window !== "undefined") window.localStorage.setItem(LAST_SEEN_KEY, id);
  } catch {
    // News remains accessible when browser storage is unavailable.
  }
}
