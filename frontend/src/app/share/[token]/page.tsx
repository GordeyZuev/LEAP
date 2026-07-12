"use client";

import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ChevronDown,
  Clock,
  Copy,
  Check,
  FileCode,
  FileText,
  AlignLeft,
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
import { type VideoPlayerMarker } from "@/components/ui/video-player";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

// ---------------------------------------------------------------------------
// File download panel
// ---------------------------------------------------------------------------

const FILE_META: Record<string, { label: string; icon: React.ReactNode }> = {
  srt: { label: "SRT subtitles", icon: <FileCode size={13} /> },
  vtt: { label: "VTT subtitles", icon: <FileCode size={13} /> },
  transcript_json: { label: "Transcript JSON", icon: <FileText size={13} /> },
  transcript_txt: { label: "Transcript", icon: <AlignLeft size={13} /> },
  transcript_words: { label: "Words", icon: <AlignLeft size={13} /> },
};

function FileRow({ token, fileType }: { token: string; fileType: string }) {
  const meta = FILE_META[fileType];
  if (!meta) return null;
  return (
    <a
      href={getShareFileUrl(token, fileType)}
      download
      className="flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-2.5 text-xs font-medium text-secondary-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
    >
      {meta.icon}
      <span className="flex-1">{meta.label}</span>
      <ArrowDownToLine size={11} className="shrink-0 text-muted-foreground" />
    </a>
  );
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
        error
          ? "border-red-300 bg-red-50 text-red-600 hover:bg-red-100 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400 dark:hover:bg-red-500/20"
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
  hasProcessed,
  hasOriginal,
  markers,
  vttBlobUrl,
  videoRef,
  onTimeUpdate,
  onVariantChange,
}: {
  token: string;
  hasProcessed: boolean;
  hasOriginal: boolean;
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
  onVariantChange?: (v: "processed" | "original") => void;
}) {
  const [variant, setVariant] = useState<"processed" | "original">(hasProcessed ? "processed" : "original");

  function switchVariant(v: "processed" | "original") {
    setVariant(v);
    onVariantChange?.(v);
  }

  const { data: videoUrl, isLoading, isError } = useQuery({
    queryKey: ["share-media", token, variant],
    queryFn: async () => {
      const res = await getShareMedia(token, variant);
      return res.url;
    },
  });

  const bothAvailable = hasProcessed && hasOriginal;

  return (
    <div className="flex flex-col gap-2">
      <div className="aspect-video overflow-hidden rounded-2xl bg-black">
        {isLoading && (
          <div className="flex aspect-video items-center justify-center">
            <Loader2 size={24} className="animate-spin text-white/40" />
          </div>
        )}
        {(isError || (!isLoading && !videoUrl)) && (
          <div className="flex aspect-video items-center justify-center gap-2 text-sm text-white/60">
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
      {bothAvailable && (
        <div className="mt-3 flex gap-2">
          {(["processed", "original"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => switchVariant(v)}
              className={cn(
                "rounded-xl border px-4 py-2 text-sm font-medium capitalize transition-colors",
                variant === v
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-card text-secondary-foreground hover:bg-muted"
              )}
            >
              {v}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collapsible section wrapper
// ---------------------------------------------------------------------------

function CollapsibleSection({
  title,
  subtitle,
  defaultOpen = true,
  children,
}: {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border border-border bg-card shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <div className="min-w-0">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h2>
          {subtitle && (
            <p className="mt-0.5 truncate text-sm font-medium text-foreground">{subtitle}</p>
          )}
        </div>
        <ChevronDown
          size={15}
          className={cn("ml-3 shrink-0 text-muted-foreground transition-transform duration-200", open && "rotate-180")}
        />
      </button>
      {open && <div className="border-t border-border px-5 pb-5 pt-4">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SharePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);

  const [recording, setRecording] = useState<PublicRecordingResponse | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [activeChapterIdx, setActiveChapterIdx] = useState(-1);
  const [vttBlobUrl, setVttBlobUrl] = useState<string | null>(null);
  const [videoVariant, setVideoVariant] = useState<"processed" | "original">("processed");
  const [copied, setCopied] = useState(false);
  const chapterRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const videoRef = useRef<HTMLVideoElement>(null);

  const handleCopyLink = useCallback(() => {
    void navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, []);

  useEffect(() => {
    getPublicRecording(token)
      .then(setRecording)
      .catch(() => setNotFound(true));
  }, [token]);

  // Load VTT for subtitles if available
  useEffect(() => {
    if (!recording?.available_files.includes("vtt")) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    fetch(getShareFileUrl(token, "vtt"))
      .then((r) => r.blob())
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setVttBlobUrl(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setVttBlobUrl(null);
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

  const handleTimeUpdate = useCallback(
    (time: number) => {
      let idx = -1;
      for (let i = topicTimestamps.length - 1; i >= 0; i--) {
        if (time >= topicTimestamps[i].start) { idx = i; break; }
      }
      setActiveChapterIdx(idx);
    },
    [topicTimestamps],
  );

  const handleSeek = useCallback((time: number) => {
    if (videoRef.current) videoRef.current.currentTime = time;
  }, []);

  if (notFound) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
        <div className="text-center">
          <p className="text-lg font-semibold text-foreground">Link not found</p>
          <p className="mt-1 text-sm">This share link may have been revoked or never existed.</p>
        </div>
      </div>
    );
  }

  if (!recording) {
    return (
      <div className="min-h-screen bg-background">
        {/* Header skeleton */}
        <header className="border-b border-border bg-card px-6 py-4">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Skeleton className="h-6 w-6 rounded" />
              <Skeleton className="h-4 w-10" />
            </div>
            <Skeleton className="h-4 w-36" />
          </div>
        </header>
        {/* Content skeleton */}
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          <Skeleton className="mb-6 h-7 w-2/3 sm:w-1/2" />
          <div className="flex flex-col gap-4 lg:flex-row">
            <div className="min-w-0 flex-1 rounded-2xl border border-border bg-card p-5">
              <Skeleton className="aspect-video w-full rounded-xl" />
            </div>
            <div className="w-full lg:w-64 xl:w-72 shrink-0">
              <div className="rounded-2xl border border-border bg-card p-4">
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

  const hasFiles = recording.available_files.length > 0;
  const hasVideo = recording.has_processed_video || recording.has_original_video;
  const currentVariant: "processed" | "original" = recording.has_processed_video ? videoVariant : "original";

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card px-6 py-4">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <span className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo_symb.svg" alt="LEAP" className="h-6 w-6" />
            <span className="text-sm font-semibold text-foreground">LEAP</span>
          </span>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Clock size={13} />
              <span>{formatDate(recording.start_time)}</span>
              {recording.duration > 0 && (
                <>
                  <span className="text-border">·</span>
                  <span>{formatDuration(recording.duration)}</span>
                </>
              )}
            </div>
            <button
              type="button"
              onClick={handleCopyLink}
              className={cn(
                "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors",
                copied
                  ? "border-green-300 bg-green-50 text-green-700 dark:border-green-500/30 dark:bg-green-500/10 dark:text-green-400"
                  : "border-border bg-card text-secondary-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
              )}
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? "Copied!" : "Copy link"}
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {/* Recording title */}
        <h1 className="mb-6 text-xl font-bold text-foreground sm:text-2xl">{recording.display_name}</h1>

        {/* Top row: video card (left) + files panel (right) */}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch">
          {/* Video card */}
          <div className="min-w-0 flex-1 rounded-2xl border border-border bg-card p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Video</h2>
            </div>
            <ShareVideoPlayer
              token={token}
              hasProcessed={recording.has_processed_video}
              hasOriginal={recording.has_original_video}
              markers={markers}
              vttBlobUrl={vttBlobUrl}
              videoRef={videoRef}
              onTimeUpdate={handleTimeUpdate}
              onVariantChange={setVideoVariant}
            />
          </div>

          {/* Files & downloads panel */}
          {(hasFiles || hasVideo) && (
            <div className="w-full lg:w-64 xl:w-72 shrink-0">
              <div className="h-full rounded-2xl border border-border bg-card p-4 shadow-sm">
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Artefacts
                </h2>
                <div className="flex flex-col gap-2">
                  {hasVideo && (
                    <VideoDownloadButton token={token} variant={currentVariant} />
                  )}
                  {recording.available_files.map((ft) => (
                    <FileRow key={ft} token={token} fileType={ft} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Description — collapsible, only shown when content exists */}
        {recording.description && (
          <div className="mt-4">
            <CollapsibleSection
              title="Description"
              subtitle={recording.display_name}
              defaultOpen={true}
            >
              <p className="whitespace-pre-wrap text-sm text-foreground leading-relaxed">
                {recording.description}
              </p>
            </CollapsibleSection>
          </div>
        )}

        {/* Video AI-Data — collapsible */}
        {hasAiContent && topicVersion && (
          <div className="mt-4">
            <CollapsibleSection title="Video AI-Data" defaultOpen={false}>
              <AIContentEditor
                recordingId={recording.id}
                version={topicVersion}
                onUpdated={() => {}}
                onSeek={handleSeek}
                activeChapterIdx={activeChapterIdx}
                chapterItemRef={(idx, el) => {
                  if (el) chapterRefs.current.set(idx, el);
                  else chapterRefs.current.delete(idx);
                }}
                readOnly
              />
            </CollapsibleSection>
          </div>
        )}
      </main>
    </div>
  );
}
