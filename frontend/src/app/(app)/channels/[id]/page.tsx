"use client";

import { Suspense, use, useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, GripVertical, ListVideo, Plus, Trash2 } from "lucide-react";

import {
  addChannelPlaylists,
  addChannelVideos,
  deleteChannel,
  deleteChannelBanner,
  disableChannelShare,
  enableChannelShare,
  getChannel,
  listChannelPlaylists,
  listChannelVideos,
  removeChannelPlaylist,
  removeChannelVideo,
  reorderChannelPlaylists,
  reorderChannelVideos,
  updateChannel,
  uploadChannelBanner,
  type ChannelPlaylistRow,
} from "@/api/channels";
import { apiClient } from "@/api/client";
import { listPlaylists } from "@/api/playlists";
import { SearchInput } from "@/components/filters/search-input";
import { StablePosterImage } from "@/components/recordings/recording-poster";
import { PlaylistStackPoster } from "@/components/playlists/playlist-stack-poster";
import { ShareAnalyticsPanel } from "@/components/recordings/share-analytics-panel";
import { ShareAccessCard } from "@/components/share/share-access-card";
import { ShareAnalyticsPlaque } from "@/components/share/share-analytics-plaque";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DescriptionEditor } from "@/components/ui/description-editor";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Field } from "@/components/ui/field";
import { FormattedText } from "@/components/ui/formatted-text";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { CARD_SHELL, SectionCard } from "@/components/ui/section-card";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { Toast } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { CHANNEL_BANNER_ASPECT } from "@/lib/constants";
import { CHECKBOX } from "@/lib/filter-field-classes";
import { CHANNEL_JINJA_VARS, interpolateChannelDescription } from "@/lib/formatted-text";
import { cn, extractApiError, formatDurationCompact } from "@/lib/utils";

function channelUrl(slug: string): string {
  if (typeof window === "undefined") return `/c/${slug}`;
  return `${window.location.origin}/c/${slug}`;
}

interface RecordingPick {
  id: number;
  display_name: string;
  duration: number;
}

function playlistShareUrl(token: string): string {
  if (typeof window === "undefined") return `/share/p/${token}`;
  return `${window.location.origin}/share/p/${token}`;
}

type PageTab = "content" | "channel" | "analytics";
const PAGE_TABS: TabItem<PageTab>[] = [
  { value: "content", label: "Content" },
  { value: "channel", label: "Settings" },
  { value: "analytics", label: "Analytics" },
];

const ROW_LINK =
  "text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm";

function HiddenLink({ reason, href }: { reason: string | null; href: string }) {
  if (!reason) return null;
  return (
    <Link href={href} className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:underline">
      Hidden · {reason}
    </Link>
  );
}

export default function ChannelEditorPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading channel…</div>}>
      <ChannelEditor params={params} />
    </Suspense>
  );
}

function ChannelEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const channelId = Number(id);
  const router = useRouter();
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const { toast, show, dismiss } = useToast();
  const rawPage = searchParams.get("tab");
  const pageTab: PageTab = rawPage === "channel" || rawPage === "analytics" ? rawPage : "content";
  const goPage = useCallback((next: PageTab) => {
    const p = new URLSearchParams(window.location.search);
    if (next === "content") p.delete("tab");
    else p.set("tab", next);
    const qs = p.toString();
    router.replace(qs ? `?${qs}` : window.location.pathname, { scroll: false });
  }, [router]);
  const [tab, setTab] = useState<"videos" | "playlists">("playlists");
  const [nameEditing, setNameEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [slugDraft, setSlugDraft] = useState<string | null>(null);
  const [slugConfirm, setSlugConfirm] = useState(false);
  const [descDraft, setDescDraft] = useState<string | null>(null);
  const [addVideosOpen, setAddVideosOpen] = useState(false);
  const [addPlaylistsOpen, setAddPlaylistsOpen] = useState(false);
  const [addSearch, setAddSearch] = useState("");
  const [addSelected, setAddSelected] = useState<Set<number>>(new Set());
  const [disableConfirm, setDisableConfirm] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copiedPlaylistId, setCopiedPlaylistId] = useState<number | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);

  const { data: channel, isLoading, error, refetch } = useQuery({
    queryKey: ["channel", channelId],
    queryFn: () => getChannel(channelId),
    enabled: Number.isFinite(channelId),
  });

  const videosQuery = useQuery({
    queryKey: ["channel-videos", channelId],
    queryFn: () => listChannelVideos(channelId, { per_page: 200 }),
    enabled: Number.isFinite(channelId),
  });
  const playlistsQuery = useQuery({
    queryKey: ["channel-playlists", channelId],
    queryFn: () => listChannelPlaylists(channelId, { per_page: 200 }),
    enabled: Number.isFinite(channelId),
  });

  const videos = useMemo(() => videosQuery.data?.items ?? [], [videosQuery.data?.items]);
  const playlists = useMemo(() => playlistsQuery.data?.items ?? [], [playlistsQuery.data?.items]);
  const publicUrl = channel ? channelUrl(channel.slug) : null;

  const recordingsQuery = useQuery({
    queryKey: ["recordings-picker", addSearch],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (addSearch) p.set("search", addSearch);
      p.set("per_page", "50");
      const res = await apiClient.get<{ items: RecordingPick[] }>(`/recordings?${p.toString()}`);
      return res.data.items;
    },
    enabled: addVideosOpen,
  });

  const playlistPickQuery = useQuery({
    queryKey: ["playlists", "picker", addSearch],
    queryFn: () => listPlaylists({ per_page: 100, q: addSearch || undefined, sort_by: "name", sort_order: "asc" }),
    enabled: addPlaylistsOpen,
  });

  const inVideos = useMemo(() => new Set(videos.map((v) => v.recording_id)), [videos]);
  const inPlaylists = useMemo(() => new Set(playlists.map((p) => p.playlist_id)), [playlists]);

  const rename = useMutation({
    mutationFn: (name: string) => updateChannel(channelId, { name }),
    onSuccess: () => {
      setNameEditing(false);
      void qc.invalidateQueries({ queryKey: ["channel", channelId] });
      void qc.invalidateQueries({ queryKey: ["channels"] });
    },
    onError: (e) => show("error", extractApiError(e, "Could not rename.")),
  });
  const saveSlug = useMutation({
    mutationFn: (slug: string) => updateChannel(channelId, { slug }),
    onSuccess: () => {
      setSlugDraft(null);
      setSlugConfirm(false);
      void qc.invalidateQueries({ queryKey: ["channel", channelId] });
      void qc.invalidateQueries({ queryKey: ["channels"] });
      show("success", "Slug updated. The old URL no longer works.");
    },
    onError: (e) => show("error", extractApiError(e, "Could not change slug.")),
  });
  const saveDesc = useMutation({
    mutationFn: (description: string | null) => updateChannel(channelId, { description }),
    onSuccess: () => {
      setDescDraft(null);
      void qc.invalidateQueries({ queryKey: ["channel", channelId] });
    },
  });
  const enableShare = useMutation({
    mutationFn: () => enableChannelShare(channelId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["channel", channelId] });
      void qc.invalidateQueries({ queryKey: ["channels"] });
    },
  });
  const disableShare = useMutation({
    mutationFn: () => disableChannelShare(channelId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["channel", channelId] });
      void qc.invalidateQueries({ queryKey: ["channels"] });
      setDisableConfirm(false);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteChannel(channelId),
    onSuccess: () => router.push("/channels"),
  });

  async function copyLink() {
    if (!publicUrl) return;
    await navigator.clipboard.writeText(publicUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function copyPlaylistLink(playlistId: number, token: string) {
    await navigator.clipboard.writeText(playlistShareUrl(token));
    setCopiedPlaylistId(playlistId);
    setTimeout(() => setCopiedPlaylistId(null), 2000);
  }

  async function dropVideo(targetId: number, fromId?: number) {
    if (!fromId || fromId === targetId) return;
    const ids = videos.map((v) => v.recording_id);
    const fromIdx = ids.indexOf(fromId);
    const toIdx = ids.indexOf(targetId);
    if (fromIdx < 0 || toIdx < 0) return;
    ids.splice(fromIdx, 1);
    ids.splice(toIdx, 0, fromId);
    await reorderChannelVideos(channelId, ids);
    void qc.invalidateQueries({ queryKey: ["channel-videos", channelId] });
  }

  async function dropPlaylist(targetId: number, fromId?: number) {
    if (!fromId || fromId === targetId) return;
    const ids = playlists.map((p) => p.playlist_id);
    const fromIdx = ids.indexOf(fromId);
    const toIdx = ids.indexOf(targetId);
    if (fromIdx < 0 || toIdx < 0) return;
    ids.splice(fromIdx, 1);
    ids.splice(toIdx, 0, fromId);
    await reorderChannelPlaylists(channelId, ids);
    void qc.invalidateQueries({ queryKey: ["channel-playlists", channelId] });
  }

  if (isLoading) return <div className="p-8 text-sm text-muted-foreground">Loading channel…</div>;
  if (error || !channel) {
    return <ErrorState title="Channel not found" onRetry={() => void refetch()} />;
  }

  const descriptionValue = descDraft ?? channel.description ?? "";
  const slugValue = slugDraft ?? channel.slug;
  const descriptionPreview = interpolateChannelDescription(descriptionValue, {
    videoCount: videos.length,
    playlistCount: playlists.length,
    durationSeconds: videos.reduce((sum, v) => sum + v.duration, 0),
    videoTitles: videos.map((v) => v.title),
    playlistNames: playlists.map((p) => p.name),
  });

  const aside = (
    <aside className="min-w-0 lg:sticky lg:top-6">
      <ShareAccessCard
        headingId="channel-access-heading"
        active={channel.share_enabled}
        hasToken={true}
        publicUrl={publicUrl}
        copied={copied}
        enablePending={enableShare.isPending}
        onCopy={() => void copyLink()}
        onEnable={() => enableShare.mutate()}
        onDisable={() => setDisableConfirm(true)}
        hintActive={`One permanent link /c/${channel.slug}. Disable keeps the same address.`}
        hintDisabled="Enabling again uses the same slug."
        hintNever="Share stays off until the showcase is ready."
      />
      {pageTab !== "analytics" && (
        <ShareAnalyticsPlaque
          subject={{ kind: "channel", id: channelId }}
          onOpenDetails={() => goPage("analytics")}
        />
      )}
    </aside>
  );

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <Link href="/channels" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft size={14} /> Channels
      </Link>
      <PageHeader
        title={channel.name}
        description={`${channel.video_count} videos · ${channel.playlist_count} playlists`}
      />
      <Tabs items={PAGE_TABS} value={pageTab} onChange={goPage} label="Channel sections">
        {pageTab === "content" && (
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <SectionCard
          title={tab === "playlists" ? "Playlists" : "Videos"}
          description="Same tabs as the public page. Drag to reorder."
          className="min-w-0"
          action={
            <ActionButton
              size="sm"
              variant="secondary"
              icon={<Plus size={12} />}
              onClick={() => {
                setAddSelected(new Set());
                setAddSearch("");
                if (tab === "playlists") setAddPlaylistsOpen(true);
                else setAddVideosOpen(true);
              }}
            >
              {tab === "playlists" ? "Add playlists" : "Add videos"}
            </ActionButton>
          }
        >
          <Tabs
            label="Channel tabs"
            hidePanel
            value={tab}
            onChange={(v) => setTab(v as "videos" | "playlists")}
            items={[
              { value: "playlists", label: "Playlists" },
              { value: "videos", label: "Videos" },
            ]}
          >
            {null}
          </Tabs>
          {tab === "videos" && videos.length === 0 && (
            <EmptyState
              icon={Plus}
              title="No videos yet"
              description="Add recordings to the Videos tab. Viewers only see items with a share link."
              action={
                <ActionButton size="sm" icon={<Plus size={12} />} onClick={() => { setAddSelected(new Set()); setAddSearch(""); setAddVideosOpen(true); }}>
                  Add videos
                </ActionButton>
              }
            />
          )}
          {tab === "videos" && videos.length > 0 && (
            <ul className="divide-y divide-border">
              {videos.map((item) => (
                <li
                  key={item.recording_id}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    void dropVideo(item.recording_id, Number(e.dataTransfer.getData("text/plain")));
                    setDraggingId(null);
                  }}
                  className={cn("flex items-center gap-3 py-3", draggingId === item.recording_id && "opacity-50")}
                >
                  <button
                    type="button"
                    draggable
                    aria-label="Reorder"
                    onDragStart={(e) => {
                      setDraggingId(item.recording_id);
                      e.dataTransfer.setData("text/plain", String(item.recording_id));
                    }}
                    className="flex size-11 shrink-0 cursor-grab items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"
                  >
                    <GripVertical size={16} />
                  </button>
                  <div className="w-28 shrink-0">
                    <StablePosterImage posterUrl={item.poster_url} posterAssetKey={item.poster_asset_key} className="aspect-video w-full" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <Link href={`/recordings/${item.recording_id}`} className="block truncate text-sm font-medium hover:underline">
                      {item.title}
                    </Link>
                    <p className="text-xs text-muted-foreground">{formatDurationCompact(item.duration)}</p>
                    <HiddenLink reason={item.hidden_reason} href={`/recordings/${item.recording_id}`} />
                  </div>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hover:text-danger-fg"
                    onClick={() =>
                      void removeChannelVideo(channelId, item.recording_id).then(() =>
                        qc.invalidateQueries({ queryKey: ["channel-videos", channelId] }),
                      )
                    }
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
          {tab === "playlists" && playlists.length === 0 && (
            <EmptyState
              icon={ListVideo}
              title="No playlists yet"
              description="Attach courses. Viewers only see shared playlists."
              action={
                <ActionButton size="sm" icon={<Plus size={12} />} onClick={() => { setAddSelected(new Set()); setAddSearch(""); setAddPlaylistsOpen(true); }}>
                  Add playlists
                </ActionButton>
              }
            />
          )}
          {tab === "playlists" && playlists.length > 0 && (
            <ul className="divide-y divide-border">
              {playlists.map((item: ChannelPlaylistRow) => (
                <li
                  key={item.playlist_id}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    void dropPlaylist(item.playlist_id, Number(e.dataTransfer.getData("text/plain")));
                    setDraggingId(null);
                  }}
                  className={cn("flex items-center gap-3 py-3", draggingId === item.playlist_id && "opacity-50")}
                >
                  <button
                    type="button"
                    draggable
                    aria-label="Reorder"
                    onDragStart={(e) => {
                      setDraggingId(item.playlist_id);
                      e.dataTransfer.setData("text/plain", String(item.playlist_id));
                    }}
                    className="flex size-11 shrink-0 cursor-grab items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"
                  >
                    <GripVertical size={16} />
                  </button>
                  <div className="w-28 shrink-0">
                    <PlaylistStackPoster
                      posterUrl={item.poster_url}
                      posterAssetKey={item.poster_asset_key}
                      videoCount={item.video_count}
                      className="aspect-video w-full"
                      size="sm"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <Link href={`/playlists/${item.playlist_id}`} className="block truncate text-sm font-medium hover:underline">
                      {item.name}
                    </Link>
                    <p className="text-xs text-muted-foreground">{item.video_count} videos</p>
                    <HiddenLink reason={item.hidden_reason} href={`/playlists/${item.playlist_id}`} />
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    {item.share_enabled && item.share_token && (
                      <button
                        type="button"
                        className={ROW_LINK}
                        onClick={() => void copyPlaylistLink(item.playlist_id, item.share_token!)}
                      >
                        {copiedPlaylistId === item.playlist_id ? "Copied" : "Copy link"}
                      </button>
                    )}
                    <button
                      type="button"
                      className="text-xs text-muted-foreground hover:text-danger-fg"
                      onClick={() =>
                        void removeChannelPlaylist(channelId, item.playlist_id).then(() =>
                          qc.invalidateQueries({ queryKey: ["channel-playlists", channelId] }),
                        )
                      }
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
        {aside}
      </div>
        )}
        {pageTab === "channel" && (
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <section className={cn(CARD_SHELL, "min-w-0 p-5")}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <Field label="Name" className="min-w-0 flex-1">
              <input
                value={nameEditing ? nameDraft : channel.name}
                onChange={(e) => {
                  setNameEditing(true);
                  setNameDraft(e.target.value);
                }}
                className="w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
              />
            </Field>
            <ActionButton variant="secondary" icon={<Trash2 size={14} />} onClick={() => setDeleteConfirm(true)}>
              Delete
            </ActionButton>
          </div>
          {nameEditing && nameDraft.trim() !== channel.name && (
            <ActionButton
              size="sm"
              className="mt-2"
              isPending={rename.isPending}
              disabled={!nameDraft.trim()}
              onClick={() => rename.mutate(nameDraft.trim())}
            >
              Save name
            </ActionButton>
          )}

          <div className="mt-5">
            <p className="text-xs font-medium text-muted-foreground">Banner</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Wide strip on the public page. Same width as the fields below.
            </p>
            <div
              className={cn(
                CHANNEL_BANNER_ASPECT,
                "mt-2 w-full overflow-hidden rounded-xl border border-border bg-muted",
                "outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10",
              )}
            >
              {channel.banner_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={channel.banner_url} alt="" className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-muted-foreground">No banner</div>
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <label className="pressable inline-flex min-h-8 cursor-pointer items-center rounded-xl border border-border px-3 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-muted">
                {channel.banner_url ? "Replace" : "Upload"}
                <input
                  type="file"
                  accept="image/*"
                  className="sr-only"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    void uploadChannelBanner(channelId, file)
                      .then(() => {
                        void qc.invalidateQueries({ queryKey: ["channel", channelId] });
                        void qc.invalidateQueries({ queryKey: ["channels"] });
                      })
                      .catch((err) => show("error", extractApiError(err, "Could not upload banner.")));
                    e.target.value = "";
                  }}
                />
              </label>
              {channel.banner_url && (
                <ActionButton
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    void deleteChannelBanner(channelId).then(() => {
                      void qc.invalidateQueries({ queryKey: ["channel", channelId] });
                    })
                  }
                >
                  Remove
                </ActionButton>
              )}
            </div>
          </div>

          <div className="mt-4">
            <label htmlFor="channel-slug" className="text-xs font-medium text-muted-foreground">
              Slug
            </label>
            <p className="mt-0.5 text-xs text-muted-foreground">
              One permanent public URL. Letters, digits, hyphen, underscore. Changing it breaks the old link.
            </p>
            <div className="mt-1 flex gap-2">
              <input
                id="channel-slug"
                value={slugValue}
                onChange={(e) => setSlugDraft(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 64))}
                className="min-w-0 flex-1 rounded-lg border border-input bg-card px-2 py-1 font-mono text-sm"
              />
              {slugDraft !== null && slugDraft !== channel.slug && (
                <ActionButton size="sm" onClick={() => (channel.share_enabled ? setSlugConfirm(true) : saveSlug.mutate(slugDraft))}>
                  Save slug
                </ActionButton>
              )}
            </div>
          </div>

          <div className="mt-4">
            <DescriptionEditor
              id="channel-description"
              label="Description"
              value={descriptionValue}
              onChange={(v) => setDescDraft(v)}
              placeholder="What this channel is about…"
              variables={CHANNEL_JINJA_VARS}
              maxLength={4000}
              hint="A short about, not a lecture. Long text fades, then Show more."
            />
            {descriptionValue.trim() !== "" && (
              <div className="mt-3 rounded-xl border border-border bg-muted/20 px-3 py-2.5">
                <p className="mb-1.5 text-[10px] text-muted-foreground/60">Public look</p>
                <FormattedText text={descriptionPreview} className="text-sm text-muted-foreground" />
              </div>
            )}
            {descDraft !== null && (
              <ActionButton
                size="sm"
                className="mt-2"
                isPending={saveDesc.isPending}
                onClick={() => saveDesc.mutate(/^\s*$/.test(descDraft) ? null : descDraft)}
              >
                Save description
              </ActionButton>
            )}
          </div>
        </section>
        {aside}
      </div>
        )}
        {pageTab === "analytics" && (
          <ShareAnalyticsPanel
            subject={{ kind: "channel", id: channelId }}
            open
            hideHeading
            showRevokedBanner={!channel.share_enabled}
            viewsHint="Videos and playlist items on this channel"
          />
        )}
      </Tabs>

      <Modal open={addVideosOpen} onClose={() => setAddVideosOpen(false)} label="Add videos" panelClassName="max-w-lg">
        <div className="space-y-4 p-6">
          <h2 className="text-sm font-semibold">Add videos</h2>
          <SearchInput id="add-channel-videos" value={addSearch} onChange={setAddSearch} placeholder="Search recordings…" />
          <div className="max-h-80 space-y-2 overflow-y-auto">
            {(recordingsQuery.data ?? [])
              .filter((r) => !inVideos.has(r.id))
              .map((r) => (
                <label key={r.id} className="flex cursor-pointer items-center gap-3 rounded-xl border border-border p-3">
                  <input
                    type="checkbox"
                    className={CHECKBOX}
                    checked={addSelected.has(r.id)}
                    onChange={(e) => {
                      setAddSelected((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(r.id);
                        else next.delete(r.id);
                        return next;
                      });
                    }}
                  />
                  <span className="min-w-0 flex-1 truncate text-sm">{r.display_name}</span>
                </label>
              ))}
          </div>
          <div className="flex justify-end gap-2">
            <ActionButton type="button" variant="secondary" onClick={() => setAddVideosOpen(false)}>Cancel</ActionButton>
            <ActionButton
              disabled={addSelected.size === 0}
              onClick={() => {
                void addChannelVideos(channelId, [...addSelected]).then(() => {
                  setAddVideosOpen(false);
                  setAddSelected(new Set());
                  void qc.invalidateQueries({ queryKey: ["channel-videos", channelId] });
                  void qc.invalidateQueries({ queryKey: ["channel", channelId] });
                });
              }}
            >
              Apply
            </ActionButton>
          </div>
        </div>
      </Modal>

      <Modal open={addPlaylistsOpen} onClose={() => setAddPlaylistsOpen(false)} label="Add playlists" panelClassName="max-w-lg">
        <div className="space-y-4 p-6">
          <h2 className="text-sm font-semibold">Add playlists</h2>
          <SearchInput id="add-channel-playlists" value={addSearch} onChange={setAddSearch} placeholder="Search playlists…" />
          <div className="max-h-80 space-y-2 overflow-y-auto">
            {(playlistPickQuery.data?.items ?? [])
              .filter((p) => !inPlaylists.has(p.id))
              .map((p) => (
                <label key={p.id} className="flex cursor-pointer items-center gap-3 rounded-xl border border-border p-3">
                  <input
                    type="checkbox"
                    className={CHECKBOX}
                    checked={addSelected.has(p.id)}
                    onChange={(e) => {
                      setAddSelected((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(p.id);
                        else next.delete(p.id);
                        return next;
                      });
                    }}
                  />
                  <span className="min-w-0 flex-1 truncate text-sm">{p.name}</span>
                </label>
              ))}
          </div>
          <div className="flex justify-end gap-2">
            <ActionButton type="button" variant="secondary" onClick={() => setAddPlaylistsOpen(false)}>Cancel</ActionButton>
            <ActionButton
              disabled={addSelected.size === 0}
              onClick={() => {
                void addChannelPlaylists(channelId, [...addSelected]).then(() => {
                  setAddPlaylistsOpen(false);
                  setAddSelected(new Set());
                  void qc.invalidateQueries({ queryKey: ["channel-playlists", channelId] });
                  void qc.invalidateQueries({ queryKey: ["channel", channelId] });
                });
              }}
            >
              Apply
            </ActionButton>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={slugConfirm}
        onCancel={() => setSlugConfirm(false)}
        onConfirm={() => slugDraft && saveSlug.mutate(slugDraft)}
        title="Change public URL?"
        description="The old /c/ link will stop opening. There is no redirect."
        confirmLabel="Change slug"
      />
      <ConfirmDialog
        open={disableConfirm}
        onCancel={() => setDisableConfirm(false)}
        onConfirm={() => disableShare.mutate()}
        title="Disable channel link?"
        description="The slug stays reserved. Enable again to restore the same URL."
        confirmLabel="Disable"
        danger
      />
      <ConfirmDialog
        open={deleteConfirm}
        onCancel={() => setDeleteConfirm(false)}
        onConfirm={() => remove.mutate()}
        title="Delete channel?"
        description="This frees the slug. Playlists and recordings are not deleted."
        confirmLabel="Delete"
        danger
      />
      {toast && <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismiss} />}
    </div>
  );
}
