import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export const VIDEO_PLAYER_FRAME = "relative aspect-video w-full overflow-hidden rounded-xl bg-muted";

export function VideoPlayerLoading() {
  return (
    <div className={cn(VIDEO_PLAYER_FRAME, "flex items-center justify-center")}>
      <Loader2 size={24} className="animate-spin text-muted-foreground" />
    </div>
  );
}
