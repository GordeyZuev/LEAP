"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Calendar, ChevronRight, Clock, LayoutGrid, List, ListVideo, Radio } from "lucide-react";

import { getPublicChannel, sendChannelPageBeacon } from "@/api/share";
import { FilterSelect } from "@/components/filters/filter-select";
import { SearchInput } from "@/components/filters/search-input";
import { PlaylistStackPoster } from "@/components/playlists/playlist-stack-poster";
import { StablePosterImage } from "@/components/recordings/recording-poster";
import { PUBLIC_PAGE_MAIN } from "@/components/share/public-share-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Pagination } from "@/components/ui/pagination";
import { ExpandableFormattedText, FormattedText } from "@/components/ui/formatted-text";
import { Tabs } from "@/components/ui/tabs";
import { CARD_INTERACTIVE, CARD_SHELL } from "@/components/ui/section-card";
import {
  CHANNEL_PLAYLIST_SORT,
  CHANNEL_VIDEO_SORT,
  channelVideoSearchName,
  parseChannelPlaylistSort,
  parseChannelVideoSort,
  sortChannelPlaylists,
  sortChannelVideos,
  type ChannelPlaylistSort,
  type ChannelVideoSort,
} from "@/lib/channel-catalog";
import { CHANNEL_BANNER_FRAME, CHANNEL_BANNER_IMG } from "@/lib/constants";
import { CATALOG_PAGE_SIZE, paginateItems, parseCatalogPage } from "@/lib/catalog-page";
import { FILTER_LABEL } from "@/lib/filter-field-classes";
import { cn, formatDate, formatDurationCompact, httpStatus } from "@/lib/utils";

const CATALOG_CARD = cn("flex flex-col overflow-hidden p-4", CARD_SHELL, CARD_INTERACTIVE);
const CATALOG_ROW = cn(
  "flex items-start gap-4 overflow-hidden rounded-[1.25rem] border border-border bg-card p-3 shadow-sm",
  CARD_INTERACTIVE,
);
const GRID = "grid grid-cols-[repeat(auto-fill,minmax(min(16rem,100%),1fr))] gap-4";
const LIST = "flex flex-col gap-3";
const CATALOG_PANEL = "channel-catalog";
const VIEW_BTN =
  "pressable flex size-9 items-center justify-center rounded-lg border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";
const VIEW_ON = "border-primary bg-primary text-white";
const VIEW_OFF = "border-border bg-card text-muted-foreground hover:bg-muted";

type Tab = "videos" | "playlists";
type ViewMode = "grid" | "list";

function matchesQuery(haystack: string, q: string): boolean {
  if (!q) return true;
  return haystack.toLowerCase().includes(q.trim().toLowerCase());
}

function DurationBadge({ seconds }: { seconds: number | null | undefined }) {
  const dur = formatDurationCompact(seconds);
  if (!dur) return null;
  return (
    <span className="pointer-events-none absolute bottom-1.5 end-1.5 rounded-md bg-black/75 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-white">
      {dur}
    </span>
  );
}

function ListBlurb({ text }: { text?: string | null }) {
  if (!text?.trim()) return null;
  return (
    <FormattedText
      text={text}
      className="mt-2 line-clamp-2 text-sm leading-snug text-muted-foreground"
    />
  );
}

function ListMeta({
  items,
}: {
  items: { icon: typeof Calendar; text: string }[];
}) {
  if (items.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {items.map(({ icon: Icon, text }) => (
        <span key={text} className="inline-flex items-center gap-1.5">
          <Icon size={12} strokeWidth={2} className="shrink-0 text-muted-foreground/80" aria-hidden />
          <span className="tabular-nums">{text}</span>
        </span>
      ))}
    </div>
  );
}

function parseView(raw: string | null): ViewMode {
  return raw === "list" ? "list" : "grid";
}

function writeParams(next: { tab: Tab; q: string; sort: string; view: ViewMode; page: number }) {
  const url = new URL(window.location.href);
  if (next.tab === "videos") url.searchParams.set("tab", "videos");
  else url.searchParams.delete("tab");
  if (next.q.trim()) url.searchParams.set("q", next.q.trim());
  else url.searchParams.delete("q");
  if (next.sort !== "order") url.searchParams.set("sort", next.sort);
  else url.searchParams.delete("sort");
  if (next.view === "list") url.searchParams.set("view", "list");
  else url.searchParams.delete("view");
  if (next.page > 1) url.searchParams.set("page", String(next.page));
  else url.searchParams.delete("page");
  window.history.replaceState(null, "", url.toString());
}

export function ChannelPublicView({ slug }: { slug: string }) {
  const sp = useSearchParams();
  const [tab, setTab] = useState<Tab>(sp.get("tab") === "videos" ? "videos" : "playlists");
  const [query, setQuery] = useState(sp.get("q") ?? "");
  const [videoSort, setVideoSort] = useState<ChannelVideoSort>(parseChannelVideoSort(sp.get("sort")));
  const [playlistSort, setPlaylistSort] = useState<ChannelPlaylistSort>(parseChannelPlaylistSort(sp.get("sort")));
  const [view, setView] = useState<ViewMode>(parseView(sp.get("view")));
  const [catalogPage, setCatalogPage] = useState(() => parseCatalogPage(sp.get("page")));
  const catalogFilterKey = `${tab}\0${query}\0${tab === "videos" ? videoSort : playlistSort}`;
  const [appliedFilterKey, setAppliedFilterKey] = useState(catalogFilterKey);
  if (appliedFilterKey !== catalogFilterKey) {
    setAppliedFilterKey(catalogFilterKey);
    if (catalogPage !== 1) setCatalogPage(1);
  }

  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["public-channel", slug],
    queryFn: () => getPublicChannel(slug),
    retry: false,
  });

  useEffect(() => {
    void sendChannelPageBeacon(slug).catch(() => {});
  }, [slug]);

  const sort = tab === "videos" ? videoSort : playlistSort;

  const videos = useMemo(() => {
    if (!data) return [];
    const q = query.trim();
    const filtered = data.videos.filter((v) =>
      matchesQuery(`${channelVideoSearchName(v.title)} ${v.blurb ?? ""}`, q),
    );
    return sortChannelVideos(filtered, videoSort);
  }, [data, query, videoSort]);

  const playlists = useMemo(() => {
    if (!data) return [];
    const q = query.trim();
    const filtered = data.playlists.filter((p) => matchesQuery(`${p.name} ${p.blurb ?? ""}`, q));
    return sortChannelPlaylists(filtered, playlistSort);
  }, [data, query, playlistSort]);

  const pagingPage = appliedFilterKey !== catalogFilterKey ? 1 : catalogPage;
  const pagedVideos = paginateItems(videos, pagingPage);
  const pagedPlaylists = paginateItems(playlists, pagingPage);
  const catalogPaged = tab === "videos" ? pagedVideos : pagedPlaylists;

  useEffect(() => {
    if (!data) return;
    writeParams({ tab, q: query, sort, view, page: catalogPaged.page });
  }, [data, tab, query, sort, view, catalogPaged.page]);

  if (httpStatus(error) === 404) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center px-6">
        <ErrorState title="Link not found" description="This channel is not shared, or it never existed." />
      </div>
    );
  }
  if (error && !data) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center px-6">
        <ErrorState title="Unable to load this channel" onRetry={() => void refetch()} />
      </div>
    );
  }
  if (isPending || !data) {
    return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
  }

  const catalogEmpty = tab === "videos" ? data.videos.length === 0 : data.playlists.length === 0;
  const filteredEmpty = tab === "videos" ? videos.length === 0 : playlists.length === 0;
  const searching = query.trim().length > 0;

  return (
    <div>
      {data.banner_url ? (
        <div className={CHANNEL_BANNER_FRAME}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={data.banner_url} alt="" className={CHANNEL_BANNER_IMG} />
        </div>
      ) : null}
      <main className={PUBLIC_PAGE_MAIN}>
        <h1
          className={
            data.description
              ? "mb-2 text-xl font-semibold tracking-tight text-foreground sm:text-2xl"
              : "mb-6 text-xl font-semibold tracking-tight text-foreground sm:text-2xl"
          }
        >
          {data.name}
        </h1>
        {data.description ? (
          <ExpandableFormattedText text={data.description} className="mb-6" />
        ) : null}

        <Tabs
          label="Channel contents"
          idPrefix="channel-contents"
          panelId={CATALOG_PANEL}
          value={tab}
          onChange={setTab}
          items={[
            { value: "playlists", label: "Playlists" },
            { value: "videos", label: "Videos" },
          ]}
          hidePanel
        >
          {null}
        </Tabs>

        {!catalogEmpty && (
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
            <SearchInput
              id="channel-catalog-search"
              className="min-w-0 sm:min-w-[15rem] sm:flex-[2]"
              value={query}
              onChange={setQuery}
              placeholder={tab === "videos" ? "Search videos…" : "Search playlists…"}
            />
            <div className="min-w-0 sm:min-w-[11rem] sm:flex-1">
              <label htmlFor="channel-catalog-sort" className={FILTER_LABEL}>
                Sort by
              </label>
              {tab === "videos" ? (
                <FilterSelect
                  id="channel-catalog-sort"
                  value={videoSort}
                  options={[...CHANNEL_VIDEO_SORT]}
                  onChange={(v) => setVideoSort(v as ChannelVideoSort)}
                  filled={videoSort !== "order"}
                />
              ) : (
                <FilterSelect
                  id="channel-catalog-sort"
                  value={playlistSort}
                  options={[...CHANNEL_PLAYLIST_SORT]}
                  onChange={(v) => setPlaylistSort(v as ChannelPlaylistSort)}
                  filled={playlistSort !== "order"}
                />
              )}
            </div>
            <div className="flex shrink-0 flex-col">
              <span className={FILTER_LABEL} id="channel-catalog-view-label">
                View
              </span>
              <div
                role="group"
                aria-labelledby="channel-catalog-view-label"
                className="flex h-[2.875rem] items-center gap-1.5"
              >
                <button
                  type="button"
                  title="Grid view"
                  aria-label="Grid view"
                  aria-pressed={view === "grid"}
                  onClick={() => setView("grid")}
                  className={cn(VIEW_BTN, view === "grid" ? VIEW_ON : VIEW_OFF)}
                >
                  <LayoutGrid size={14} />
                </button>
                <button
                  type="button"
                  title="List view"
                  aria-label="List view"
                  aria-pressed={view === "list"}
                  onClick={() => setView("list")}
                  className={cn(VIEW_BTN, view === "list" ? VIEW_ON : VIEW_OFF)}
                >
                  <List size={14} />
                </button>
              </div>
            </div>
          </div>
        )}

        <div role="tabpanel" id={CATALOG_PANEL} aria-labelledby={`channel-contents-tab-${tab}`}>
          {catalogEmpty && (
            <EmptyState
              icon={Radio}
              title={tab === "videos" ? "No videos yet" : "No playlists yet"}
              description="Nothing is shared on this tab."
            />
          )}
          {!catalogEmpty && filteredEmpty && searching && (
            <EmptyState
              icon={Radio}
              title={`No results for “${query.trim()}”`}
              description="Try a different search."
              action={
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                >
                  Clear search
                </button>
              }
            />
          )}
          {tab === "videos" && videos.length > 0 && (
            <ul className={view === "grid" ? GRID : LIST}>
              {pagedVideos.items.map((v) => {
                const name = channelVideoSearchName(v.title);
                const href = `/share/${v.share_token}?from=${encodeURIComponent(slug)}`;
                const date = formatDate(v.start_time);
                const duration = formatDurationCompact(v.duration);
                const list = view === "list";
                return (
                  <li key={v.share_token}>
                    <Link href={href} className={list ? CATALOG_ROW : CATALOG_CARD}>
                      <div className={cn("relative shrink-0", list ? "w-40 sm:w-52" : "mb-3 w-full")}>
                        <StablePosterImage
                          posterUrl={v.poster_url}
                          posterAssetKey={v.poster_asset_key}
                          className="aspect-video w-full rounded-lg"
                          placeholderIconSize={list ? 22 : 28}
                        />
                        {list ? <DurationBadge seconds={v.duration} /> : null}
                      </div>
                      <div className="min-w-0 flex-1">
                        <h2
                          className={cn(
                            "line-clamp-2 font-semibold leading-snug text-foreground",
                            list ? "text-base" : "text-sm",
                          )}
                        >
                          {name}
                        </h2>
                        {list ? (
                          <>
                            <ListMeta
                              items={[
                                ...(date !== "—" ? [{ icon: Calendar, text: date }] : []),
                                ...(duration ? [{ icon: Clock, text: duration }] : []),
                              ]}
                            />
                            <ListBlurb text={v.blurb} />
                          </>
                        ) : date !== "—" || duration ? (
                          <p className="mt-1 text-xs text-muted-foreground">
                            {date !== "—" ? <span className="tabular-nums">{date}</span> : null}
                            {date !== "—" && duration ? " · " : null}
                            {duration}
                          </p>
                        ) : null}
                      </div>
                      {list ? (
                        <ChevronRight
                          size={18}
                          className="mt-3 hidden shrink-0 text-muted-foreground/40 sm:block"
                          aria-hidden
                        />
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          {tab === "playlists" && playlists.length > 0 && (
            <ul className={view === "grid" ? GRID : LIST}>
              {pagedPlaylists.items.map((p) => {
                const href = `/share/p/${p.share_token}?from=${encodeURIComponent(slug)}`;
                const duration = formatDurationCompact(p.duration_sum);
                const list = view === "list";
                const videoLabel = `${p.video_count} ${p.video_count === 1 ? "video" : "videos"}`;
                return (
                  <li key={p.share_token}>
                    <Link href={href} className={list ? CATALOG_ROW : CATALOG_CARD}>
                      <PlaylistStackPoster
                        posterUrl={p.poster_url}
                        posterAssetKey={p.poster_asset_key}
                        videoCount={p.video_count}
                        size={list ? "sm" : "md"}
                        wrapperClassName={list ? "w-40 shrink-0 sm:w-52" : "mb-3"}
                        className="aspect-video w-full rounded-lg"
                      />
                      <div className="min-w-0 flex-1">
                        <h2
                          className={cn(
                            "line-clamp-2 font-semibold leading-snug text-foreground",
                            list ? "text-base" : "text-sm",
                          )}
                        >
                          {p.name}
                        </h2>
                        {list ? (
                          <>
                            <ListMeta
                              items={[
                                { icon: ListVideo, text: videoLabel },
                                ...(duration ? [{ icon: Clock, text: duration }] : []),
                              ]}
                            />
                            <ListBlurb text={p.blurb} />
                          </>
                        ) : duration ? (
                          <p className="mt-1 text-xs text-muted-foreground">{duration}</p>
                        ) : null}
                      </div>
                      {list ? (
                        <ChevronRight
                          size={18}
                          className="mt-3 hidden shrink-0 text-muted-foreground/40 sm:block"
                          aria-hidden
                        />
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          {catalogPaged.totalPages > 1 ? (
            <Pagination
              page={catalogPaged.page}
              totalPages={catalogPaged.totalPages}
              total={catalogPaged.total}
              perPage={CATALOG_PAGE_SIZE}
              onPageChange={setCatalogPage}
              itemLabel={tab === "videos" ? "video" : "playlist"}
            />
          ) : null}
        </div>
      </main>
    </div>
  );
}
