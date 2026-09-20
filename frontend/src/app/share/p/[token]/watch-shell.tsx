"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Clock,
  Folder,
  ListVideo,
  Play,
  VideoOff,
} from "lucide-react";

import {
  getPlaylistShareFileUrl,
  getPlaylistSharePosters,
  getPlaylistShareMedia,
  getPublicPlaylist,
  getPublicPlaylistItem,
  sendPlaylistLandingBeacon,
  sendPlaylistSharePageBeacon,
  type PublicPlaylistItem,
  type PublicPlaylistGroup,
  type PublicRecordingResponse,
} from "@/api/share";
import { AIContentEditor, type TopicVersion } from "@/components/recordings/ai-content-editor";
import { resolveStorageUrl } from "@/api/client";
import { StablePosterImage } from "@/components/recordings/recording-poster";
import { ArtefactList, SourceExtrasSection, sourceExtrasToArtefacts, type ArtefactItem, type ArtefactType } from "@/components/recordings/artefact-list";
import { ShareVideoDownloadButton } from "@/components/recordings/share-video-download-button";
import { PublicShareHeader } from "@/components/share/public-share-header";
import { TranscriptPanel, type TranscriptCue } from "@/components/recordings/transcript-panel";
import { type VideoPlayerMarker } from "@/components/ui/video-player";
import { VIDEO_PLAYER_FRAME, VideoPlayerLoading } from "@/components/ui/video-player-frame";
import { FilterSelect } from "@/components/filters/filter-select";
import { SearchInput } from "@/components/filters/search-input";
import { CARD_SHELL, CollapsibleCard } from "@/components/ui/section-card";
import { COMPANION_BODY, COMPANION_BODY_PINNED, COMPANION_TABS_ROW, WATCH_BELOW, WatchStage } from "@/components/ui/watch-stage";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { FormattedText } from "@/components/ui/formatted-text";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { usePresignedMediaRefresh } from "@/hooks/use-presigned-media";
import { useShareEngagement } from "@/hooks/use-share-engagement";
import { useShareVtt } from "@/hooks/use-share-vtt";
import { useWatchTheater } from "@/hooks/use-watch-theater";
import { WatchVideoVariantChrome } from "@/components/ui/watch-video-variant-chrome";
import { readPlaylistAutoplayNext, writePlaylistAutoplayNext } from "@/lib/playlist-autoplay";
import { cn, formatDate, formatDuration, formatDurationCompact, httpStatus, scrollPlayerIntoView } from "@/lib/utils";
import {
  catalogPlaylistItems,
  parsePlaylistVideoSort,
  PLAYLIST_VIDEO_SORT,
  visiblePlaylistFolderItems,
  type PlaylistVideoSort,
} from "@/lib/playlist-catalog";
import { firstPlayable, lastIndexAtOrBefore, nextPlayable } from "@/lib/playlist-playable";
import { paginateItems, parseCatalogPage, CATALOG_PAGE_SIZE } from "@/lib/catalog-page";
import type { ChapterSeekSource, PlaylistNavFrom } from "@/lib/share-engagement";
import { trackPlaylistNavigateDeduped } from "@/lib/share-engagement";
import { playlistResumeKey } from "@/lib/video-resume";

const VideoPlayer = dynamic(
  () => import("@/components/ui/video-player").then((m) => m.VideoPlayer),
  { ssr: false, loading: () => <VideoPlayerLoading /> },
);

const MEDIA_URL_STALE_MS = 50 * 60 * 1000;
const EMPTY_ITEMS: PublicPlaylistItem[] = [];
const NAV_FROM_KEY = "leap:playlist-nav-from";

function playlistLandingHref(token: string, fromSlug: string | null, groupId: number | null = null): string {
  const p = new URLSearchParams();
  if (groupId !== null) p.set("group", String(groupId));
  if (fromSlug) p.set("from", fromSlug);
  const query = p.toString();
  return `/share/p/${token}${query ? `?${query}` : ""}`;
}

function playlistWatchHref(
  token: string, itemId: number, fromSlug: string | null, groupId: number | null = null,
): string {
  const p = new URLSearchParams();
  p.set("v", String(itemId));
  if (groupId !== null) p.set("group", String(groupId));
  if (fromSlug) p.set("from", fromSlug);
  return `/share/p/${token}?${p.toString()}`;
}

function writeLandingParams(next: { q: string; sort: PlaylistVideoSort; page: number; groupId: number | null }) {
  const url = new URL(window.location.href);
  if (next.q.trim()) url.searchParams.set("q", next.q.trim());
  else url.searchParams.delete("q");
  if (next.sort !== "order") url.searchParams.set("sort", next.sort);
  else url.searchParams.delete("sort");
  if (next.page > 1) url.searchParams.set("page", String(next.page));
  else url.searchParams.delete("page");
  if (next.groupId !== null) url.searchParams.set("group", String(next.groupId));
  else url.searchParams.delete("group");
  url.searchParams.delete("v");
  window.history.replaceState(null, "", url.toString());
}

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

const PAGE_SHELL = "mx-auto w-full max-w-[110rem] px-4 sm:px-6 lg:px-8";
const PAGE_MAIN = cn(PAGE_SHELL, "py-4 sm:py-8");
const PLAYLIST_GRID =
  "grid grid-cols-1 gap-8 md:grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)] md:items-start lg:grid-cols-[minmax(18rem,26rem)_minmax(0,1fr)] xl:grid-cols-[minmax(20rem,28rem)_minmax(0,1fr)]";
const PLAYLIST_PLAQUE = cn(
  CARD_SHELL,
  "flex min-w-0 flex-col overflow-hidden p-3 sm:p-5",
  "md:sticky md:top-6",
);

type SidePanelTab = "videos" | "topics" | "transcript";

function Thumb({
  src,
  posterAssetKey,
  duration,
  active,
}: {
  src: string | null;
  posterAssetKey?: string | null;
  duration: number;
  active: boolean;
}) {
  const dur = formatDurationCompact(duration);
  return (
    <span className="relative aspect-video w-[7.5rem] shrink-0">
      <StablePosterImage
        posterUrl={src}
        posterAssetKey={posterAssetKey}
        className="h-full w-full"
        placeholderIconSize={16}
      />
      {dur && (
        <span className="pointer-events-none absolute bottom-1 end-1 rounded bg-black/70 px-1 py-0.5 text-[10px] font-medium tabular-nums text-white">
          {dur}
        </span>
      )}
      {active && (
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg bg-black/35 text-white">
          <Play size={18} fill="currentColor" aria-hidden />
        </span>
      )}
    </span>
  );
}

function PlaylistVideoPlayer({
  token,
  itemId,
  variant,
  processedPlayUrl,
  originalPlayUrl,
  mediaExpiresIn,
  mediaIssuedAtMs,
  itemFetching,
  onItemRefetch,
  markers,
  vttBlobUrl,
  videoRef,
  onTimeUpdate,
  onGone,
  onEnded,
  onMarkerSeek,
  autoPlayRequested,
  onAutoPlayAttempt,
  overlay,
}: {
  token: string;
  itemId: number;
  variant: "processed" | "original";
  processedPlayUrl?: string | null;
  originalPlayUrl?: string | null;
  mediaExpiresIn?: number | null;
  mediaIssuedAtMs: number;
  itemFetching: boolean;
  onItemRefetch: (variant: "processed" | "original") => Promise<string | null>;
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
  onGone?: () => void;
  onEnded?: () => void;
  onMarkerSeek?: (time: number, label: string) => void;
  autoPlayRequested?: boolean;
  onAutoPlayAttempt?: () => void;
  overlay?: React.ReactNode;
}) {
  const presetUrl = variant === "processed" ? processedPlayUrl : originalPlayUrl;
  const { data: media, dataUpdatedAt: mediaUpdatedAt, isLoading, refetch, error } = useQuery({
    queryKey: ["playlist-share-media", token, itemId, variant],
    queryFn: () => getPlaylistShareMedia(token, itemId, false, variant),
    enabled: !presetUrl && !itemFetching,
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
    const status = httpStatus(error);
    if (status === 404) onGone?.();
  }, [error, onGone]);

  if (!resolvedUrl && (itemFetching || isLoading)) return <VideoPlayerLoading />;
  if (!resolvedUrl) {
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
      key={`${itemId}-${variant}`}
      ref={videoRef}
      src={resolvedUrl}
      resumeKey={playlistResumeKey(token, itemId, variant)}
      onReload={refreshMedia}
      markers={markers}
      vttBlobUrl={variant === "processed" ? vttBlobUrl : null}
      onTimeUpdate={onTimeUpdate}
      onEnded={onEnded}
      onMarkerSeek={onMarkerSeek}
      autoPlayRequested={autoPlayRequested}
      onAutoPlayAttempt={onAutoPlayAttempt}
      overlay={overlay}
      className="rounded-none outline-none"
    />
  );
}

export function WatchShell({
  token,
  initialPlaylist,
  initialView = "full",
  initialFromSlug = null,
}: {
  token: string;
  initialPlaylist?: import("@/api/share").PublicPlaylistResponse | null;
  initialView?: "full" | "catalog";
  initialFromSlug?: string | null;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const requestedId = Number(searchParams.get("v") || 0) || null;
  const fromSlug = searchParams.get("from");
  const [landingQuery, setLandingQuery] = useState(searchParams.get("q") ?? "");
  const [landingSort, setLandingSort] = useState<PlaylistVideoSort>(parsePlaylistVideoSort(searchParams.get("sort")));
  const [landingPage, setLandingPage] = useState(() => parseCatalogPage(searchParams.get("page")));
  const landingGroupId = (() => {
    const id = Number(searchParams.get("group"));
    return Number.isSafeInteger(id) && id > 0 ? id : null;
  })();
  const landingFilterKey = `${landingQuery}\0${landingSort}\0${landingGroupId ?? ""}`;
  const [appliedLandingFilterKey, setAppliedLandingFilterKey] = useState(landingFilterKey);
  if (appliedLandingFilterKey !== landingFilterKey) {
    setAppliedLandingFilterKey(landingFilterKey);
    if (landingPage !== 1) setLandingPage(1);
  }
  const engagementPath = useMemo(() => {
    if (!requestedId) return null;
    const q = fromSlug ? `?from=${encodeURIComponent(fromSlug)}` : "";
    return `/share/p/${token}/items/${requestedId}/engagement${q}`;
  }, [token, requestedId, fromSlug]);
  const { track, flush } = useShareEngagement(engagementPath);
  const watching = requestedId != null;
  const playlistView = "catalog";

  const {
    data: playlist,
    error,
    isPending,
    refetch,
  } = useQuery({
    queryKey: ["public-playlist", token, playlistView, fromSlug],
    queryFn: () => getPublicPlaylist(token, playlistView, fromSlug),
    initialData: playlistView === initialView && fromSlug === initialFromSlug ? (initialPlaylist ?? undefined) : undefined,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const channel = playlist?.channels.find((candidate) => candidate.slug === fromSlug?.trim().toLowerCase());
  const channelSlug = channel?.slug ?? null;

  const [goneId, setGoneId] = useState<number | null>(null);
  const [playTargetId, setPlayTargetId] = useState<number | null>(null);
  const [endedId, setEndedId] = useState<number | null>(null);
  const [sidePanelTab, setSidePanelTab] = useState<SidePanelTab | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const durationFallbackRef = useRef(0);
  const positionRef = useRef(0);
  const companionPanelId = useId();

  const items = playlist?.items ?? EMPTY_ITEMS;
  const groups = playlist?.groups ?? [];
  const selectedGroup = groups.find((group) => group.id === landingGroupId);
  const hasGroups = groups.length > 0;
  const activeGroupId = selectedGroup?.id ?? null;
  const landingItems = useMemo(
    () => {
      const visible = visiblePlaylistFolderItems(items, selectedGroup?.id ?? null, hasGroups, landingQuery);
      return catalogPlaylistItems(visible, landingQuery, landingSort);
    },
    [items, landingQuery, landingSort, hasGroups, selectedGroup],
  );
  const landingPagingPage = appliedLandingFilterKey !== landingFilterKey ? 1 : landingPage;
  const landingPaged = useMemo(
    () => paginateItems(landingItems, landingPagingPage),
    [landingItems, landingPagingPage],
  );
  const current = useMemo(() => {
    if (!watching || !items.length) return undefined;
    return items.find((i) => i.id === requestedId);
  }, [items, requestedId, watching]);
  const startAt = firstPlayable(items);
  const cover = startAt ?? items[0];
  const posterIds = useMemo(
    () => [...new Set([...landingPaged.items.map((item) => item.id), ...(cover ? [cover.id] : [])])].sort((a, b) => a - b),
    [landingPaged.items, cover],
  );
  const { data: posters } = useQuery({
    queryKey: ["public-playlist-posters", token, posterIds.join(",")],
    queryFn: () => getPlaylistSharePosters(token, posterIds),
    enabled: !watching && posterIds.length > 0,
    staleTime: MEDIA_URL_STALE_MS,
    retry: false,
  });
  const landingPosterItems = useMemo(
    () => landingPaged.items.map((item) => ({
      ...item,
      poster_url: posters?.[item.id]?.url ?? item.poster_url,
      poster_asset_key: posters?.[item.id]?.asset_key ?? item.poster_asset_key,
    })),
    [landingPaged.items, posters],
  );
  const gone = goneId !== null && goneId === current?.id;

  const handleMediaMissing = useCallback(() => {
    void refetch();
  }, [refetch]);

  useEffect(() => {
    if (!playlist) return;
    if (requestedId) return;
    void sendPlaylistLandingBeacon(token).catch(() => {});
  }, [token, playlist, requestedId]);

  useEffect(() => {
    if (!watching || !current?.playable) return;
    void sendPlaylistSharePageBeacon(token, current.id).catch(() => {});
  }, [token, watching, current?.id, current?.playable]);

  useEffect(() => {
    if (watching || !playlist) return;
    writeLandingParams({ q: landingQuery, sort: landingSort, page: landingPaged.page, groupId: activeGroupId });
  }, [watching, playlist, landingQuery, landingSort, landingPaged.page, activeGroupId]);

  const [videoVariant, setVideoVariant] = useState<"processed" | "original">("processed");
  const [variantItemId, setVariantItemId] = useState(current?.id);
  if (current?.id !== variantItemId) {
    setVariantItemId(current?.id);
    setVideoVariant("processed");
  }

  const {
    data: recording,
    dataUpdatedAt: itemUpdatedAt,
    error: itemError,
    isFetching: itemFetching,
    isPlaceholderData,
    refetch: refetchItem,
  } = useQuery<PublicRecordingResponse>({
    queryKey: ["public-playlist-item", token, current?.id],
    queryFn: () => getPublicPlaylistItem(token, current!.id, "player"),
    enabled: watching && !!current?.playable,
    placeholderData: keepPreviousData,
    retry: false,
  });

  const refetchItemPlayer = useCallback(async (variant: "processed" | "original") => {
    const result = await refetchItem({ cancelRefetch: false });
    if (!result.isSuccess) return null;
    return variant === "processed" ? result.data?.play_url ?? null : result.data?.original_play_url ?? null;
  }, [refetchItem]);

  useEffect(() => {
    if (httpStatus(itemError) !== 404) return;
    void refetch().then((result) => {
      if (httpStatus(result.error) !== 404) setGoneId(current?.id ?? null);
    });
  }, [itemError, refetch, current?.id]);

  const [activeChapterIdx, setActiveChapterIdx] = useState(-1);
  const [activeCueIdx, setActiveCueIdx] = useState(-1);

  const itemRecording = recording && !isPlaceholderData ? recording : undefined;
  const currentId = current?.id;
  const vttFallback =
    currentId && itemRecording?.available_files?.includes("vtt")
      ? getPlaylistShareFileUrl(token, currentId, "vtt", true)
      : null;
  const { vttBlobUrl, transcript } = useShareVtt({
    enabled: Boolean(itemRecording?.vtt_url || vttFallback),
    vttUrl: itemRecording?.vtt_url,
    fallbackUrl: vttFallback,
  });

  const topicTimestamps = useMemo(
    () =>
      Array.isArray(itemRecording?.topic_timestamps)
        ? (itemRecording!.topic_timestamps as { topic: string; start: number }[])
        : [],
    [itemRecording],
  );
  const mainTopics = useMemo(
    () => (Array.isArray(itemRecording?.main_topics) ? (itemRecording!.main_topics as string[]) : []),
    [itemRecording],
  );
  const topicVersion: TopicVersion | null = itemRecording
    ? {
        main_topics: mainTopics,
        topic_timestamps: topicTimestamps,
        summary: itemRecording.summary ?? undefined,
        questions: itemRecording.questions ?? undefined,
      }
    : null;
  const bothVariants = Boolean(
    itemRecording?.has_processed_video && itemRecording?.has_original_video && itemRecording.original_play_url,
  );
  const playVariant = bothVariants ? videoVariant : "processed";
  const onProcessedTimeline = playVariant === "processed";
  const markers: VideoPlayerMarker[] = topicTimestamps.map((t) => ({ time: t.start, label: t.topic }));
  const playerMarkers = onProcessedTimeline ? markers : [];
  const hasTopicsPanel = topicTimestamps.length > 0;
  const hasTranscript = transcript.length > 0;
  const hasExtraContent = !!(
    topicVersion?.summary ||
    topicVersion?.questions?.length ||
    topicVersion?.main_topics?.length
  );

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
    if (!watching || !current?.playable) return;
    let from: PlaylistNavFrom = "url";
    try {
      const pending = window.sessionStorage.getItem(NAV_FROM_KEY);
      if (pending === "sidebar" || pending === "landing" || pending === "autoplay" || pending === "url") {
        from = pending;
        window.sessionStorage.removeItem(NAV_FROM_KEY);
      }
    } catch {
      /* private mode */
    }
    trackPlaylistNavigateDeduped(
      track,
      `${token}:${current.id}:${from}`,
      { to_item_id: current.id, from },
    );
  }, [watching, current?.id, current?.playable, track, token]);

  useEffect(() => {
    if (itemRecording?.duration) {
      durationFallbackRef.current = itemRecording.duration;
    }
  }, [itemRecording?.duration]);

  useEffect(() => {
    if (!watching || !itemRecording?.id) return;
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
  }, [watching, itemRecording?.id, track, flush]);

  function watchUrl(itemId: number) {
    return playlistWatchHref(token, itemId, channelSlug, items.find((item) => item.id === itemId)?.group_id ?? null);
  }

  function goTo(item: PublicPlaylistItem | undefined, play = true, from: PlaylistNavFrom = "sidebar") {
    if (!item) return;
    try {
      window.sessionStorage.setItem(NAV_FROM_KEY, from);
    } catch {
      /* ignore */
    }
    flush();
    setGoneId(null);
    setEndedId(null);
    if (play) setPlayTargetId(item.id);
    router.push(watchUrl(item.id));
  }

  const nextItem = current ? nextPlayable(items, current.id) : firstPlayable(items);
  const durationSum = items.reduce((sum, item) => sum + (item.duration || 0), 0);
  const ended = endedId !== null && endedId === current?.id;

  useEffect(() => {
    if (!recording || !nextItem) return;
    void queryClient.prefetchQuery({
      queryKey: ["public-playlist-item", token, nextItem.id],
      queryFn: () => getPublicPlaylistItem(token, nextItem.id, "player"),
    });
  }, [recording, nextItem, token, queryClient]);

  if (httpStatus(error) === 404) {
    return (
      <div className="bg-background">
        <PublicShareHeader />
        <div className="flex min-h-[70vh] items-center justify-center px-6">
          <div className="w-full max-w-md">
            <ErrorState
              title="Link not found"
              description="This share link has been revoked, or it never existed."
            />
          </div>
        </div>
      </div>
    );
  }

  if (error && !playlist) {
    return (
      <div className="bg-background">
        <PublicShareHeader />
        <div className="flex min-h-[70vh] items-center justify-center px-6">
          <div className="w-full max-w-md">
            <ErrorState
              title="Unable to load this playlist"
              description="Check your connection and try again."
              error={error}
              onRetry={() => void refetch()}
            />
          </div>
        </div>
      </div>
    );
  }

  if (isPending || !playlist) {
    return (
      <div className="bg-background">
        <PublicShareHeader />
        <main className={PAGE_MAIN}>
          {watching ? (
            <div className="space-y-3">
              <div className={cn(VIDEO_PLAYER_FRAME, "animate-pulse")} />
              <Skeleton className="h-7 w-2/3 sm:w-1/2" />
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
    ...(hasTopicsPanel ? [{ value: "topics" as const, label: "Chapters" }] : []),
    ...(hasTranscript ? [{ value: "transcript" as const, label: "Transcript" }] : []),
    { value: "videos", label: "Playlist" },
  ];
  const activeTab = sidePanelTab && sidePanelTabs.some((t) => t.value === sidePanelTab)
    ? sidePanelTab
    : (sidePanelTabs[0]?.value ?? "videos");

  const allowVideo = itemRecording?.allow_video_download !== false;
  const allowFiles = itemRecording?.allow_files_download !== false;
  const artefacts: ArtefactItem[] =
    itemRecording && current
      ? itemRecording.available_files.map((ft) => ({
          type: ft as ArtefactType,
          href: allowFiles ? getPlaylistShareFileUrl(token, current.id, ft) : undefined,
          locked: !allowFiles,
        }))
      : [];
  const sourceExtras =
    allowFiles && itemRecording ? sourceExtrasToArtefacts(itemRecording.source_extras, resolveStorageUrl) : [];
  const hasVideo = !!itemRecording?.has_processed_video || !!itemRecording?.has_original_video;
  const hasFiles = artefacts.length > 0 || sourceExtras.length > 0 || hasVideo;

  return (
    <div className="bg-background">
      <a
        href="#playlist-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow"
      >
        Skip to {watching ? "video" : "playlist"}
      </a>
      <PublicShareHeader>
        {watching ? (
          <Link
            href={playlistLandingHref(token, channelSlug, current?.group_id ?? null)}
            className="min-w-0 truncate rounded-sm text-sm text-muted-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            {playlist.name}
          </Link>
        ) : (
          <span className="hidden min-w-0 truncate text-sm text-muted-foreground sm:block">{playlist.name}</span>
        )}
      </PublicShareHeader>

      <main id="playlist-main" className={PAGE_MAIN}>
        {watching ? (
          <WatchLayout
              token={token}
              fromSlug={channelSlug}
              channelName={channel?.name ?? null}
              playlistName={playlist.name}
              items={items}
              groups={groups}
              current={current}
              gone={gone}
              ended={ended}
              nextItem={nextItem}
              markers={playerMarkers}
              vttBlobUrl={vttBlobUrl}
              videoRef={videoRef}
              companionPanelId={companionPanelId}
              sidePanelTabs={sidePanelTabs}
              activeTab={activeTab}
              onTabChange={(tab) => {
                setSidePanelTab(tab);
                if (tab === "topics" || tab === "transcript") scrollPlayerIntoView();
              }}
              topicVersion={topicVersion}
              hasTopicsPanel={hasTopicsPanel}
              hasTranscript={hasTranscript && onProcessedTimeline}
              transcript={transcript}
              activeChapterIdx={activeChapterIdx}
              activeCueIdx={activeCueIdx}
              recordingId={itemRecording?.id}
              recordingTitle={itemRecording?.title ?? current?.title}
              recordingStartTime={itemRecording?.start_time ?? current?.start_time}
              recordingDuration={itemRecording?.duration ?? current?.duration ?? 0}
              processedPlayUrl={itemRecording?.play_url}
              originalPlayUrl={itemRecording?.original_play_url}
              mediaExpiresIn={itemRecording?.media_expires_in}
              mediaIssuedAtMs={itemUpdatedAt}
              itemFetching={itemFetching && !itemRecording}
              onItemRefetch={refetchItemPlayer}
              videoVariant={playVariant}
              onVideoVariantChange={setVideoVariant}
              bothVariants={bothVariants}
              onProcessedTimeline={onProcessedTimeline}
              onSeek={(time) => {
                const source: ChapterSeekSource = activeTab === "transcript" ? "transcript" : "sidebar";
                seekWithEngagement(time, source);
              }}
              onMarkerSeek={(time, label) => {
                handleSeek(time);
                track("chapter_seek", {
                  source: "marker",
                  time_sec: Math.floor(time),
                  label,
                });
              }}
              onItemSelect={(item) => goTo(item, true, "sidebar")}
              onTimeUpdate={handleTimeUpdate}
              onGone={handleMediaMissing}
              onEnded={() => {
                track("playback_complete", {});
                if (readPlaylistAutoplayNext() && nextItem) {
                  goTo(nextItem, true, "autoplay");
                  return;
                }
                setEndedId(current?.id ?? null);
              }}
              autoPlayRequested={playTargetId === current?.id}
              onAutoPlayAttempt={() => setPlayTargetId((id) => id === current?.id ? null : id)}
              onNext={() => goTo(nextItem, true, "sidebar")}
              below={
                <div className={WATCH_BELOW}>
                  {hasExtraContent && topicVersion && (
                    <CollapsibleCard title="Summary & questions">
                      <AIContentEditor
                        key={itemRecording?.id ?? 0}
                        recordingId={itemRecording?.id ?? 0}
                        version={topicVersion}
                        onUpdated={() => {}}
                        readOnly
                        sections={["topics", "summary", "questions"]}
                      />
                    </CollapsibleCard>
                  )}

                  {hasFiles && current && (
                    <CollapsibleCard title="Files">
                      <div className="flex flex-col gap-2">
                        {hasVideo && (
                          <ShareVideoDownloadButton
                            locked={!allowVideo}
                            download={() => getPlaylistShareMedia(token, current.id, true, playVariant)}
                          />
                        )}
                        <ArtefactList items={artefacts} />
                        <SourceExtrasSection items={sourceExtras} />
                      </div>
                    </CollapsibleCard>
                  )}

                  {itemRecording?.description && (
                    <CollapsibleCard title="Created Overview" defaultOpen={false}>
                      <FormattedText
                        text={itemRecording.description}
                        className="text-sm leading-relaxed text-foreground"
                      />
                    </CollapsibleCard>
                  )}
                </div>
              }
            />
        ) : (
          <div className={PLAYLIST_GRID}>
            <section className={PLAYLIST_PLAQUE}>
              {channel ? (
                <Link href={`/c/${channel.slug}`} className="mb-2 text-sm text-muted-foreground hover:text-foreground">
                  ← {channel.name}
                </Link>
              ) : null}
              <h1 className="shrink-0 text-xl font-semibold tracking-tight break-words text-foreground">{playlist.name}</h1>
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
                  onClick={() => {
                    setPlayTargetId(startAt.id);
                    try {
                      window.sessionStorage.setItem(NAV_FROM_KEY, "landing");
                    } catch {
                      /* private mode */
                    }
                  }}
                  aria-label={`Play ${startAt.title}`}
                  className="relative mt-4 block overflow-hidden rounded-xl max-md:-mx-3 max-md:rounded-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                >
                  <span className={cn(VIDEO_PLAYER_FRAME, "block bg-muted")}>
                    <StablePosterImage
                      posterUrl={posters?.[cover.id]?.url ?? cover.poster_url}
                      posterAssetKey={posters?.[cover.id]?.asset_key ?? cover.poster_asset_key}
                      className="h-full w-full rounded-none"
                      placeholderIconSize={28}
                    />
                    <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/35 text-white">
                      <Play size={48} fill="currentColor" aria-hidden />
                    </span>
                  </span>
                </Link>
              )}

              {noPlayable ? (
                <p className="mt-3 text-sm leading-relaxed text-pretty text-muted-foreground">
                  This playlist has no playable videos yet.
                </p>
              ) : playlist.description ? (
                <FormattedText
                  text={playlist.description}
                  className="mt-3 text-sm leading-relaxed text-pretty text-muted-foreground"
                />
              ) : null}
            </section>

            <div className="min-w-0">
              {items.length > 0 && (
                <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
                  <SearchInput
                    id="playlist-catalog-search"
                    className="min-w-0 sm:min-w-[15rem] sm:flex-[2]"
                    value={landingQuery}
                    onChange={setLandingQuery}
                    placeholder="Search videos…"
                  />
                  <div className="min-w-0 sm:min-w-[11rem] sm:flex-1">
                    <label htmlFor="playlist-catalog-sort" className={FILTER_LABEL}>
                      Sort by
                    </label>
                    <FilterSelect
                      id="playlist-catalog-sort"
                      value={landingSort}
                      options={[...PLAYLIST_VIDEO_SORT]}
                      onChange={(v) => setLandingSort(v as PlaylistVideoSort)}
                      filled={landingSort !== "order"}
                    />
                  </div>
                </div>
              )}
              {hasGroups && (
                selectedGroup ? (
                  <div className="mb-4 flex items-center gap-3">
                    <Link
                      href={playlistLandingHref(token, channelSlug)}
                      className="text-sm font-medium text-primary hover:underline"
                    >
                      ← All groups
                    </Link>
                    <span className="text-sm font-semibold">{selectedGroup.name}</span>
                  </div>
                ) : !landingQuery.trim() ? (
                  <div className="mb-5 grid gap-3 sm:grid-cols-2">
                    {groups.map((group) => (
                      <Link
                        key={group.id}
                        href={playlistLandingHref(token, channelSlug, group.id)}
                        className="pressable flex min-w-0 items-center gap-3 rounded-xl border border-border bg-card p-4 text-left hover:bg-muted/60"
                      >
                        <Folder size={24} className="shrink-0 text-primary" aria-hidden />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold">{group.name}</span>
                          <span className="text-xs text-muted-foreground">
                            {group.item_count} {group.item_count === 1 ? "video" : "videos"}
                          </span>
                        </span>
                      </Link>
                    ))}
                  </div>
                ) : null
              )}
              {items.length > 0 && landingItems.length === 0 && landingQuery.trim() ? (
                <EmptyState
                  icon={ListVideo}
                  title={`No results for “${landingQuery.trim()}”`}
                  description="Try a different search."
                  action={
                    <button
                      type="button"
                      onClick={() => setLandingQuery("")}
                      className="text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                    >
                      Clear search
                    </button>
                  }
                />
              ) : landingItems.length > 0 ? (
                <VideoList
                  token={token}
                  fromSlug={channelSlug}
                  items={landingPosterItems}
                  currentId={null}
                  onItemSelect={(item) => goTo(item, true, "landing")}
                  startNumber={(landingPaged.page - 1) * CATALOG_PAGE_SIZE + 1}
                />
              ) : selectedGroup ? (
                <EmptyState icon={ListVideo} title="No videos in this group yet" />
              ) : null}
              {landingPaged.totalPages > 1 ? (
                <Pagination
                  page={landingPaged.page}
                  totalPages={landingPaged.totalPages}
                  total={landingPaged.total}
                  perPage={CATALOG_PAGE_SIZE}
                  onPageChange={setLandingPage}
                  itemLabel="video"
                />
              ) : null}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function WatchLayout({
  token,
  fromSlug,
  channelName,
  playlistName,
  items,
  groups,
  current,
  gone,
  ended,
  nextItem,
  markers,
  vttBlobUrl,
  videoRef,
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
  recordingTitle,
  recordingStartTime,
  recordingDuration,
  processedPlayUrl,
  originalPlayUrl,
  mediaExpiresIn,
  mediaIssuedAtMs,
  itemFetching,
  onItemRefetch,
  videoVariant,
  onVideoVariantChange,
  bothVariants,
  onProcessedTimeline,
  onSeek,
  onMarkerSeek,
  onItemSelect,
  onTimeUpdate,
  onGone,
  onEnded,
  autoPlayRequested,
  onAutoPlayAttempt,
  onNext,
  below,
}: {
  token: string;
  fromSlug: string | null;
  channelName: string | null;
  playlistName: string;
  items: PublicPlaylistItem[];
  groups: PublicPlaylistGroup[];
  current: PublicPlaylistItem | undefined;
  gone: boolean;
  ended: boolean;
  nextItem: PublicPlaylistItem | undefined;
  markers: VideoPlayerMarker[];
  vttBlobUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
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
  recordingTitle?: string;
  recordingStartTime?: string;
  recordingDuration?: number;
  processedPlayUrl?: string | null;
  originalPlayUrl?: string | null;
  mediaExpiresIn?: number | null;
  mediaIssuedAtMs: number;
  itemFetching: boolean;
  onItemRefetch: (variant: "processed" | "original") => Promise<string | null>;
  videoVariant: "processed" | "original";
  onVideoVariantChange: (v: "processed" | "original") => void;
  bothVariants: boolean;
  onProcessedTimeline: boolean;
  onSeek: (time: number) => void;
  onMarkerSeek: (time: number, label: string) => void;
  onItemSelect: (item: PublicPlaylistItem) => void;
  onTimeUpdate: (time: number) => void;
  onGone: () => void;
  onEnded: () => void;
  autoPlayRequested: boolean;
  onAutoPlayAttempt: () => void;
  onNext: () => void;
  below?: React.ReactNode;
}) {
  const { theater, setTheater } = useWatchTheater();
  const [autoplayNext, setAutoplayNext] = useState(readPlaylistAutoplayNext);
  const [sidebarQuery, setSidebarQuery] = useState("");
  const [sidebarGroupId, setSidebarGroupId] = useState<number | null>(current?.group_id ?? null);
  const [sidebarForItemId, setSidebarForItemId] = useState(current?.id);
  if (sidebarForItemId !== current?.id) {
    setSidebarForItemId(current?.id);
    setSidebarGroupId(current?.group_id ?? null);
  }
  const sidebarItems = useMemo(
    () => catalogPlaylistItems(
      sidebarGroupId === null ? items : items.filter((item) => item.group_id === sidebarGroupId),
      sidebarQuery,
      "order",
    ),
    [items, sidebarQuery, sidebarGroupId],
  );
  const playable = !!current?.playable && !gone;
  const currentGroup = groups.find((group) => group.id === current?.group_id);
  const showEndCard = playable && ended;
  const dateLabel = formatDate(recordingStartTime ?? current?.start_time);
  const durationLabel = formatDuration(recordingDuration || current?.duration || 0);
  const companionBody =
    activeTab === "videos" ? (
      <div className="flex min-h-0 flex-col gap-3">
        {items.length > 0 && (
          <SearchInput
            id="playlist-sidebar-search"
            value={sidebarQuery}
            onChange={setSidebarQuery}
            placeholder="Search videos…"
          />
        )}
        {groups.length > 0 && (
          <select
            aria-label="Playlist group"
            value={sidebarGroupId ?? ""}
            onChange={(event) => setSidebarGroupId(event.target.value ? Number(event.target.value) : null)}
            className={cn(FILTER_CONTROL, "w-full text-sm")}
          >
            <option value="">All groups</option>
            {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
          </select>
        )}
        {items.length > 0 && sidebarItems.length === 0 && sidebarQuery.trim() ? (
          <EmptyState
            icon={ListVideo}
            className="py-8"
            title={`No results for “${sidebarQuery.trim()}”`}
            description="Try a different search."
            action={
              <button
                type="button"
                onClick={() => setSidebarQuery("")}
                className="text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
              >
                Clear search
              </button>
            }
          />
        ) : (
          <VideoList
            token={token}
            fromSlug={fromSlug}
            items={sidebarItems}
            currentId={current?.id ?? null}
            onItemSelect={onItemSelect}
            embedded
          />
        )}
      </div>
    ) : activeTab === "topics" && hasTopicsPanel && topicVersion ? (
      <AIContentEditor
        key={recordingId ?? 0}
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
        listClassName="min-h-0 flex-1 overflow-y-auto"
      />
    ) : null;

  const overlay = (showEndCard || gone) ? (
    <div className="plyr__leap-endcard motion-safe:plyr__leap-hud-in">
      {gone ? (
        <>
          <p>This video is unavailable</p>
          {nextItem ? (
            <button
              type="button"
              autoFocus
              onClick={onNext}
              className="pressable rounded-xl bg-white px-4 py-2 text-sm font-medium text-black"
            >
              Play next
            </button>
          ) : null}
        </>
      ) : nextItem ? (
        <>
          <p>Up next</p>
          <h2>{nextItem.title}</h2>
          <label className="flex items-center gap-2 text-xs text-white/90">
            <input
              type="checkbox"
              checked={autoplayNext}
              onChange={(e) => {
                setAutoplayNext(e.target.checked);
                writePlaylistAutoplayNext(e.target.checked);
              }}
              className="rounded border-white/40"
            />
            Play next automatically
          </label>
          <button
            type="button"
            autoFocus
            onClick={onNext}
            className="pressable rounded-xl bg-white px-4 py-2 text-sm font-medium text-black"
          >
            Play next
          </button>
        </>
      ) : (
        <p>End of playlist</p>
      )}
    </div>
  ) : undefined;

  const player = playable && current ? (
    <PlaylistVideoPlayer
      token={token}
      itemId={current.id}
      variant={videoVariant}
      processedPlayUrl={processedPlayUrl}
      originalPlayUrl={originalPlayUrl}
      mediaExpiresIn={mediaExpiresIn}
      mediaIssuedAtMs={mediaIssuedAtMs}
      itemFetching={itemFetching}
      onItemRefetch={onItemRefetch}
      markers={markers}
      vttBlobUrl={vttBlobUrl}
      videoRef={videoRef}
      onTimeUpdate={onTimeUpdate}
      onGone={onGone}
      onEnded={onEnded}
      onMarkerSeek={onMarkerSeek}
      autoPlayRequested={autoPlayRequested}
      onAutoPlayAttempt={onAutoPlayAttempt}
      overlay={overlay}
    />
  ) : (
    <div
      role="status"
      className={cn(
        VIDEO_PLAYER_FRAME,
        "flex flex-col items-center justify-center gap-2 rounded-none outline-none text-sm text-muted-foreground",
      )}
    >
      <VideoOff size={18} />
      <span>{current ? "This video is unavailable" : "This video is not in the playlist"}</span>
      {nextItem && (
        <button type="button" onClick={onNext} className="text-sm text-primary hover:underline">
          Play next
        </button>
      )}
    </div>
  );

  return (
    <WatchStage
      player={player}
      title={
        <div>
          <nav aria-label="Video location" className="mb-2 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
            {fromSlug && (
              <>
                <Link href={`/c/${fromSlug}`} className="min-w-0 max-w-full break-words font-medium text-primary hover:text-primary-hover hover:underline">
                  {channelName ?? fromSlug}
                </Link>
                <span aria-hidden>/</span>
              </>
            )}
            <Link href={playlistLandingHref(token, fromSlug)} className="min-w-0 max-w-full break-words font-medium text-primary hover:text-primary-hover hover:underline">
              {playlistName}
            </Link>
            {currentGroup && (
              <>
                <span aria-hidden>/</span>
                <Link href={playlistLandingHref(token, fromSlug, currentGroup.id)}
                  className="min-w-0 max-w-full break-words font-medium text-primary hover:text-primary-hover hover:underline">{currentGroup.name}</Link>
              </>
            )}
          </nav>
          <h1 className="text-xl font-semibold tracking-tight break-words text-foreground sm:text-2xl">
            {recordingTitle ?? current?.title ?? "Video unavailable"}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-2">
              <Clock size={13} />
              <span>{dateLabel}</span>
              {durationLabel && (
                <>
                  <span aria-hidden="true" className="text-border">·</span>
                  <span>{durationLabel}</span>
                </>
              )}
            </span>
          </div>
          <WatchVideoVariantChrome
            bothVariants={bothVariants}
            variant={videoVariant}
            onVariantChange={onVideoVariantChange}
            showTimelineHint={!onProcessedTimeline && (hasTopicsPanel || hasTranscript)}
          />
        </div>
      }
      theater={theater}
      onTheaterChange={setTheater}
      companion={
        <>
          {sidePanelTabs.length > 1 ? (
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
          ) : (
            <h2 className="shrink-0 border-b border-border px-5 pb-3 pt-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {sidePanelTabs[0]?.label}
            </h2>
          )}
          <div
            role="tabpanel"
            id={companionPanelId}
            aria-labelledby={sidePanelTabs.length > 1 ? `${companionPanelId}-tab-${activeTab}` : undefined}
            className={cn(
              activeTab === "videos" ? COMPANION_BODY : COMPANION_BODY_PINNED,
              activeTab === "videos" && "px-3",
            )}
          >
            {companionBody}
          </div>
        </>
      }
      below={below}
    />
  );
}

function VideoList({
  token,
  fromSlug,
  items,
  currentId,
  onItemSelect,
  sticky = false,
  embedded = false,
  startNumber,
}: {
  token: string;
  fromSlug: string | null;
  items: PublicPlaylistItem[];
  currentId: number | null;
  onItemSelect?: (item: PublicPlaylistItem) => void;
  sticky?: boolean;
  embedded?: boolean;
  /** 1-based index of the first visible row. Omit to show saved playlist position. */
  startNumber?: number;
}) {
  const list = (
    <ol className="space-y-1">
      {items.map((item, i) => {
        const active = currentId === item.id;
        const status = itemStatus(item);
        const date = formatDate(item.start_time);
        const n = startNumber != null ? startNumber + i : item.position + 1;
        const rowClass = cn(
          "pressable pressable-block flex w-full min-h-11 min-w-0 items-center gap-3 rounded-xl p-2 text-left",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
          active && "bg-muted",
          !item.playable && "cursor-not-allowed opacity-60",
          item.playable && !active && "hover:bg-muted/70",
        );
        const body = (
          <>
            <span className="w-7 shrink-0 text-center text-xs tabular-nums text-muted-foreground">{n}</span>
            <Thumb
              src={item.poster_url}
              posterAssetKey={item.poster_asset_key}
              duration={item.duration}
              active={active && item.playable}
            />
            <span className="min-w-0 flex-1">
              <span className={cn("line-clamp-2 text-sm font-medium leading-snug text-foreground", !item.playable && "text-muted-foreground")}>
                {item.title}
              </span>
              {(date !== "—" || status) && (
                <span className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                  {date !== "—" ? <span className="tabular-nums">{date}</span> : null}
                  {status && <span>{status}</span>}
                </span>
              )}
            </span>
          </>
        );
        return (
          <li key={item.id}>
            {item.playable ? (
              onItemSelect ? (
                <button
                  type="button"
                  aria-current={active ? "true" : undefined}
                  onClick={() => {
                    onItemSelect(item);
                  }}
                  className={rowClass}
                >
                  {body}
                </button>
              ) : (
                <Link
                  href={playlistWatchHref(token, item.id, fromSlug, item.group_id)}
                  aria-current={active ? "true" : undefined}
                  className={rowClass}
                >
                  {body}
                </Link>
              )
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
      <div aria-label="Playlist videos">
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
