"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  Copy,
  Play,
  Video,
  VideoOff,
} from "lucide-react";

import {
  getPlaylistShareFileUrl,
  getPlaylistShareMedia,
  getPublicPlaylist,
  getPublicPlaylistItem,
  sendPlaylistSharePageBeacon,
  type PublicPlaylistItem,
  type PublicRecordingResponse,
} from "@/api/share";
import { AIContentEditor, type TopicVersion } from "@/components/recordings/ai-content-editor";
import { ArtefactList, type ArtefactItem, type ArtefactType } from "@/components/recordings/artefact-list";
import { ShareVideoDownloadButton } from "@/components/recordings/share-video-download-button";
import { TranscriptPanel, parseVtt, type TranscriptCue } from "@/components/recordings/transcript-panel";
import { type VideoPlayerMarker } from "@/components/ui/video-player";
import { VIDEO_PLAYER_FRAME, VideoPlayerLoading } from "@/components/ui/video-player-frame";
import { CARD_SHELL, CollapsibleCard } from "@/components/ui/section-card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { FormattedText } from "@/components/ui/formatted-text";
import { cn, formatDurationCompact, httpStatus } from "@/lib/utils";
import { playlistResumeKey } from "@/lib/video-resume";

const VideoPlayer = dynamic(
  () => import("@/components/ui/video-player").then((m) => m.VideoPlayer),
  { ssr: false, loading: () => <VideoPlayerLoading /> },
);

const MEDIA_URL_STALE_MS = 50 * 60 * 1000;
const EMPTY_ITEMS: PublicPlaylistItem[] = [];

function formatPlaylistDuration(seconds: number): string {
  if (!seconds || seconds < 0) return "0m";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${Math.max(m, 0)}m`;
}

function itemStatus(item: PublicPlaylistItem): string | null {
  if (item.playable) return null;
  if (item.unavailable_reason === "deleted") return "Deleted";
  if (item.unavailable_reason === "blank") return "Blank";
  return "Processing";
}

const PAGE_SHELL = "mx-auto w-full max-w-[110rem] px-4 sm:px-8";
const PAGE_MAIN = cn(PAGE_SHELL, "py-4 sm:py-8");
const PAGE_HEADER_INNER = cn(PAGE_SHELL, "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3 sm:py-4");
const PLAYLIST_GRID =
  "grid grid-cols-1 gap-8 md:grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)] md:items-start lg:grid-cols-[minmax(18rem,26rem)_minmax(0,1fr)] xl:grid-cols-[minmax(20rem,28rem)_minmax(0,1fr)]";
const WATCH_GRID =
  "grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start xl:grid-cols-[minmax(0,1fr)_26rem] 2xl:grid-cols-[minmax(0,1fr)_28rem]";
const COMPANION_COL = "min-w-0 lg:sticky lg:top-6 lg:self-start";
const COMPANION_PANEL = cn(CARD_SHELL, "flex min-h-0 flex-col overflow-hidden");
const COMPANION_SHELL = "flex min-h-0 flex-1 flex-col overflow-hidden";
const COMPANION_TABS_ROW = "shrink-0 border-b border-border px-5 pb-3 pt-3";
const COMPANION_BODY = "min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-5 pt-4";
const PLAYLIST_PLAQUE = cn(
  CARD_SHELL,
  "flex min-h-0 min-w-0 flex-col overflow-hidden p-3 sm:p-5",
  "md:sticky md:top-6 md:h-[calc(100dvh-7.5rem)]",
);
const PLAYER_SHELL = cn(
  CARD_SHELL,
  "overflow-hidden",
  "max-lg:p-0 max-lg:[&_.rounded-xl]:rounded-2xl max-lg:[&_.outline]:outline-none",
  "lg:p-3",
);

type SidePanelTab = "videos" | "topics" | "transcript";

function lastIndexAtOrBefore(items: { start: number }[], time: number): number {
  for (let i = items.length - 1; i >= 0; i--) {
    if (time >= items[i].start) return i;
  }
  return -1;
}

function firstPlayable(items: PublicPlaylistItem[]): PublicPlaylistItem | undefined {
  return items.find((i) => i.playable);
}

function nextPlayable(items: PublicPlaylistItem[], fromId: number): PublicPlaylistItem | undefined {
  const idx = items.findIndex((i) => i.id === fromId);
  if (idx < 0) return firstPlayable(items);
  return items.slice(idx + 1).find((i) => i.playable);
}

function Thumb({
  src,
  duration,
  active,
}: {
  src: string | null;
  duration: number;
  active: boolean;
}) {
  const dur = formatDurationCompact(duration);
  return (
    <span
      className={cn(
        "relative aspect-video w-[7.5rem] shrink-0 overflow-hidden rounded-lg bg-muted",
        "outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10",
      )}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" className="h-full w-full object-cover" />
      ) : (
        <span className="flex h-full items-center justify-center text-muted-foreground">
          <Video size={16} strokeWidth={1.5} aria-hidden />
        </span>
      )}
      {dur && (
        <span className="absolute bottom-1 end-1 rounded bg-black/70 px-1 py-0.5 text-[10px] font-medium tabular-nums text-white">
          {dur}
        </span>
      )}
      {active && (
        <span className="absolute inset-0 flex items-center justify-center bg-black/35 text-white">
          <Play size={18} fill="currentColor" aria-hidden />
        </span>
      )}
    </span>
  );
}

function PlaylistVideoPlayer({
  token,
  itemId,
  markers,
  vttBlobUrl,
  videoRef,
  onTimeUpdate,
  onGone,
}: {
  token: string;
  itemId: number;
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
  onGone?: () => void;
}) {
  const { data: videoUrl, isLoading, isError, refetch, error } = useQuery({
    queryKey: ["playlist-share-media", token, itemId],
    queryFn: async () => {
      const res = await getPlaylistShareMedia(token, itemId);
      return res.url;
    },
    staleTime: MEDIA_URL_STALE_MS,
    retry: false,
  });

  useEffect(() => {
    const status = httpStatus(error);
    if (status === 404) onGone?.();
  }, [error, onGone]);

  if (isLoading) return <VideoPlayerLoading />;
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
        <span>This video is unavailable</span>
      </div>
    );
  }

  return (
    <VideoPlayer
      ref={videoRef}
      src={videoUrl}
      resumeKey={playlistResumeKey(token, itemId)}
      onReload={() => refetch()}
      markers={markers}
      vttBlobUrl={vttBlobUrl}
      onTimeUpdate={onTimeUpdate}
    />
  );
}

export function WatchShell({ token }: { token: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedId = Number(searchParams.get("v") || 0) || null;

  const {
    data: playlist,
    error,
    isPending,
    refetch,
  } = useQuery({
    queryKey: ["public-playlist", token],
    queryFn: () => getPublicPlaylist(token),
    retry: false,
  });

  const [goneId, setGoneId] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const [playIntent, setPlayIntent] = useState(false);
  const [sidePanelTab, setSidePanelTab] = useState<SidePanelTab>("videos");
  const videoColRef = useRef<HTMLDivElement>(null);
  const [companionMaxH, setCompanionMaxH] = useState<number>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const companionPanelId = useId();

  const items = playlist?.items ?? EMPTY_ITEMS;
  const watching = requestedId != null;
  const current = useMemo(() => {
    if (!watching || !items.length) return undefined;
    return items.find((i) => i.id === requestedId);
  }, [items, requestedId, watching]);
  const cover = items[0];
  const startAt = firstPlayable(items);
  const gone = goneId !== null && goneId === current?.id;

  const handleMediaMissing = useCallback(() => {
    void refetch();
  }, [refetch]);

  useEffect(() => {
    if (!watching || !current?.playable) return;
    void sendPlaylistSharePageBeacon(token, current.id).catch(() => {});
  }, [token, watching, current?.id, current?.playable]);

  const { data: recording, error: itemError } = useQuery<PublicRecordingResponse>({
    queryKey: ["public-playlist-item", token, current?.id],
    queryFn: () => getPublicPlaylistItem(token, current!.id),
    enabled: watching && !!current?.playable,
    retry: false,
  });

  useEffect(() => {
    if (httpStatus(itemError) !== 404) return;
    void refetch().then((result) => {
      if (httpStatus(result.error) !== 404) setGoneId(current?.id ?? null);
    });
  }, [itemError, refetch, current?.id]);

  const [vttBlobUrl, setVttBlobUrl] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptCue[]>([]);
  const [activeChapterIdx, setActiveChapterIdx] = useState(-1);
  const [activeCueIdx, setActiveCueIdx] = useState(-1);

  const currentId = current?.id;
  const availableFiles = recording?.available_files;
  useEffect(() => {
    if (!availableFiles?.includes("vtt") || !currentId) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    fetch(getPlaylistShareFileUrl(token, currentId, "vtt", true))
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
  }, [token, currentId, availableFiles]);

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

  const markers: VideoPlayerMarker[] = topicTimestamps.map((t) => ({ time: t.start, label: t.topic }));
  const hasTopicsPanel = !!(mainTopics.length || topicTimestamps.length);
  const hasTranscript = transcript.length > 0;
  const hasExtraContent = !!(topicVersion?.summary || topicVersion?.questions?.length);

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

  const nextItem = current ? nextPlayable(items, current.id) : undefined;
  const durationSum = items.reduce((sum, item) => sum + (item.duration || 0), 0);

  function watchUrl(itemId: number) {
    return `/share/p/${token}?v=${itemId}`;
  }

  function goTo(item: PublicPlaylistItem | undefined, play = true) {
    if (!item) return;
    setGoneId(null);
    if (play) setPlayIntent(true);
    router.push(watchUrl(item.id));
  }

  const shouldAutoplay = watching && playIntent;

  useEffect(() => {
    if (!shouldAutoplay) return;
    const el = videoRef.current;
    if (!el) return;
    let cancelled = false;
    const tryPlay = () => {
      if (cancelled) return;
      void el.play().catch(() => {}).finally(() => {
        if (!cancelled) setPlayIntent(false);
      });
    };
    if (el.readyState >= 2) tryPlay();
    else el.addEventListener("canplay", tryPlay, { once: true });
    const fallback = window.setTimeout(tryPlay, 400);
    return () => {
      cancelled = true;
      el.removeEventListener("canplay", tryPlay);
      window.clearTimeout(fallback);
    };
  }, [shouldAutoplay, current?.id]);

  useEffect(() => {
    if (!watching) return;
    const el = videoColRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;

    const syncHeight = () => {
      setCompanionMaxH(el.getBoundingClientRect().height);
    };

    const raf = window.requestAnimationFrame(syncHeight);
    const observer = new ResizeObserver(syncHeight);
    observer.observe(el);
    window.addEventListener("resize", syncHeight);
    return () => {
      window.cancelAnimationFrame(raf);
      observer.disconnect();
      window.removeEventListener("resize", syncHeight);
    };
  }, [watching, current?.id, recording?.id, gone]);

  if (httpStatus(error) === 404) {
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

  if (error && !playlist) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6">
        <div className="w-full max-w-md">
          <ErrorState
            title="Unable to load this playlist"
            description="Check your connection and try again."
            onRetry={() => void refetch()}
          />
        </div>
      </div>
    );
  }

  if (isPending || !playlist) {
    return (
      <div className="min-h-screen bg-background">
        <header className="border-b border-border bg-card">
          <div className={PAGE_HEADER_INNER}>
            <Skeleton className="h-6 w-24" />
          </div>
        </header>
        <main className={PAGE_MAIN}>
          {watching ? (
            <div className={WATCH_GRID}>
              <div className="min-w-0 space-y-5">
                <Skeleton className="h-7 w-2/3 sm:w-1/2" />
                <div className={cn(VIDEO_PLAYER_FRAME, "animate-pulse")} />
              </div>
              <div className={cn(CARD_SHELL, "h-64 animate-pulse")} />
            </div>
          ) : (
            <div className={PLAYLIST_GRID}>
              <div className={cn(VIDEO_PLAYER_FRAME, "animate-pulse")} />
              <div className="space-y-3">
                <Skeleton className="h-16 w-full rounded-xl" />
                <Skeleton className="h-16 w-full rounded-xl" />
                <Skeleton className="h-16 w-full rounded-xl" />
              </div>
            </div>
          )}
        </main>
      </div>
    );
  }

  const playableCount = items.filter((i) => i.playable).length;
  const noPlayable = playableCount === 0;

  const sidePanelTabs: TabItem<SidePanelTab>[] = [
    { value: "videos", label: "Videos" },
    ...(hasTopicsPanel ? [{ value: "topics" as const, label: "Topics" }] : []),
    ...(hasTranscript ? [{ value: "transcript" as const, label: "Transcript" }] : []),
  ];
  const activeTab = sidePanelTabs.some((t) => t.value === sidePanelTab)
    ? sidePanelTab
    : "videos";

  const allowVideo = recording?.allow_video_download !== false;
  const allowFiles = recording?.allow_files_download !== false;
  const artefacts: ArtefactItem[] = allowFiles && recording && current
    ? recording.available_files.map((ft) => ({
        type: ft as ArtefactType,
        href: getPlaylistShareFileUrl(token, current.id, ft),
      }))
    : [];
  const hasVideo = !!recording?.has_processed_video;
  const hasFiles = artefacts.length > 0 || (hasVideo && allowVideo);

  return (
    <div className="min-h-screen bg-background">
      <a
        href="#playlist-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow"
      >
        Skip to {watching ? "video" : "playlist"}
      </a>
      <header className="border-b border-border bg-card">
        <div className={PAGE_HEADER_INNER}>
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href="/"
              className="flex shrink-0 items-center gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo_symb.svg" alt="" aria-hidden="true" className="h-6 w-6" />
              <span className="text-sm font-semibold text-foreground">LEAP</span>
            </Link>
            {watching ? (
              <Link
                href={`/share/p/${token}`}
                className="hidden min-w-0 truncate text-sm text-muted-foreground hover:text-primary sm:block"
              >
                {playlist.name}
              </Link>
            ) : (
              <span className="hidden min-w-0 truncate text-sm text-muted-foreground sm:block">{playlist.name}</span>
            )}
          </div>
          <button
            type="button"
            onClick={() => {
              const url = watching
                ? window.location.href
                : `${window.location.origin}/share/p/${token}`;
              void navigator.clipboard.writeText(url).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              });
            }}
            className={cn(
              "flex min-h-9 items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
              copied
                ? "border-success-fg/40 bg-success-fg/10 text-success-fg"
                : "border-border bg-card text-secondary-foreground hover:border-primary/40",
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

      <main id="playlist-main" className={PAGE_MAIN}>
        {watching ? (
          <div className="space-y-5 sm:space-y-8">
            <WatchLayout
              playlistName={playlist.name}
              token={token}
              items={items}
              current={current}
              gone={gone}
              nextItem={nextItem}
              markers={markers}
              vttBlobUrl={vttBlobUrl}
              videoRef={videoRef}
              videoColRef={videoColRef}
              companionMaxH={companionMaxH}
              companionPanelId={companionPanelId}
              sidePanelTabs={sidePanelTabs}
              activeTab={activeTab}
              onTabChange={setSidePanelTab}
              topicVersion={topicVersion}
              hasTopicsPanel={hasTopicsPanel}
              hasTranscript={hasTranscript}
              transcript={transcript}
              activeChapterIdx={activeChapterIdx}
              activeCueIdx={activeCueIdx}
              recordingId={recording?.id}
              onSeek={handleSeek}
              onTimeUpdate={handleTimeUpdate}
              onGone={handleMediaMissing}
              onNext={() => goTo(nextItem, true)}
              onNavigate={() => {
                setGoneId(null);
                setPlayIntent(true);
              }}
            />

            <div className="space-y-6">
              {hasExtraContent && topicVersion && (
                <CollapsibleCard title="Extra content" defaultOpen={false}>
                  <AIContentEditor
                    recordingId={recording?.id ?? 0}
                    version={topicVersion}
                    onUpdated={() => {}}
                    readOnly
                    sections={["summary", "questions"]}
                  />
                </CollapsibleCard>
              )}

              {hasFiles && current && (
                <CollapsibleCard title="Files" defaultOpen={false}>
                  <div className="flex flex-col gap-2">
                    {hasVideo && allowVideo && (
                      <ShareVideoDownloadButton
                        download={() => getPlaylistShareMedia(token, current.id, true)}
                      />
                    )}
                    <ArtefactList items={artefacts} />
                  </div>
                </CollapsibleCard>
              )}

              {recording?.description && (
                <CollapsibleCard title="Overview" defaultOpen={false}>
                  <FormattedText
                    text={recording.description}
                    className="text-sm leading-relaxed text-foreground"
                  />
                </CollapsibleCard>
              )}
            </div>
          </div>
        ) : (
          <div className={PLAYLIST_GRID}>
            <section className={PLAYLIST_PLAQUE}>
              <h1 className="shrink-0 text-xl font-semibold tracking-tight break-words text-foreground">
                {playlist.name}
              </h1>
              <p className="mt-1.5 shrink-0 text-sm text-muted-foreground">
                Playlist
                <span aria-hidden> · </span>
                <span className="tabular-nums">{items.length}</span> {items.length === 1 ? "video" : "videos"}
                {durationSum > 0 && (
                  <>
                    <span aria-hidden> · </span>
                    <span className="tabular-nums">{formatPlaylistDuration(durationSum)}</span>
                  </>
                )}
              </p>
              {!startAt || !cover ? (
                <div className={cn(VIDEO_PLAYER_FRAME, "mt-4 flex shrink-0 flex-col items-center justify-center gap-2 text-muted-foreground")}>
                  <VideoOff size={28} strokeWidth={1.5} />
                </div>
              ) : (
                <Link
                  href={watchUrl(startAt.id)}
                  onClick={() => setPlayIntent(true)}
                  aria-label={startAt.title}
                  className="relative mt-4 block shrink-0 overflow-hidden rounded-xl max-md:-mx-3 max-md:rounded-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                >
                  <span className={cn(VIDEO_PLAYER_FRAME, "block bg-muted")}>
                    {cover.poster_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={cover.poster_url} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <span className="flex h-full items-center justify-center text-muted-foreground">
                        <Video size={28} strokeWidth={1.5} aria-hidden />
                      </span>
                    )}
                  </span>
                </Link>
              )}

              {noPlayable ? (
                <p className="mt-3 flex-1 text-sm leading-relaxed text-pretty text-muted-foreground">
                  This playlist has no playable videos yet.
                </p>
              ) : playlist.description ? (
                <FormattedText
                  text={playlist.description}
                  className="mt-3 min-h-0 flex-1 overflow-y-auto text-sm leading-relaxed text-pretty text-muted-foreground"
                />
              ) : (
                <div className="min-h-0 flex-1" aria-hidden />
              )}
            </section>

            <VideoList token={token} items={items} currentId={null} onNavigate={() => setPlayIntent(true)} />
          </div>
        )}
      </main>
    </div>
  );
}

function WatchLayout({
  playlistName,
  token,
  items,
  current,
  gone,
  nextItem,
  markers,
  vttBlobUrl,
  videoRef,
  videoColRef,
  companionMaxH,
  companionPanelId,
  sidePanelTabs,
  activeTab,
  onTabChange,
  topicVersion,
  hasTopicsPanel,
  hasTranscript,
  transcript,
  activeChapterIdx,
  activeCueIdx,
  recordingId,
  onSeek,
  onTimeUpdate,
  onGone,
  onNext,
  onNavigate,
}: {
  playlistName: string;
  token: string;
  items: PublicPlaylistItem[];
  current: PublicPlaylistItem | undefined;
  gone: boolean;
  nextItem: PublicPlaylistItem | undefined;
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  videoColRef: React.RefObject<HTMLDivElement | null>;
  companionMaxH: number | undefined;
  companionPanelId: string;
  sidePanelTabs: TabItem<SidePanelTab>[];
  activeTab: SidePanelTab;
  onTabChange: (tab: SidePanelTab) => void;
  topicVersion: TopicVersion | null;
  hasTopicsPanel: boolean;
  hasTranscript: boolean;
  transcript: TranscriptCue[];
  activeChapterIdx: number;
  activeCueIdx: number;
  recordingId: number | undefined;
  onSeek: (time: number) => void;
  onTimeUpdate: (time: number) => void;
  onGone: () => void;
  onNext: () => void;
  onNavigate: () => void;
}) {
  const playable = !!current?.playable && !gone;
  const companionBody =
    activeTab === "videos" ? (
      <VideoList token={token} items={items} currentId={current?.id ?? null} onNavigate={onNavigate} embedded />
    ) : activeTab === "topics" && hasTopicsPanel && topicVersion ? (
      <AIContentEditor
        recordingId={recordingId ?? 0}
        version={topicVersion}
        onUpdated={() => {}}
        onSeek={onSeek}
        activeChapterIdx={activeChapterIdx}
        readOnly
        sections={["chapters"]}
        embeddedInPanel
      />
    ) : activeTab === "transcript" && hasTranscript ? (
      <TranscriptPanel
        cues={transcript}
        activeIdx={activeCueIdx}
        onSeek={onSeek}
        listClassName="max-h-none overflow-visible"
      />
    ) : null;

  return (
    <div className={WATCH_GRID}>
      <div ref={videoColRef} className="min-w-0">
        <p className="mb-2 text-sm text-muted-foreground">
          <Link
            href={`/share/p/${token}`}
            className="rounded-sm hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            {playlistName}
          </Link>
        </p>
        <h1 className="mb-5 text-xl font-semibold tracking-tight break-words text-foreground sm:text-2xl">
          {current?.title ?? "Video unavailable"}
        </h1>
        <div className={PLAYER_SHELL}>
          {playable && current ? (
            <PlaylistVideoPlayer
              key={current.id}
              token={token}
              itemId={current.id}
              markers={markers}
              vttBlobUrl={vttBlobUrl}
              videoRef={videoRef}
              onTimeUpdate={onTimeUpdate}
              onGone={onGone}
            />
          ) : (
            <div
              role="status"
              className={cn(
                VIDEO_PLAYER_FRAME,
                "flex flex-col items-center justify-center gap-2 text-sm text-muted-foreground",
              )}
            >
              <VideoOff size={18} />
              <span>{current ? "This video is unavailable" : "This video is not in the playlist"}</span>
            </div>
          )}
        </div>
        {gone && nextItem && (
          <button type="button" onClick={onNext} className="mt-3 text-sm text-primary hover:underline">
            Next video
          </button>
        )}
      </div>

      <div className={COMPANION_COL}>
        <div
          className={cn(COMPANION_PANEL, companionMaxH && "lg:h-[var(--companion-h)]")}
          style={companionMaxH ? { ["--companion-h" as string]: `${companionMaxH}px` } : undefined}
        >
          <div className={COMPANION_SHELL}>
            <div className={COMPANION_TABS_ROW}>
              <Tabs
                items={sidePanelTabs}
                value={activeTab}
                onChange={onTabChange}
                label="Companion content"
                hidePanel
                idPrefix={companionPanelId}
                panelId={companionPanelId}
                tablistClassName="mb-0 -my-0"
              >
                {null}
              </Tabs>
            </div>
            <div
              role="tabpanel"
              id={companionPanelId}
              aria-labelledby={`${companionPanelId}-tab-${activeTab}`}
              className={cn(COMPANION_BODY, activeTab === "videos" && "px-3")}
            >
              {companionBody}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function VideoList({
  token,
  items,
  currentId,
  onNavigate,
  sticky = false,
  embedded = false,
}: {
  token: string;
  items: PublicPlaylistItem[];
  currentId: number | null;
  onNavigate?: () => void;
  sticky?: boolean;
  embedded?: boolean;
}) {
  const list = (
    <ol className="space-y-1">
      {items.map((item, idx) => {
        const active = currentId === item.id;
        const status = itemStatus(item);
        const rowClass = cn(
          "flex w-full min-h-11 min-w-0 items-center gap-3 rounded-xl p-2 text-left transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
          active && "bg-muted",
          !item.playable && "cursor-not-allowed opacity-60",
          item.playable && !active && "hover:bg-muted/70",
        );
        const body = (
          <>
            <span className="w-5 shrink-0 text-center text-xs tabular-nums text-muted-foreground">{idx + 1}</span>
            <Thumb src={item.poster_url} duration={item.duration} active={active && item.playable} />
            <span className="min-w-0 flex-1">
              <span className={cn("line-clamp-2 text-sm font-medium leading-snug text-foreground", !item.playable && "text-muted-foreground")}>
                {item.title}
              </span>
              {status && <span className="mt-1 block text-xs text-muted-foreground">{status}</span>}
            </span>
          </>
        );
        return (
          <li key={item.id}>
            {item.playable ? (
              <Link
                href={`/share/p/${token}?v=${item.id}`}
                aria-current={active ? "true" : undefined}
                onClick={onNavigate}
                className={rowClass}
              >
                {body}
              </Link>
            ) : (
              <span className={rowClass}>{body}</span>
            )}
          </li>
        );
      })}
    </ol>
  );

  if (embedded) {
    return (
      <div aria-label="Videos">
        {list}
      </div>
    );
  }

  return (
    <section
      aria-label="Videos"
      className={cn(
        CARD_SHELL,
        "min-w-0 p-3 sm:p-4",
        sticky && "lg:sticky lg:top-6 lg:max-h-[calc(100dvh-7.5rem)] lg:overflow-y-auto",
      )}
    >
      <h2 className="mb-3 px-1 text-sm font-semibold text-foreground">Videos</h2>
      {list}
    </section>
  );
}
