"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  Clock,
  Copy,
  VideoOff,
} from "lucide-react";

import {
  getPublicRecording,
  getShareMedia,
  getShareFileUrl,
  sendSharePageBeacon,
  type PublicRecordingResponse,
} from "@/api/share";
import { AIContentEditor, type TopicVersion } from "@/components/recordings/ai-content-editor";
import { resolveStorageUrl } from "@/api/client";
import { ArtefactList, SourceExtrasSection, sourceExtrasToArtefacts, type ArtefactItem, type ArtefactType } from "@/components/recordings/artefact-list";
import { ShareVideoDownloadButton } from "@/components/recordings/share-video-download-button";
import { TranscriptPanel } from "@/components/recordings/transcript-panel";
import { type VideoPlayerMarker } from "@/components/ui/video-player";
import { VIDEO_PLAYER_FRAME, VideoPlayerLoading } from "@/components/ui/video-player-frame";
import { CollapsibleCard } from "@/components/ui/section-card";
import { COMPANION_BODY_PINNED, COMPANION_TABS_ROW, WATCH_BELOW, WatchStage } from "@/components/ui/watch-stage";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { FormattedText } from "@/components/ui/formatted-text";
import { cn, formatDate, formatDuration, httpStatus, scrollPlayerIntoView } from "@/lib/utils";
import { lastIndexAtOrBefore } from "@/lib/playlist-playable";
import { recordingResumeKey } from "@/lib/video-resume";
import { AgeRatingBadge } from "@/components/ui/age-rating-badge";
import {
  COPY_LINK_CHIP,
  COPY_LINK_CHIP_COPIED,
  COPY_LINK_CHIP_IDLE,
} from "@/components/share/public-share-header";
import { usePresignedMediaRefresh } from "@/hooks/use-presigned-media";
import { useShareEngagement } from "@/hooks/use-share-engagement";
import { useShareVtt } from "@/hooks/use-share-vtt";
import { useWatchTheater } from "@/hooks/use-watch-theater";
import type { ChapterSeekSource } from "@/lib/share-engagement";
import { WatchVideoVariantChrome } from "@/components/ui/watch-video-variant-chrome";

const VideoPlayer = dynamic(
  () => import("@/components/ui/video-player").then((m) => m.VideoPlayer),
  {
    ssr: false,
    loading: () => <VideoPlayerLoading />,
  },
);
const MEDIA_URL_STALE_MS = 50 * 60 * 1000;

const PAGE_SHELL = "mx-auto w-full max-w-[110rem] px-4 sm:px-6 lg:px-8";
const PAGE_MAIN = cn(PAGE_SHELL, "py-4 sm:py-8");
const PAGE_HEADER_INNER = cn(PAGE_SHELL, "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3 sm:py-4");

type SidePanelTab = "topics" | "transcript";

function ShareVideoPlayer({
  token,
  recordingId,
  variant,
  processedPlayUrl,
  originalPlayUrl,
  mediaExpiresIn,
  onItemRefetch,
  markers,
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
  onItemRefetch: () => void;
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
  onMediaMissing?: () => void;
  onMarkerSeek?: (time: number, label: string) => void;
  onEnded?: () => void;
}) {
  const presetUrl = variant === "processed" ? processedPlayUrl : originalPlayUrl;
  const { data: videoUrl, isLoading, isError, refetch, error } = useQuery({
    queryKey: ["share-media", token, variant],
    queryFn: async () => {
      const res = await getShareMedia(token, variant);
      return res.url;
    },
    enabled: !presetUrl,
    staleTime: MEDIA_URL_STALE_MS,
    retry: false,
  });
  const resolvedUrl = presetUrl ?? videoUrl;

  usePresignedMediaRefresh({
    expiresIn: mediaExpiresIn,
    enabled: Boolean(presetUrl),
    onRefresh: onItemRefetch,
  });

  useEffect(() => {
    if (httpStatus(error) === 404) onMediaMissing?.();
  }, [error, onMediaMissing]);

  if (!presetUrl && isLoading) {
    return <VideoPlayerLoading />;
  }

  if ((!presetUrl && isError) || !resolvedUrl) {
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
      onReload={() => {
        onItemRefetch();
        void refetch();
      }}
      markers={markers}
      vttBlobUrl={variant === "processed" ? vttBlobUrl : null}
      onTimeUpdate={onTimeUpdate}
      onMarkerSeek={onMarkerSeek}
      onEnded={onEnded}
      className="rounded-none outline-none"
    />
  );
}

export function ShareView({ token }: { token: string }) {
  const fromSlug = useSearchParams().get("from");
  const engagementPath = useMemo(() => {
    const q = fromSlug ? `?from=${encodeURIComponent(fromSlug)}` : "";
    return `/share/${token}/engagement${q}`;
  }, [token, fromSlug]);
  const { track, flush } = useShareEngagement(engagementPath);
  const {
    data: recording,
    error,
    isPending,
    refetch,
  } = useQuery<PublicRecordingResponse>({
    queryKey: ["share-recording", token],
    queryFn: () => getPublicRecording(token, "player"),
    retry: false,
  });

  useEffect(() => {
    void sendSharePageBeacon(token).catch(() => {});
  }, [token]);

  const [activeChapterIdx, setActiveChapterIdx] = useState(-1);
  const [activeCueIdx, setActiveCueIdx] = useState(-1);
  const [videoVariant, setVideoVariant] = useState<"processed" | "original">("processed");
  const [sidePanelTab, setSidePanelTab] = useState<SidePanelTab>("topics");
  const onCompanionTab = useCallback((tab: SidePanelTab) => {
    setSidePanelTab(tab);
    scrollPlayerIntoView();
  }, []);
  const [copied, setCopied] = useState(false);
  const { theater, setTheater } = useWatchTheater();
  const videoRef = useRef<HTMLVideoElement>(null);
  const durationFallbackRef = useRef(0);
  const positionRef = useRef(0);
  const companionPanelId = useId();

  const handleCopyLink = useCallback(() => {
    void navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, []);

  const handleMediaMissing = useCallback(() => {
    void refetch();
  }, [refetch]);

  const vttFallback = recording?.available_files?.includes("vtt")
    ? getShareFileUrl(token, "vtt", true)
    : null;
  const { vttBlobUrl, transcript } = useShareVtt({
    enabled: Boolean(recording?.vtt_url || vttFallback),
    vttUrl: recording?.vtt_url,
    fallbackUrl: vttFallback,
  });

  const refetchPlayer = useCallback(() => {
    void refetch();
  }, [refetch]);

  const topicTimestamps = useMemo(
    () => (Array.isArray(recording?.topic_timestamps) ? (recording!.topic_timestamps as { topic: string; start: number }[]) : []),
    [recording],
  );
  const mainTopics = useMemo(
    () => (Array.isArray(recording?.main_topics) ? (recording!.main_topics as string[]) : []),
    [recording],
  );

  const topicVersion: TopicVersion | null = recording
    ? {
        main_topics: mainTopics,
        topic_timestamps: topicTimestamps,
        summary: recording.summary ?? undefined,
        questions: recording.questions ?? undefined,
      }
    : null;

  const hasTopicsPanel = topicTimestamps.length > 0;
  const hasTranscript = transcript.length > 0;
  const hasExtraContent = !!(
    topicVersion?.summary ||
    topicVersion?.questions?.length ||
    topicVersion?.main_topics?.length
  );

  const markers: VideoPlayerMarker[] = topicTimestamps.map((t) => ({ time: t.start, label: t.topic }));

  const handleTimeUpdate = useCallback(
    (time: number) => {
      positionRef.current = time;
      setActiveChapterIdx(lastIndexAtOrBefore(topicTimestamps, time));
      setActiveCueIdx(lastIndexAtOrBefore(transcript, time));
    },
    [topicTimestamps, transcript],
  );

  const handleSeek = useCallback((time: number) => {
    positionRef.current = time;
    if (videoRef.current) videoRef.current.currentTime = time;
  }, []);

  const chapterLabelAt = useCallback(
    (time: number) => {
      const idx = lastIndexAtOrBefore(topicTimestamps, time);
      if (idx >= 0) return topicTimestamps[idx]!.topic;
      return `${Math.floor(time)}s`;
    },
    [topicTimestamps],
  );

  const seekWithEngagement = useCallback(
    (time: number, source: ChapterSeekSource) => {
      handleSeek(time);
      track("chapter_seek", {
        source,
        time_sec: Math.floor(time),
        label: chapterLabelAt(time),
      });
    },
    [chapterLabelAt, handleSeek, track],
  );

  useEffect(() => {
    if (recording?.duration) {
      durationFallbackRef.current = recording.duration;
    }
  }, [recording?.duration]);

  useEffect(() => {
    const recordingId = recording?.id;
    if (!recordingId) return;
    positionRef.current = 0;
    const snapPlayback = () => {
      const el = videoRef.current;
      if (!el) return;
      if (Number.isFinite(el.currentTime)) positionRef.current = el.currentTime;
      if (Number.isFinite(el.duration) && el.duration > 0) {
        durationFallbackRef.current = el.duration;
      }
    };
    snapPlayback();
    const timer = window.setInterval(snapPlayback, 250);
    return () => {
      window.clearInterval(timer);
      const duration = Math.floor(durationFallbackRef.current);
      const position = Math.floor(positionRef.current);
      if (duration > 0) {
        track("watch_exit", { position_sec: Math.min(position, duration), duration_sec: duration });
        flush();
      }
    };
  }, [recording?.id, track, flush]);

  const missing = httpStatus(error) === 404;
  if (missing) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center bg-background px-6">
        <div className="w-full max-w-md">
          <ErrorState
            title="Link not found"
            description="This share link has been revoked, or it never existed."
          />
        </div>
      </div>
    );
  }

  if (error && !recording) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center bg-background px-6">
        <div className="w-full max-w-md">
          <ErrorState
            title="Unable to load this recording"
            description="Check your connection and try again."
            onRetry={() => void refetch()}
          />
        </div>
      </div>
    );
  }

  if (isPending || !recording) {
    return (
      <div className="bg-background">
        <header className="border-b border-border bg-card">
          <div className={PAGE_HEADER_INNER}>
            <div className="flex items-center gap-3">
              <Skeleton className="h-6 w-6 rounded" />
              <Skeleton className="h-4 w-10" />
            </div>
            <Skeleton className="h-4 w-36" />
          </div>
        </header>
        <main className={PAGE_MAIN}>
          <WatchStage
            player={<div className={cn(VIDEO_PLAYER_FRAME, "animate-pulse")} />}
            title={<Skeleton className="h-7 w-2/3 sm:w-1/2" />}
          />
        </main>
      </div>
    );
  }

  const hasVideo = recording.has_processed_video || recording.has_original_video;
  const bothVariants = Boolean(
    recording.has_processed_video && recording.has_original_video && recording.original_play_url,
  );
  const currentVariant: "processed" | "original" = recording.has_processed_video
    ? bothVariants
      ? videoVariant
      : "processed"
    : "original";

  const allowVideo = recording.allow_video_download !== false;
  const allowFiles = recording.allow_files_download !== false;
  const artefacts: ArtefactItem[] = recording.available_files.map((ft) => ({
    type: ft as ArtefactType,
    href: allowFiles ? getShareFileUrl(token, ft) : undefined,
    locked: !allowFiles,
  }));
  const sourceExtras = allowFiles
    ? sourceExtrasToArtefacts(recording.source_extras, resolveStorageUrl)
    : [];

  const onProcessedTimeline = currentVariant === "processed";

  const sidePanelTabs: TabItem<SidePanelTab>[] = [];
  if (hasTopicsPanel) sidePanelTabs.push({ value: "topics", label: "Chapters" });
  if (hasTranscript) sidePanelTabs.push({ value: "transcript", label: "Transcript" });
  const showCompanionTabs = sidePanelTabs.length > 1;
  const showCompanionCol = sidePanelTabs.length > 0;
  const defaultSidePanelTab: SidePanelTab = hasTopicsPanel ? "topics" : "transcript";
  const activeSidePanelTab = sidePanelTabs.some((t) => t.value === sidePanelTab)
    ? sidePanelTab
    : defaultSidePanelTab;

  const companionBody =
    activeSidePanelTab === "topics" && hasTopicsPanel && topicVersion ? (
      <AIContentEditor
        recordingId={recording.id}
        version={topicVersion}
        onUpdated={() => {}}
        onSeek={(time) => seekWithEngagement(time, "sidebar")}
        activeChapterIdx={activeChapterIdx}
        readOnly
        sections={["chapters"]}
        embeddedInPanel
      />
    ) : activeSidePanelTab === "transcript" && hasTranscript ? (
      <TranscriptPanel
        cues={transcript}
        activeIdx={activeCueIdx}
        onSeek={(time) => seekWithEngagement(time, "transcript")}
        listClassName="min-h-0 flex-1 overflow-y-auto"
      />
    ) : null;

  const playerNode = (
    <ShareVideoPlayer
      token={token}
      recordingId={recording.id}
      variant={currentVariant}
      processedPlayUrl={recording.play_url}
      originalPlayUrl={recording.original_play_url}
      mediaExpiresIn={recording.media_expires_in}
      onItemRefetch={refetchPlayer}
      markers={onProcessedTimeline ? markers : []}
      vttBlobUrl={onProcessedTimeline ? vttBlobUrl : null}
      videoRef={videoRef}
      onTimeUpdate={handleTimeUpdate}
      onMediaMissing={handleMediaMissing}
      onMarkerSeek={(time, label) => {
        handleSeek(time);
        track("chapter_seek", {
          source: "marker",
          time_sec: Math.floor(time),
          label,
        });
      }}
      onEnded={() => track("playback_complete", {})}
    />
  );

  const hasFiles = artefacts.length > 0 || sourceExtras.length > 0 || hasVideo;

  const companion = showCompanionCol ? (
    <>
      {showCompanionTabs ? (
        <div className={COMPANION_TABS_ROW}>
          <Tabs
            items={sidePanelTabs}
            value={activeSidePanelTab}
            onChange={onCompanionTab}
            label="Companion content"
            hidePanel
            idPrefix={companionPanelId}
            panelId={companionPanelId}
            tablistClassName="mb-0 -my-0"
          >
            {null}
          </Tabs>
        </div>
      ) : (
        <h2 className="shrink-0 border-b border-border px-5 pb-3 pt-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {sidePanelTabs[0]?.label}
        </h2>
      )}
      {showCompanionTabs ? (
        <div
          role="tabpanel"
          id={companionPanelId}
          aria-labelledby={`${companionPanelId}-tab-${activeSidePanelTab}`}
          className={COMPANION_BODY_PINNED}
        >
          {companionBody}
        </div>
      ) : (
        <div className={COMPANION_BODY_PINNED}>{companionBody}</div>
      )}
    </>
  ) : undefined;

  return (
    <div className="bg-background">
      <header className="border-b border-border bg-card">
        <div className={PAGE_HEADER_INNER}>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo_symb.svg" alt="" aria-hidden="true" className="h-6 w-6" />
              <span className="text-sm font-semibold text-foreground">LEAP</span>
            </span>
            <AgeRatingBadge />
          </div>
          <button
            type="button"
            onClick={handleCopyLink}
            className={cn(COPY_LINK_CHIP, copied ? COPY_LINK_CHIP_COPIED : COPY_LINK_CHIP_IDLE)}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? "Copied" : "Copy link"}
          </button>
          <span role="status" className="sr-only">
            {copied ? "Link copied to clipboard" : ""}
          </span>
        </div>
      </header>

      <main className={PAGE_MAIN}>
        <WatchStage
            player={playerNode}
            title={
              <div>
                {fromSlug && (
                  <Link href={`/c/${fromSlug}`} className="mb-2 inline-flex text-sm text-muted-foreground hover:text-foreground">
                    ← {fromSlug}
                  </Link>
                )}
                <h1 className="text-xl font-semibold tracking-tight break-words text-foreground sm:text-2xl">
                  {recording.title || recording.display_name}
                </h1>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                  <span className="flex items-center gap-2">
                    <Clock size={13} />
                    <span>{formatDate(recording.start_time)}</span>
                    {recording.duration > 0 && (
                      <>
                        <span aria-hidden="true" className="text-border">·</span>
                        <span>{formatDuration(recording.duration) ?? "—"}</span>
                      </>
                    )}
                  </span>
                </div>
                <WatchVideoVariantChrome
                  bothVariants={bothVariants}
                  variant={currentVariant}
                  onVariantChange={setVideoVariant}
                  showTimelineHint={!onProcessedTimeline && (hasTopicsPanel || hasTranscript)}
                />
              </div>
            }
            theater={theater}
            onTheaterChange={setTheater}
            companion={companion}
            below={
              <div className={WATCH_BELOW}>
                {hasExtraContent && topicVersion && (
                  <CollapsibleCard title="Summary & questions">
                    <AIContentEditor
                      recordingId={recording.id}
                      version={topicVersion}
                      onUpdated={() => {}}
                      readOnly
                      sections={["topics", "summary", "questions"]}
                    />
                  </CollapsibleCard>
                )}

                {hasFiles && (
                  <CollapsibleCard title="Files">
                    <div className="flex flex-col gap-2">
                      {hasVideo && (
                        <ShareVideoDownloadButton
                          locked={!allowVideo}
                          download={() => getShareMedia(token, currentVariant, true)}
                        />
                      )}
                      <ArtefactList items={artefacts} />
                      <SourceExtrasSection items={sourceExtras} />
                    </div>
                  </CollapsibleCard>
                )}

                {recording.description && (
                  <CollapsibleCard title="Created Overview" defaultOpen={false}>
                    <FormattedText
                      text={recording.description}
                      className="text-sm leading-relaxed text-foreground"
                    />
                  </CollapsibleCard>
                )}
              </div>
            }
          />
      </main>
    </div>
  );
}
