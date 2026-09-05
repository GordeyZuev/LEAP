import { cn } from "@/lib/utils";

export const VIDEO_PLAYER_FRAME =
  "relative aspect-video w-full overflow-hidden rounded-xl bg-muted outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10";

export function VideoPlayerLoading() {
  return (
    <div
      className={cn(VIDEO_PLAYER_FRAME, "video-fill-landscape animate-pulse")}
      role="status"
      aria-label="Loading video"
    />
  );
}
