"use client";

import { ListVideo } from "lucide-react";

import { StablePosterImage } from "@/components/recordings/recording-poster";
import { cn } from "@/lib/utils";

/**
 * YouTube-style collection thumbnail: two receding layers behind the poster
 * plus a count badge, so a playlist does not read as a single video.
 */
export function PlaylistStackPoster({
  posterUrl,
  posterAssetKey,
  videoCount,
  className,
  wrapperClassName,
  placeholderIconSize = 16,
  size = "md",
}: {
  posterUrl?: string | null;
  posterAssetKey?: string | null;
  videoCount: number;
  className?: string;
  wrapperClassName?: string;
  placeholderIconSize?: number;
  size?: "sm" | "md";
}) {
  const compact = size === "sm";
  const label = `${videoCount} ${videoCount === 1 ? "video" : "videos"}`;

  return (
    <div className={cn("relative", compact ? "pt-1.5" : "pt-2", wrapperClassName)}>
      <div
        className="pointer-events-none absolute inset-x-[12%] top-0 h-[calc(100%-10px)] rounded-t-lg bg-foreground/15"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute inset-x-[6%] top-[3px] h-[calc(100%-6px)] rounded-t-lg bg-foreground/25"
        aria-hidden
      />
      <div className="relative">
        <StablePosterImage
          posterUrl={posterUrl}
          posterAssetKey={posterAssetKey}
          className={className}
          placeholderIconSize={placeholderIconSize}
        />
        <div
          className={cn(
            "pointer-events-none absolute bottom-1.5 end-1.5 flex items-center gap-1 rounded-md bg-black/75 text-white",
            compact ? "px-1 py-0.5" : "px-1.5 py-0.5",
          )}
        >
          <ListVideo size={compact ? 10 : 12} strokeWidth={2} aria-hidden />
          <span className={cn("font-medium tabular-nums", compact ? "text-[9px]" : "text-[10px]")}>
            {compact ? videoCount : label}
          </span>
        </div>
      </div>
    </div>
  );
}
