"use client";

import { VideoVariantSwitch } from "@/components/ui/video-variant-switch";

export function WatchVideoVariantChrome({
  bothVariants,
  variant,
  onVariantChange,
  showTimelineHint,
}: {
  bothVariants: boolean;
  variant: "processed" | "original";
  onVariantChange: (next: "processed" | "original") => void;
  showTimelineHint: boolean;
}) {
  if (!bothVariants) return null;
  return (
    <div className="mt-1 space-y-1.5">
      <VideoVariantSwitch value={variant} onChange={onVariantChange} className="text-xs" />
      {showTimelineHint && (
        <p className="text-xs text-muted-foreground">Chapters and transcript follow the edited video.</p>
      )}
    </div>
  );
}
