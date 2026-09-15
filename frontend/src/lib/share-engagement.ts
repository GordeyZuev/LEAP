const SESSION_KEY = "leap:engagement-session";
const MAX_QUEUE = 20;

export type EngagementEventName =
  | "chapter_seek"
  | "playlist_navigate"
  | "playback_complete"
  | "watch_exit";

export type ChapterSeekSource = "marker" | "sidebar" | "transcript";

export type PlaylistNavFrom = "sidebar" | "landing" | "autoplay" | "url";

export interface EngagementEventPayload {
  [key: string]: string | number | boolean | null | undefined;
}

export function getEngagementSessionId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const id = crypto.randomUUID();
    window.sessionStorage.setItem(SESSION_KEY, id);
    return id;
  } catch {
    return crypto.randomUUID();
  }
}

export function trackPlaylistNavigateDeduped(
  track: (name: EngagementEventName, payload: EngagementEventPayload) => void,
  dedupeKey: string,
  payload: { to_item_id: number; from: PlaylistNavFrom },
): void {
  const now = Date.now();
  const last = recentNavigateAt.get(dedupeKey) ?? 0;
  if (now - last < 750) return;
  recentNavigateAt.set(dedupeKey, now);
  track("playlist_navigate", payload);
}

const recentNavigateAt = new Map<string, number>();

export function createEngagementTracker(ingestPath: string) {
  const queue: { name: EngagementEventName; payload: EngagementEventPayload }[] = [];

  const track = (name: EngagementEventName, payload: EngagementEventPayload = {}) => {
    if (!ingestPath) return;
    queue.push({ name, payload });
    if (queue.length >= MAX_QUEUE) {
      void flushEngagementQueue(ingestPath, queue);
    }
  };

  const flush = () => {
    void flushEngagementQueue(ingestPath, queue);
  };

  return { track, flush };
}

export async function flushEngagementQueue(
  ingestPath: string,
  queue: { name: EngagementEventName; payload: EngagementEventPayload }[],
): Promise<void> {
  if (!ingestPath || queue.length === 0) return;
  const events = queue.splice(0, MAX_QUEUE);
  const body = {
    session_id: getEngagementSessionId(),
    events: events.map((e) => ({ name: e.name, payload: e.payload })),
  };
  const { sendPublicEngagementBeacon } = await import("@/api/share");
  await sendPublicEngagementBeacon(ingestPath, body);
}
