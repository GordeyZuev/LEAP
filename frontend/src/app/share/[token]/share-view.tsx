"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
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
import { TranscriptPanel, parseVtt, type TranscriptCue } from "@/components/recordings/transcript-panel";
import { type VideoPlayerMarker } from "@/components/ui/video-player";
import { VIDEO_PLAYER_FRAME, VideoPlayerLoading } from "@/components/ui/video-player-frame";
import { CollapsibleCard } from "@/components/ui/section-card";
import { COMPANION_BODY_PINNED, COMPANION_TABS_ROW, WATCH_BELOW, WatchStage } from "@/components/ui/watch-stage";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { VideoVariantSwitch } from "@/components/ui/video-variant-switch";
import { FormattedText } from "@/components/ui/formatted-text";
import { cn, formatDate, formatDuration, httpStatus, scrollPlayerIntoView } from "@/lib/utils";
import { lastIndexAtOrBefore } from "@/lib/playlist-playable";
import { recordingResumeKey } from "@/lib/video-resume";
import { AgeRatingBadge } from "@/components/ui/age-rating-badge";
import { useWatchTheater } from "@/hooks/use-watch-theater";

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
  markers,
  vttBlobUrl,
  videoRef,
  onTimeUpdate,
  onMediaMissing,
}: {
  token: string;
  recordingId: number;
  variant: "processed" | "original";
  processedPlayUrl?: string | null;
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
  onMediaMissing?: () => void;
}) {
  const presetUrl = variant === "processed" ? processedPlayUrl : null;
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
      onReload={() => refetch()}
      markers={markers}
      vttBlobUrl={variant === "processed" ? vttBlobUrl : null}
      onTimeUpdate={onTimeUpdate}
      className="rounded-none outline-none"
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
    queryFn: () => getPublicRecording(token, "player"),
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
  const onCompanionTab = useCallback((tab: SidePanelTab) => {
    setSidePanelTab(tab);
    scrollPlayerIntoView();
  }, []);
  const [copied, setCopied] = useState(false);
  const { theater, setTheater } = useWatchTheater();
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

  const vttFetchUrl = recording?.vtt_url ?? null;
  useEffect(() => {
    if (!recording?.available_files.includes("vtt")) return;
    const url = vttFetchUrl ?? getShareFileUrl(token, "vtt", true);
    let cancelled = false;
    let objectUrl: string | null = null;
    fetch(url)
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
  }, [token, recording?.available_files, vttFetchUrl]);

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
      setActiveChapterIdx(lastIndexAtOrBefore(topicTimestamps, time));
      setActiveCueIdx(lastIndexAtOrBefore(transcript, time));
    },
    [topicTimestamps, transcript],
  );

  const handleSeek = useCallback((time: number) => {
    if (videoRef.current) videoRef.current.currentTime = time;
  }, []);

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
        listClassName="min-h-0 flex-1 overflow-y-auto"
      />
    ) : null;

  const playerNode = (
    <ShareVideoPlayer
      token={token}
      recordingId={recording.id}
      variant={currentVariant}
      processedPlayUrl={recording.play_url}
      markers={onProcessedTimeline ? markers : []}
      vttBlobUrl={onProcessedTimeline ? vttBlobUrl : null}
      videoRef={videoRef}
      onTimeUpdate={handleTimeUpdate}
      onMediaMissing={handleMediaMissing}
    />
  );

  const hasFiles = artefacts.length > 0 || sourceExtras.length > 0 || (hasVideo && allowVideo);

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
      </header>

      <main className={PAGE_MAIN}>
        <WatchStage
            player={playerNode}
            title={
              <div>
                <h1 className="text-xl font-semibold tracking-tight break-words text-foreground sm:text-2xl">
                  {recording.display_name}
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
                  {bothVariants && (
                    <>
                      <span aria-hidden="true" className="text-border">·</span>
                      <VideoVariantSwitch value={currentVariant} onChange={setVideoVariant} className="text-xs" />
                    </>
                  )}
                </div>
                {bothVariants && !onProcessedTimeline && (hasTopicsPanel || hasTranscript) && (
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    Chapters and transcript follow the edited video.
                  </p>
                )}
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
                      {hasVideo && allowVideo && (
                        <ShareVideoDownloadButton download={() => getShareMedia(token, currentVariant, true)} />
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
