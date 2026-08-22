import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export const VIDEO_PLAYER_FRAME = "relative aspect-video w-full rounded-xl";

export function VideoPlayerLoading({ theme = "light" }: { theme?: "light" | "dark" }) {
  const dark = theme === "dark";
  return (
    <div className={cn(VIDEO_PLAYER_FRAME, "flex items-center justify-center", dark ? "bg-black" : "bg-muted")}>
      <Loader2 size={24} className={cn("animate-spin", dark ? "text-white/40" : "text-muted-foreground")} />
    </div>
  );
}
