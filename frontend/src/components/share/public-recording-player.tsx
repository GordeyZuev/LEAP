"use client";

import { useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { VideoOff } from "lucide-react";

import { getShareMedia } from "@/api/share";
import type { VideoPlayerMarker } from "@/components/ui/video-player";
import { VIDEO_PLAYER_FRAME, VideoPlayerLoading } from "@/components/ui/video-player-frame";
import { usePresignedMediaRefresh } from "@/hooks/use-presigned-media";
import { cn, httpStatus } from "@/lib/utils";
import { recordingResumeKey } from "@/lib/video-resume";

const VideoPlayer = dynamic(
  () => import("@/components/ui/video-player").then((m) => m.VideoPlayer),
  { ssr: false, loading: () => <VideoPlayerLoading /> },
);
const MEDIA_URL_STALE_MS = 50 * 60 * 1000;

export function PublicRecordingPlayer({
  token,
  recordingId,
  variant,
  processedPlayUrl,
  originalPlayUrl,
  mediaExpiresIn,
  mediaIssuedAtMs,
  onItemRefetch,
  markers,
  previewVttUrl,
  vttBlobUrl,
  videoRef,
  onTimeUpdate,
  onMediaMissing,
  onMarkerSeek,
  onEnded,
}: {
  token: string;
  recordingId: number;
  variant: "processed" | "original";
  processedPlayUrl?: string | null;
  originalPlayUrl?: string | null;
  mediaExpiresIn?: number | null;
  mediaIssuedAtMs: number;
  onItemRefetch: (variant: "processed" | "original") => Promise<string | null>;
  markers: VideoPlayerMarker[];
  previewVttUrl?: string | null;
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
  onMediaMissing?: () => void;
  onMarkerSeek?: (time: number, label: string) => void;
  onEnded?: () => void;
}) {
  const presetUrl = variant === "processed" ? processedPlayUrl : originalPlayUrl;
  const { data: media, dataUpdatedAt: mediaUpdatedAt, isLoading, refetch, error } = useQuery({
    queryKey: ["share-media", token, variant],
    queryFn: () => getShareMedia(token, variant),
    enabled: !presetUrl,
    staleTime: MEDIA_URL_STALE_MS,
    retry: false,
  });
  const resolvedUrl = presetUrl ?? media?.url;
  const refreshMedia = useCallback(async () => {
    if (presetUrl) return onItemRefetch(variant);
    const result = await refetch({ cancelRefetch: false });
    return result.isSuccess ? result.data?.url ?? null : null;
  }, [presetUrl, onItemRefetch, refetch, variant]);

  usePresignedMediaRefresh({
    expiresIn: presetUrl ? mediaExpiresIn : media?.expires_in,
    enabled: Boolean(resolvedUrl),
    url: resolvedUrl,
    issuedAtMs: presetUrl ? mediaIssuedAtMs : mediaUpdatedAt,
    onRefresh: refreshMedia,
  });

  useEffect(() => {
    if (httpStatus(error) === 404) onMediaMissing?.();
  }, [error, onMediaMissing]);

  if (!resolvedUrl && isLoading) return <VideoPlayerLoading />;

  if (!resolvedUrl) {
    return (
      <div
        role="status"
        className={cn(
          VIDEO_PLAYER_FRAME,
          "flex flex-col items-center justify-center gap-2 rounded-none bg-muted text-sm text-muted-foreground outline-none",
        )}
      >
        <VideoOff size={18} />
        <span>Video unavailable</span>
      </div>
    );
  }

  return (
    <VideoPlayer
      key={variant}
      ref={videoRef}
      src={resolvedUrl}
      resumeKey={recordingResumeKey(String(recordingId), variant)}
      onReload={refreshMedia}
      markers={markers}
      previewVttUrl={variant === "processed" ? previewVttUrl : null}
      vttBlobUrl={variant === "processed" ? vttBlobUrl : null}
      onTimeUpdate={onTimeUpdate}
      onMarkerSeek={onMarkerSeek}
      onEnded={onEnded}
      className="rounded-none outline-none"
    />
  );
}
