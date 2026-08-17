"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  Check,
  Clock,
  Copy,
  Loader2,
  Video,
  VideoOff,
} from "lucide-react";

import {
  getPublicRecording,
  getShareMedia,
  getShareFileUrl,
  type PublicRecordingResponse,
} from "@/api/share";
import { AIContentEditor, type TopicVersion } from "@/components/recordings/ai-content-editor";
import { ArtefactList, type ArtefactItem, type ArtefactType } from "@/components/recordings/artefact-list";
import { TranscriptPanel, parseVtt, type TranscriptCue } from "@/components/recordings/transcript-panel";
import { type VideoPlayerMarker } from "@/components/ui/video-player";
import { CollapsibleCard, SectionCard } from "@/components/ui/section-card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { cn, formatDate, formatDuration } from "@/lib/utils";

// Plyr uses `document` at module level — must be client-only
const VideoPlayer = dynamic(
  () => import("@/components/ui/video-player").then((m) => m.VideoPlayer),
  {
    ssr: false,
    loading: () => (
      <div className="flex aspect-video items-center justify-center">
        <Loader2 size={24} className="animate-spin text-white/40" />
      </div>
    ),
  },
);

// Matches the app shell's page padding so the public page reads as the same
// product, capped so prose never runs the full width of a wide monitor.
const PAGE_MAIN = "mx-auto w-full max-w-[110rem] p-6 sm:p-8";
const PAGE_HEADER_INNER = "mx-auto flex w-full max-w-[110rem] flex-wrap items-center justify-between gap-x-4 gap-y-2";

const VIDEO_VARIANT_TABS: TabItem<"processed" | "original">[] = [
  { value: "processed", label: "Processed" },
  { value: "original", label: "Original" },
];

/** Index of the last entry that has already started at `time`, or -1. */
function lastIndexAtOrBefore(items: { start: number }[], time: number): number {
  for (let i = items.length - 1; i >= 0; i--) {
    if (time >= items[i].start) return i;
  }
  return -1;
}

// ---------------------------------------------------------------------------
// Video download button — fetches presigned URL then triggers download
// ---------------------------------------------------------------------------

function VideoDownloadButton({
  token,
  variant,
}: {
  token: string;
  variant: "processed" | "original";
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function handleDownload() {
    setLoading(true);
    setError(false);
    try {
      const res = await getShareMedia(token, variant, true);
      const a = document.createElement("a");
      a.href = res.url;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleDownload}
      disabled={loading}
      className={cn(
        "flex w-full items-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-medium transition-colors disabled:opacity-50",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
        error
          ? "border-danger-fg/40 bg-danger-fg/10 text-danger-fg hover:bg-danger-fg/15"
          : "border-primary/30 bg-primary/5 text-primary hover:bg-primary/10"
      )}
    >
      {loading ? <Loader2 size={13} className="animate-spin" /> : <Video size={13} />}
      <span className="flex-1 text-left">{error ? "Download failed — retry" : "Download video"}</span>
      <ArrowDownToLine size={11} className="shrink-0" />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Video player with presigned URL fetching
// ---------------------------------------------------------------------------

function ShareVideoPlayer({
  token,
  variant,
  markers,
  vttBlobUrl,
  videoRef,
  onTimeUpdate,
}: {
  token: string;
  variant: "processed" | "original";
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
}) {
  const { data: videoUrl, isLoading, isError } = useQuery({
    queryKey: ["share-media", token, variant],
    queryFn: async () => {
      const res = await getShareMedia(token, variant);
      return res.url;
    },
  });

  return (
    <div className="aspect-video overflow-hidden rounded-xl bg-black">
      {isLoading && (
        <div className="flex aspect-video items-center justify-center">
          <Loader2 size={24} className="animate-spin text-white/40" />
        </div>
      )}
      {(isError || (!isLoading && !videoUrl)) && (
        <div
          role="status"
          className="flex aspect-video items-center justify-center gap-2 text-sm text-white/60"
        >
          <VideoOff size={18} />
          <span>Video unavailable</span>
        </div>
      )}
      {videoUrl && !isLoading && (
        <VideoPlayer
          ref={videoRef}
          src={videoUrl}
          markers={markers}
          vttBlobUrl={vttBlobUrl}
          onTimeUpdate={onTimeUpdate}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------

export function ShareView({ token }: { token: string }) {
  const {
    data: recording,
    error,
    isPending,
    refetch,
  } = useQuery<PublicRecordingResponse>({
    queryKey: ["share-recording", token],
    queryFn: () => getPublicRecording(token),
    // A revoked link is a final answer; don't spend three round trips on it.
    retry: false,
  });

  const [activeChapterIdx, setActiveChapterIdx] = useState(-1);
  const [activeCueIdx, setActiveCueIdx] = useState(-1);
  const [vttBlobUrl, setVttBlobUrl] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptCue[]>([]);
  const [videoVariant, setVideoVariant] = useState<"processed" | "original">("processed");
  const [copied, setCopied] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const handleCopyLink = useCallback(() => {
    void navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, []);

  // Load VTT once: it feeds both the player's subtitle track and the transcript.
  useEffect(() => {
    if (!recording?.available_files.includes("vtt")) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    fetch(getShareFileUrl(token, "vtt"))
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

  const hasAiContent = !!(
    topicVersion &&
    (topicTimestamps.length || mainTopics.length || topicVersion.summary || topicVersion.questions?.length)
  );

  const markers: VideoPlayerMarker[] = topicTimestamps.map((t) => ({ time: t.start, label: t.topic }));

  // Plyr fires `timeupdate` several times a second. Both values are resolved to
  // an *index* here so React's bail-out absorbs every tick that doesn't cross a
  // boundary — passing the raw time down would re-render the whole page 4×/s.
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

  // `!recording` matters: refetch-on-focus means a flaky network can set
  // `error` while the page is already rendered, and swapping a working page
  // for an error screen because a background refresh blipped is worse than
  // showing slightly stale content.
  if (error && !recording) {
    // Only a 404 means the link is actually gone. A 5xx or a dropped
    // connection is a transport failure the reader can retry — telling them
    // the link was revoked would be a lie in two cases out of three.
    const missing = (error as { response?: { status?: number } })?.response?.status === 404;
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6">
        <div className="w-full max-w-md">
          <ErrorState
            title={missing ? "Link not found" : "Unable to load this recording"}
            description={
              missing
                ? "This share link has been revoked, or it never existed."
                : "Check your connection and try again."
            }
            onRetry={missing ? undefined : () => void refetch()}
          />
        </div>
      </div>
    );
  }

  if (isPending || !recording) {
    return (
      <div className="min-h-screen bg-background">
        <header className="border-b border-border bg-card px-6 py-4">
          <div className={PAGE_HEADER_INNER}>
            <div className="flex items-center gap-3">
              <Skeleton className="h-6 w-6 rounded" />
              <Skeleton className="h-4 w-10" />
            </div>
            <Skeleton className="h-4 w-36" />
          </div>
        </header>
        <main className={PAGE_MAIN}>
          <Skeleton className="mb-6 h-8 w-2/3 sm:w-1/2" />
          <div className="flex flex-col gap-6 lg:flex-row">
            <div className="min-w-0 flex-1 rounded-2xl border border-border bg-card p-5">
              <Skeleton className="aspect-video w-full rounded-xl" />
            </div>
            <div className="w-full shrink-0 lg:w-80">
              <div className="rounded-2xl border border-border bg-card p-5">
                <Skeleton className="mb-3 h-3 w-24" />
                <div className="flex flex-col gap-2">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-9 w-full rounded-xl" />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  const hasVideo = recording.has_processed_video || recording.has_original_video;
  const bothVariants = recording.has_processed_video && recording.has_original_video;
  const currentVariant: "processed" | "original" = recording.has_processed_video ? videoVariant : "original";

  const artefacts: ArtefactItem[] = recording.available_files.map((ft) => ({
    type: ft as ArtefactType,
    href: getShareFileUrl(token, ft),
  }));

  // Chapters, subtitles and the transcript are all produced after the trim
  // stage, so their timecodes only line up with the processed video. On the
  // original they would seek to the wrong place — same rule the recording
  // detail page applies.
  const onProcessedTimeline = currentVariant === "processed";

  const playerNode = (
    <ShareVideoPlayer
      token={token}
      variant={currentVariant}
      markers={onProcessedTimeline ? markers : []}
      vttBlobUrl={onProcessedTimeline ? vttBlobUrl : null}
      videoRef={videoRef}
      onTimeUpdate={handleTimeUpdate}
    />
  );

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card px-6 py-4">
        <div className={PAGE_HEADER_INNER}>
          {/* The one route back into the product for someone who arrived here
              from a pasted link. */}
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
            {/* Announced separately: the visible confirmation lives inside the
                button that already holds focus, so it is never read out. */}
            <span role="status" className="sr-only">
              {copied ? "Link copied to clipboard" : ""}
            </span>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className={PAGE_MAIN}>
        <h1 className="mb-6 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          {recording.display_name}
        </h1>

        {/* Top row: video (left) + artefacts (right) */}
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <div className="min-w-0 flex-1">
            <SectionCard title="Video" density="compact">
              {bothVariants ? (
                <Tabs
                  items={VIDEO_VARIANT_TABS}
                  value={currentVariant}
                  onChange={setVideoVariant}
                  label="Video source"
                >
                  {playerNode}
                </Tabs>
              ) : (
                playerNode
              )}
            </SectionCard>
          </div>

          {(artefacts.length > 0 || hasVideo) && (
            <div className="w-full shrink-0 lg:w-80">
              <SectionCard title="Files" density="compact">
                <div className="flex flex-col gap-2">
                  {hasVideo && <VideoDownloadButton token={token} variant={currentVariant} />}
                  <ArtefactList items={artefacts} />
                </div>
              </SectionCard>
            </div>
          )}
        </div>

        <div className="mt-6 space-y-6">
          {onProcessedTimeline && transcript.length > 0 && (
            <CollapsibleCard title="Transcript" defaultOpen={false}>
              <TranscriptPanel cues={transcript} activeIdx={activeCueIdx} onSeek={handleSeek} />
            </CollapsibleCard>
          )}

          {/* Open by default: chapters, summary and questions are the whole
              reason this is a share page and not a bare video file. Hidden on
              the original, where their timecodes do not apply. */}
          {onProcessedTimeline && hasAiContent && topicVersion && (
            <CollapsibleCard title="Chapters & summary" defaultOpen>
              <AIContentEditor
                recordingId={recording.id}
                version={topicVersion}
                onUpdated={() => {}}
                onSeek={handleSeek}
                activeChapterIdx={activeChapterIdx}
                readOnly
              />
            </CollapsibleCard>
          )}

          {recording.description && (
            <CollapsibleCard title="Description" defaultOpen>
              <p className="max-w-prose whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                {recording.description}
              </p>
            </CollapsibleCard>
          )}
        </div>
      </main>
    </div>
  );
}
