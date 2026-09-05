"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
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
import { ArtefactList, type ArtefactItem, type ArtefactType } from "@/components/recordings/artefact-list";
import { ShareVideoDownloadButton } from "@/components/recordings/share-video-download-button";
import { TranscriptPanel, parseVtt, type TranscriptCue } from "@/components/recordings/transcript-panel";
import { type VideoPlayerMarker } from "@/components/ui/video-player";
import { VIDEO_PLAYER_FRAME, VideoPlayerLoading } from "@/components/ui/video-player-frame";
import { CollapsibleCard, CARD_SHELL } from "@/components/ui/section-card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { SegmentedField } from "@/components/ui/segmented-field";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { cn, formatDate, formatDuration, httpStatus } from "@/lib/utils";
import { recordingResumeKey } from "@/lib/video-resume";

const VideoPlayer = dynamic(
  () => import("@/components/ui/video-player").then((m) => m.VideoPlayer),
  {
    ssr: false,
    loading: () => <VideoPlayerLoading />,
  },
);
const MEDIA_URL_STALE_MS = 50 * 60 * 1000;

const PAGE_SHELL = "mx-auto w-full max-w-[110rem] px-4 sm:px-8";
const PAGE_MAIN = cn(PAGE_SHELL, "py-4 sm:py-8");
const PAGE_HEADER_INNER = cn(PAGE_SHELL, "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3 sm:py-4");
const WATCH_GRID =
  "grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start xl:grid-cols-[minmax(0,1fr)_26rem] 2xl:grid-cols-[minmax(0,1fr)_28rem]";
const COMPANION_COL = "min-w-0 lg:sticky lg:top-6 lg:self-start";
const COMPANION_PANEL = cn(CARD_SHELL, "flex min-h-0 flex-col overflow-hidden");
const COMPANION_SHELL = "flex min-h-0 flex-1 flex-col overflow-hidden";
const COMPANION_TOPIC = "shrink-0 border-b border-border px-5 pb-3 pt-4 text-base font-semibold leading-snug break-words text-foreground";
const COMPANION_TABS_ROW = "shrink-0 border-b border-border px-5 pb-3 pt-3";
const COMPANION_SECTION_LABEL =
  "shrink-0 border-b border-border px-5 pb-3 pt-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground";
const COMPANION_BODY = "min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-5 pt-4";

const VIDEO_VARIANT_OPTIONS = [
  { value: "processed" as const, label: "Processed" },
  { value: "original" as const, label: "Original" },
];

type SidePanelTab = "topics" | "transcript";

function lastIndexAtOrBefore(items: { start: number }[], time: number): number {
  for (let i = items.length - 1; i >= 0; i--) {
    if (time >= items[i].start) return i;
  }
  return -1;
}

function ShareVideoPlayer({
  token,
  recordingId,
  variant,
  markers,
  vttBlobUrl,
  videoRef,
  onTimeUpdate,
  onMediaMissing,
}: {
  token: string;
  recordingId: number;
  variant: "processed" | "original";
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
  onMediaMissing?: () => void;
}) {
  const { data: videoUrl, isLoading, isError, refetch, error } = useQuery({
    queryKey: ["share-media", token, variant],
    queryFn: async () => {
      const res = await getShareMedia(token, variant);
      return res.url;
    },
    staleTime: MEDIA_URL_STALE_MS,
    retry: false,
  });

  useEffect(() => {
    if (httpStatus(error) === 404) onMediaMissing?.();
  }, [error, onMediaMissing]);

  if (isLoading) {
    return <VideoPlayerLoading />;
  }

  if (isError || !videoUrl) {
    return (
      <div
        role="status"
        className={cn(
          VIDEO_PLAYER_FRAME,
          "flex flex-col items-center justify-center gap-2 bg-muted text-sm text-muted-foreground",
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
      src={videoUrl}
      resumeKey={recordingResumeKey(String(recordingId), variant)}
      onReload={() => refetch()}
      markers={markers}
      vttBlobUrl={variant === "processed" ? vttBlobUrl : null}
      onTimeUpdate={onTimeUpdate}
    />
  );
}

export function ShareView({ token }: { token: string }) {
  const {
    data: recording,
    error,
    isPending,
    refetch,
  } = useQuery<PublicRecordingResponse>({
    queryKey: ["share-recording", token],
    queryFn: () => getPublicRecording(token),
    retry: false,
  });

  useQuery({
    queryKey: ["share-media", token, "processed"],
    queryFn: async () => (await getShareMedia(token, "processed")).url,
    staleTime: MEDIA_URL_STALE_MS,
    retry: false,
  });

  useEffect(() => {
    void sendSharePageBeacon(token).catch(() => {});
  }, [token]);

  const [activeChapterIdx, setActiveChapterIdx] = useState(-1);
  const [activeCueIdx, setActiveCueIdx] = useState(-1);
  const [vttBlobUrl, setVttBlobUrl] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptCue[]>([]);
  const [videoVariant, setVideoVariant] = useState<"processed" | "original">("processed");
  const [sidePanelTab, setSidePanelTab] = useState<SidePanelTab>("topics");
  const [copied, setCopied] = useState(false);
  const videoColRef = useRef<HTMLDivElement>(null);
  const [companionMaxH, setCompanionMaxH] = useState<number>();
  const videoRef = useRef<HTMLVideoElement>(null);
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

  useEffect(() => {
    if (!recording?.available_files.includes("vtt")) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    fetch(getShareFileUrl(token, "vtt", true))
      .then((r) => r.text())
      .then((text) => {
        if (cancelled) return;
        setTranscript(parseVtt(text));
        objectUrl = URL.createObjectURL(new Blob([text], { type: "text/vtt" }));
        setVttBlobUrl(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setVttBlobUrl(null);
      setTranscript([]);
    };
  }, [token, recording?.available_files]);

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

  const hasTopicsPanel = !!(mainTopics.length || topicTimestamps.length);
  const hasTranscript = transcript.length > 0;
  const hasExtraContent = !!(topicVersion?.summary || topicVersion?.questions?.length);

  const markers: VideoPlayerMarker[] = topicTimestamps.map((t) => ({ time: t.start, label: t.topic }));

  const handleTimeUpdate = useCallback(
    (time: number) => {
      setActiveChapterIdx(lastIndexAtOrBefore(topicTimestamps, time));
      setActiveCueIdx(lastIndexAtOrBefore(transcript, time));
    },
    [topicTimestamps, transcript],
  );

  const handleSeek = useCallback((time: number) => {
    if (videoRef.current) videoRef.current.currentTime = time;
  }, []);

  const watchVariant: "processed" | "original" =
    recording?.has_processed_video ? videoVariant : "original";
  const showCompanionColumn =
    !!recording &&
    watchVariant === "processed" &&
    (hasTopicsPanel || hasTranscript);

  useEffect(() => {
    if (!showCompanionColumn) return;
    const el = videoColRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;

    const syncHeight = () => {
      setCompanionMaxH(el.getBoundingClientRect().height);
    };

    syncHeight();
    const raf = window.requestAnimationFrame(syncHeight);
    const observer = new ResizeObserver(syncHeight);
    observer.observe(el);
    window.addEventListener("resize", syncHeight);
    return () => {
      window.cancelAnimationFrame(raf);
      observer.disconnect();
      window.removeEventListener("resize", syncHeight);
    };
  }, [
    recording?.id,
    videoVariant,
    showCompanionColumn,
    recording?.has_processed_video,
    recording?.has_original_video,
  ]);

  const missing = httpStatus(error) === 404;
  if (missing) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6">
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
      <div className="flex min-h-screen items-center justify-center bg-background px-6">
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
      <div className="min-h-screen bg-background">
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
          <div className="space-y-5">
            <Skeleton className="h-7 w-2/3 sm:w-1/2" />
            <div className={cn(VIDEO_PLAYER_FRAME, "animate-pulse")} />
          </div>
        </main>
      </div>
    );
  }

  const hasVideo = recording.has_processed_video || recording.has_original_video;
  const bothVariants = recording.has_processed_video && recording.has_original_video;
  const currentVariant: "processed" | "original" = recording.has_processed_video ? videoVariant : "original";

  const allowVideo = recording.allow_video_download !== false;
  const allowFiles = recording.allow_files_download !== false;
  const artefacts: ArtefactItem[] = allowFiles
    ? recording.available_files.map((ft) => ({
        type: ft as ArtefactType,
        href: getShareFileUrl(token, ft),
      }))
    : [];

  const onProcessedTimeline = currentVariant === "processed";
  const showCompanion = onProcessedTimeline && (hasTopicsPanel || hasTranscript);

  const sidePanelTabs: TabItem<SidePanelTab>[] = [];
  if (hasTopicsPanel) sidePanelTabs.push({ value: "topics", label: "Topics" });
  if (hasTranscript) sidePanelTabs.push({ value: "transcript", label: "Transcript" });
  const showCompanionTabs = sidePanelTabs.length > 1;
  const showCompanionCol = showCompanion && sidePanelTabs.length > 0;
  const defaultSidePanelTab: SidePanelTab = hasTopicsPanel ? "topics" : "transcript";
  const activeSidePanelTab = sidePanelTabs.some((t) => t.value === sidePanelTab)
    ? sidePanelTab
    : defaultSidePanelTab;
  const companionTopicTitle = mainTopics[0] ?? null;

  const companionBody =
    activeSidePanelTab === "topics" && hasTopicsPanel && topicVersion ? (
      <AIContentEditor
        recordingId={recording.id}
        version={topicVersion}
        onUpdated={() => {}}
        onSeek={handleSeek}
        activeChapterIdx={activeChapterIdx}
        readOnly
        sections={["chapters"]}
        embeddedInPanel
      />
    ) : activeSidePanelTab === "transcript" && hasTranscript ? (
      <TranscriptPanel
        cues={transcript}
        activeIdx={activeCueIdx}
        onSeek={handleSeek}
        listClassName="max-h-none overflow-visible"
      />
    ) : null;

  const playerNode = (
    <ShareVideoPlayer
      token={token}
      recordingId={recording.id}
      variant={currentVariant}
      markers={onProcessedTimeline ? markers : []}
      vttBlobUrl={onProcessedTimeline ? vttBlobUrl : null}
      videoRef={videoRef}
      onTimeUpdate={handleTimeUpdate}
      onMediaMissing={handleMediaMissing}
    />
  );

  const hasFiles = artefacts.length > 0 || (hasVideo && allowVideo);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card">
        <div className={PAGE_HEADER_INNER}>
          <Link
            href="/"
            className="flex items-center gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo_symb.svg" alt="" aria-hidden="true" className="h-6 w-6" />
            <span className="text-sm font-semibold text-foreground">LEAP</span>
          </Link>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Clock size={13} />
              <span>{formatDate(recording.start_time)}</span>
              {recording.duration > 0 && (
                <>
                  <span aria-hidden="true" className="text-border">·</span>
                  <span>{formatDuration(recording.duration) ?? "—"}</span>
                </>
              )}
            </div>
            <button
              type="button"
              onClick={handleCopyLink}
              className={cn(
                "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                copied
                  ? "border-success-fg/40 bg-success-fg/10 text-success-fg"
                  : "border-border bg-card text-secondary-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
              )}
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? "Copied" : "Copy link"}
            </button>
            <span role="status" className="sr-only">
              {copied ? "Link copied to clipboard" : ""}
            </span>
          </div>
        </div>
      </header>

      <main className={PAGE_MAIN}>
        <div className="space-y-5 sm:space-y-8">
          <div className={showCompanionCol ? WATCH_GRID : undefined}>
            <div ref={videoColRef} className="min-w-0">
              <h1 className="mb-5 text-xl font-semibold tracking-tight break-words text-foreground sm:text-2xl">
                {recording.display_name}
              </h1>
              {bothVariants && (
                <div className="mb-5 space-y-2">
                  <SegmentedField
                    label="Video source"
                    labelHidden
                    options={VIDEO_VARIANT_OPTIONS}
                    value={currentVariant}
                    onChange={setVideoVariant}
                  />
                  {!onProcessedTimeline && (hasTopicsPanel || hasTranscript) && (
                    <p className="text-xs text-muted-foreground">
                      Topics and transcript follow the processed video.
                    </p>
                  )}
                </div>
              )}
              <div
                className={cn(
                  CARD_SHELL,
                  "overflow-hidden",
                  "max-lg:p-0 max-lg:[&_.rounded-xl]:rounded-2xl max-lg:[&_.outline]:outline-none",
                  "lg:p-3",
                )}
              >
                {playerNode}
              </div>
            </div>

            {showCompanionCol && (
              <div className={COMPANION_COL}>
                <div
                  className={cn(COMPANION_PANEL, companionMaxH && "lg:h-[var(--companion-h)]")}
                  style={companionMaxH ? { ["--companion-h" as string]: `${companionMaxH}px` } : undefined}
                >
                  <div className={COMPANION_SHELL}>
                    {companionTopicTitle && (
                      <p className={COMPANION_TOPIC}>{companionTopicTitle}</p>
                    )}
                    {showCompanionTabs ? (
                      <div className={COMPANION_TABS_ROW}>
                        <Tabs
                          items={sidePanelTabs}
                          value={activeSidePanelTab}
                          onChange={setSidePanelTab}
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
                      !companionTopicTitle && (
                        <h2 className={COMPANION_SECTION_LABEL}>{sidePanelTabs[0]?.label}</h2>
                      )
                    )}
                    {showCompanionTabs ? (
                      <div
                        role="tabpanel"
                        id={companionPanelId}
                        aria-labelledby={`${companionPanelId}-tab-${activeSidePanelTab}`}
                        className={COMPANION_BODY}
                      >
                        {companionBody}
                      </div>
                    ) : (
                      <div className={COMPANION_BODY}>{companionBody}</div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-6">
            {onProcessedTimeline && hasExtraContent && topicVersion && (
              <CollapsibleCard title="Extra content" defaultOpen={false}>
                <AIContentEditor
                  recordingId={recording.id}
                  version={topicVersion}
                  onUpdated={() => {}}
                  readOnly
                  sections={["summary", "questions"]}
                />
              </CollapsibleCard>
            )}

            {hasFiles && (
              <CollapsibleCard title="Files" defaultOpen={false}>
                <div className="flex flex-col gap-2">
                  {hasVideo && allowVideo && (
                    <ShareVideoDownloadButton download={() => getShareMedia(token, currentVariant, true)} />
                  )}
                  <ArtefactList items={artefacts} />
                </div>
              </CollapsibleCard>
            )}

            {recording.description && (
              <CollapsibleCard title="Overview" defaultOpen={false}>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                  {recording.description}
                </p>
              </CollapsibleCard>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
