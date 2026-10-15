"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronUp, ExternalLink, ListVideo } from "lucide-react";
import { getPublicRecording, getShareFileUrl, sendSharePageBeacon, type PublicRecordingResponse } from "@/api/share";
import { PublicRecordingPlayer } from "@/components/share/public-recording-player";
import { PreviewFrameImage } from "@/components/ui/preview-frame";
import type { VideoPlayerMarker } from "@/components/ui/video-player";
import { useShareEngagement } from "@/hooks/use-share-engagement";
import { useShareVtt } from "@/hooks/use-share-vtt";
import { useVideoPreviews, type PreviewFrame } from "@/hooks/use-video-previews";
import { cn, formatDurationCompact, httpStatus } from "@/lib/utils";

const EMBED_SHELL = "mx-auto max-w-3xl overflow-hidden rounded-xl border border-border bg-card";

function EmbedChapters({
  markers,
  frames,
  videoRef,
  onSeek,
}: {
  markers: VideoPlayerMarker[];
  frames?: PreviewFrame[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onSeek: (marker: VideoPlayerMarker) => void;
}) {
  const [open, setOpen] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const panelId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const focus = requestAnimationFrame(() => {
      const buttons = panelRef.current?.querySelectorAll<HTMLButtonElement>("button");
      buttons?.[currentIndex]?.focus();
    });
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onFocusIn(event: FocusEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setOpen(false);
      triggerRef.current?.focus();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      cancelAnimationFrame(focus);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, currentIndex]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? panelId : undefined}
        onClick={() => {
          if (!open) {
            const time = videoRef.current?.currentTime ?? 0;
            setCurrentIndex(Math.max(0, markers.findLastIndex((marker) => marker.time <= time)));
          }
          setOpen(!open);
        }}
        className="inline-flex shrink-0 items-center gap-1 rounded-lg px-1.5 py-1 font-medium text-secondary-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
      >
        <ListVideo size={13} aria-hidden />
        Chapters
        <ChevronUp size={12} aria-hidden className={open ? "" : "rotate-180"} />
      </button>
      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label="Chapters"
          className="absolute bottom-[calc(100%+0.5rem)] right-2 z-30 w-[min(20rem,calc(100vw-1rem))] overflow-hidden rounded-xl border border-border bg-card shadow-xl"
        >
          <p className="border-b border-border px-3 py-2 text-xs font-semibold text-foreground">Chapters</p>
          <div className="max-h-[min(15rem,calc(56.25vw-4rem),calc(100dvh-4rem))] overflow-y-auto overscroll-contain">
            {markers.map((marker, index) => (
              <button
                key={`${marker.time}-${index}`}
                type="button"
                aria-current={index === currentIndex ? "true" : undefined}
                onClick={() => {
                  onSeek(marker);
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
                className={cn(
                  "flex w-full items-center gap-2 border-b border-border/60 px-3 py-2 text-left last:border-b-0 hover:bg-muted focus-visible:bg-muted focus-visible:outline-none",
                  index === currentIndex && "bg-primary/5",
                )}
              >
                <PreviewFrameImage frames={frames} time={marker.time} />
                <span className={cn("min-w-0 flex-1 truncate text-xs font-medium", index === currentIndex ? "text-primary" : "text-foreground")} title={marker.label}>
                  {marker.label}
                </span>
                <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
                  {formatDurationCompact(marker.time) ?? "0:00"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export function EmbedView({ token }: { token: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const previews = useVideoPreviews(`/share/${token}`);
  const { track } = useShareEngagement(`/share/${token}/engagement`);
  const { data: recording, dataUpdatedAt, isPending, error, refetch } = useQuery<PublicRecordingResponse>({
    queryKey: ["share-recording", token, "embed"],
    queryFn: () => getPublicRecording(token, "embed"),
    retry: false,
  });
  // The embed response skips the file inventory; keep the API subtitle fallback
  // for buckets that do not allow the browser to fetch a presigned VTT directly.
  const vttFallback = recording?.vtt_url ? getShareFileUrl(token, "vtt", true) : null;
  const { vttBlobUrl } = useShareVtt({
    enabled: Boolean(recording?.vtt_url || vttFallback),
    vttUrl: recording?.vtt_url,
    fallbackUrl: vttFallback,
  });

  useEffect(() => {
    void sendSharePageBeacon(token).catch(() => {});
  }, [token]);

  const markers = useMemo<VideoPlayerMarker[]>(() => {
    const topics = Array.isArray(recording?.topic_timestamps) ? recording.topic_timestamps : [];
    return topics
      .filter((item): item is { start: number; topic: string } =>
        typeof item === "object" && item !== null && typeof item.start === "number" && typeof item.topic === "string")
      .map((item) => ({ time: item.start, label: item.topic }))
      .sort((a, b) => a.time - b.time);
  }, [recording]);

  const refresh = useCallback(async () => {
    const result = await refetch({ cancelRefetch: false });
    return result.isSuccess ? result.data?.play_url ?? null : null;
  }, [refetch]);

  if (isPending) {
    return (
      <main className="min-h-screen bg-background">
        <div className={EMBED_SHELL}>
          <div className="aspect-video animate-pulse bg-muted" role="status" aria-label="Loading video" />
        </div>
      </main>
    );
  }
  if (error || !recording || !recording.has_processed_video) {
    return (
      <main className="min-h-screen bg-background text-muted-foreground">
        <div className={`${EMBED_SHELL} flex aspect-video items-center justify-center p-4 text-center text-sm`} role="status">
          {httpStatus(error) === 404 ? "This video link is unavailable." : "Video unavailable."}
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className={EMBED_SHELL}>
        <PublicRecordingPlayer
          token={token}
          recordingId={recording.id}
          variant="processed"
          processedPlayUrl={recording.play_url}
          mediaExpiresIn={recording.media_expires_in}
          mediaIssuedAtMs={dataUpdatedAt}
          onItemRefetch={refresh}
          markers={markers}
          previewVttUrl={previews?.url}
          vttBlobUrl={vttBlobUrl}
          videoRef={videoRef}
          onMarkerSeek={(time, label) => track("chapter_seek", { source: "marker", time_sec: Math.floor(time), label })}
          onEnded={() => track("playback_complete", {})}
        />
        <div className="relative flex min-h-8 items-center gap-2 border-t border-border px-2 text-xs sm:px-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo_symb.svg" alt="" aria-hidden="true" className="size-4 shrink-0" />
          <span className="min-w-0 flex-1 truncate font-medium" title={recording.title || recording.display_name}>
            {recording.title || recording.display_name}
          </span>
          {markers.length > 0 && (
            <EmbedChapters
              markers={markers}
              frames={previews?.frames}
              videoRef={videoRef}
              onSeek={(marker) => {
                if (videoRef.current) videoRef.current.currentTime = marker.time;
                track("chapter_seek", { source: "sidebar", time_sec: Math.floor(marker.time), label: marker.label });
              }}
            />
          )}
          <a
            href={`/share/${token}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex shrink-0 items-center gap-1 rounded-lg px-1.5 py-1 font-medium text-primary hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            Open in LEAP <ExternalLink size={12} aria-hidden />
          </a>
        </div>
      </div>
    </main>
  );
}
