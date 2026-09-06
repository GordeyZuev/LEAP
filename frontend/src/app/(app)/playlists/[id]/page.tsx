"use client";

import { Suspense, use, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  ExternalLink,
  GripVertical,
  Link as LinkIcon,
  ListVideo,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";

import {
  addPlaylistItems,
  deletePlaylist,
  disablePlaylistShare,
  enablePlaylistShare,
  getPlaylist,
  listPlaylistItems,
  removePlaylistItem,
  reorderPlaylistItems,
  rotatePlaylistShare,
  updatePlaylist,
  type PlaylistDetail,
  type PlaylistItem,
} from "@/api/playlists";
import { apiClient } from "@/api/client";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { FilterChips, type FilterChipItem } from "@/components/filters/filter-chips";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DescriptionEditor } from "@/components/ui/description-editor";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { FormattedText } from "@/components/ui/formatted-text";
import { Modal } from "@/components/ui/modal";
import { CARD_SHELL, SectionCard } from "@/components/ui/section-card";
import { RecordingPoster } from "@/components/recordings/recording-poster";
import { Skeleton } from "@/components/ui/skeleton";
import { Toast } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { interpolatePlaylistDescription, PLAYLIST_JINJA_VARS } from "@/lib/formatted-text";
import { cn, extractApiError, formatDate, httpStatus } from "@/lib/utils";

function shareUrl(token: string | null): string | null {
  if (!token || typeof window === "undefined") return null;
  return `${window.location.origin}/share/p/${token}`;
}

const ACCESS_LINK =
  "inline-flex min-h-7 items-center gap-0.5 text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm";
const ACCESS_ACTION =
  "inline-flex min-h-7 items-center text-xs font-medium text-muted-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm";

const EMPTY_ITEMS: PlaylistItem[] = [];

interface RecordingPick {
  id: number;
  display_name: string;
  start_time: string;
  duration: number;
}

export default function PlaylistEditorPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading playlist…</div>}>
      <PlaylistEditor params={params} />
    </Suspense>
  );
}

function PlaylistEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const playlistId = Number(id);
  const router = useRouter();
  const qc = useQueryClient();
  const sp = useSearchParams();
  const { toast, show, dismiss } = useToast();

  const q = sp.get("q") ?? "";
  const fromDate = sp.get("from_date") ?? "";
  const toDate = sp.get("to_date") ?? "";

  const [nameEditing, setNameEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [descDraft, setDescDraft] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addSearch, setAddSearch] = useState("");
  const [addSelected, setAddSelected] = useState<Set<number>>(new Set());
  const [disableConfirm, setDisableConfirm] = useState(false);
  const [rotateConfirm, setRotateConfirm] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [copied, setCopied] = useState(false);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [overId, setOverId] = useState<number | null>(null);

  const { data: playlist, isLoading, error, refetch } = useQuery({
    queryKey: ["playlist", playlistId],
    queryFn: () => getPlaylist(playlistId),
    enabled: Number.isFinite(playlistId),
  });

  const itemsQuery = useQuery({
    queryKey: ["playlist-items", playlistId, q, fromDate, toDate],
    queryFn: () =>
      listPlaylistItems(playlistId, {
        q: q || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        per_page: 200,
      }),
    enabled: Number.isFinite(playlistId),
  });

  const items = itemsQuery.data?.items ?? EMPTY_ITEMS;
  const publicUrl = shareUrl(playlist?.share_token ?? null);

  const recordingsQuery = useQuery({
    queryKey: ["recordings-picker", addSearch],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (addSearch) p.set("search", addSearch);
      p.set("per_page", "50");
      p.set("sort_by", "start_time");
      p.set("sort_order", "desc");
      const res = await apiClient.get<{ items: RecordingPick[] }>(`/recordings?${p.toString()}`);
      return res.data.items;
    },
    enabled: addOpen,
  });

  const inPlaylist = useMemo(() => new Set(items.map((i) => i.recording_id)), [items]);

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(sp.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`?${next.toString()}`);
  }

  const rename = useMutation({
    mutationFn: (name: string) => updatePlaylist(playlistId, { name }),
    onSuccess: () => {
      setNameEditing(false);
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
      qc.invalidateQueries({ queryKey: ["playlists"] });
      show("success", "Name updated");
    },
    onError: (e) => show("error", extractApiError(e, "A playlist with this name already exists.")),
  });

  const saveDesc = useMutation({
    mutationFn: (description: string | null) => updatePlaylist(playlistId, { description }),
    onSuccess: () => {
      setDescDraft(null);
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
      show("success", "Description saved");
    },
    onError: (e) => show("error", extractApiError(e, "Failed to save description")),
  });

  const enableShare = useMutation({
    mutationFn: () => enablePlaylistShare(playlistId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
      show("success", "Link enabled");
    },
    onError: (e) => show("error", extractApiError(e, "Failed to enable link")),
  });

  const disableShare = useMutation({
    mutationFn: () => disablePlaylistShare(playlistId),
    onSuccess: () => {
      setDisableConfirm(false);
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
      show("success", "Link disabled");
    },
    onError: (e) => show("error", extractApiError(e, "Failed to disable link")),
  });

  const rotateShare = useMutation({
    mutationFn: () => rotatePlaylistShare(playlistId),
    onSuccess: () => {
      setRotateConfirm(false);
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
      show("success", "Link rotated");
    },
    onError: (e) => show("error", extractApiError(e, "Failed to rotate link")),
  });

  const removeItem = useMutation({
    mutationFn: (itemId: number) => removePlaylistItem(playlistId, itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["playlist-items", playlistId] });
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
    },
    onError: (e) => show("error", extractApiError(e, "Failed to remove from playlist")),
  });

  const addItems = useMutation({
    mutationFn: (ids: number[]) => addPlaylistItems(playlistId, ids),
    onSuccess: () => {
      setAddOpen(false);
      setAddSelected(new Set());
      qc.invalidateQueries({ queryKey: ["playlist-items", playlistId] });
      qc.invalidateQueries({ queryKey: ["playlist", playlistId] });
      show("success", "Recordings added");
    },
    onError: (e) => show("error", extractApiError(e, "Failed to add recordings")),
  });

  async function persistOrder(ids: number[]) {
    try {
      await reorderPlaylistItems(playlistId, ids);
      qc.invalidateQueries({ queryKey: ["playlist-items", playlistId] });
    } catch (e) {
      show("error", extractApiError(e, "Item set does not match the playlist. Refresh and try again."));
      qc.invalidateQueries({ queryKey: ["playlist-items", playlistId] });
    }
  }

  async function move(item: PlaylistItem, dir: -1 | 1) {
    const full = await listPlaylistItems(playlistId, { per_page: 200 });
    const ids = full.items.map((i) => i.id);
    const idx = ids.indexOf(item.id);
    const next = idx + dir;
    if (idx < 0 || next < 0 || next >= ids.length) return;
    [ids[idx], ids[next]] = [ids[next], ids[idx]];
    await persistOrder(ids);
  }

  async function dropOn(targetId: number, sourceFromEvent?: number) {
    const sourceId = draggingId ?? sourceFromEvent;
    setDraggingId(null);
    setOverId(null);
    if (!sourceId || sourceId === targetId) return;
    const full = await listPlaylistItems(playlistId, { per_page: 200 });
    const ids = full.items.map((i) => i.id);
    const from = ids.indexOf(sourceId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(from, 1);
    ids.splice(to, 0, sourceId);
    qc.setQueryData(
      ["playlist-items", playlistId, q, fromDate, toDate],
      (old: { items: PlaylistItem[] } | undefined) => {
        if (!old?.items) return old;
        const next = [...old.items];
        const a = next.findIndex((i) => i.id === sourceId);
        const b = next.findIndex((i) => i.id === targetId);
        if (a < 0 || b < 0) return old;
        const [moved] = next.splice(a, 1);
        next.splice(b, 0, moved);
        return { ...old, items: next };
      },
    );
    await persistOrder(ids);
  }

  const destroy = useMutation({
    mutationFn: () => deletePlaylist(playlistId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["playlists"] });
      router.push("/playlists");
    },
    onError: (e) => show("error", extractApiError(e, "Failed to delete playlist")),
  });

  async function copyLink() {
    if (!publicUrl) return;
    await navigator.clipboard.writeText(publicUrl);
    setCopied(true);
    show("success", "Link copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  }

  const chips: FilterChipItem[] = [
    ...(q ? [{ key: "q", label: `Search: "${q}"`, onRemove: () => setFilter("q", "") }] : []),
    ...(fromDate ? [{ key: "from", label: `From ${fromDate}`, onRemove: () => setFilter("from_date", "") }] : []),
    ...(toDate ? [{ key: "to", label: `To ${toDate}`, onRemove: () => setFilter("to_date", "") }] : []),
  ];

  if (error) {
    const missing = httpStatus(error) === 404 || httpStatus(error) === 403;
    return (
      <div className="p-8">
        <ErrorState
          title={missing ? "Playlist not found" : "Unable to load this playlist"}
          description={
            missing
              ? "It may have been deleted, or it belongs to another account."
              : "Check your connection and try again."
          }
          onRetry={missing ? undefined : () => void refetch()}
        />
        <p className="mt-4 text-center">
          <Link href="/playlists" className="text-sm text-primary hover:underline">
            Back to playlists
          </Link>
        </p>
      </div>
    );
  }

  if (isLoading || !playlist) {
    return (
      <div className="space-y-4 p-6 sm:p-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  const descriptionValue = descDraft ?? playlist.description ?? "";
  const canDrag = !q && !fromDate && !toDate;
  const descriptionPreview = interpolatePlaylistDescription(descriptionValue, {
    videoCount: playlist.video_count,
    durationSeconds: playlist.duration_sum,
    titles: canDrag ? items.map((i) => i.display_name) : [],
    substituteItems: canDrag,
  });

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <Link
        href="/playlists"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} /> Playlists
      </Link>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section className={cn(CARD_SHELL, "min-w-0 p-5")}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            {nameEditing ? (
              <form
                className="flex min-w-0 flex-1 items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!nameDraft.trim()) return;
                  rename.mutate(nameDraft.trim());
                }}
              >
                <input
                  autoFocus
                  aria-label="Playlist name"
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Escape") setNameEditing(false); }}
                  className="min-w-0 flex-1 rounded-lg border border-input bg-card px-2 py-1 text-xl font-semibold tracking-tight outline-none focus:border-primary focus:ring-2 focus:ring-primary/30 sm:text-2xl"
                />
                <button type="submit" disabled={rename.isPending || !nameDraft.trim()} className="text-xs text-primary hover:underline">Save</button>
                <button type="button" onClick={() => setNameEditing(false)} className="text-xs text-muted-foreground hover:underline">Cancel</button>
              </form>
            ) : (
              <div className="group flex min-w-0 flex-1 items-center gap-2">
                <h1 className="min-w-0 truncate text-xl font-semibold tracking-tight text-foreground sm:text-2xl">{playlist.name}</h1>
                <button
                  type="button"
                  onClick={() => { setNameDraft(playlist.name); setNameEditing(true); }}
                  className="shrink-0 rounded p-1 text-muted-foreground transition-opacity hover:text-secondary-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
                  title="Rename"
                  aria-label="Rename playlist"
                >
                  <Pencil size={14} />
                </button>
              </div>
            )}
            <ActionButton variant="secondary" icon={<Trash2 size={14} />} onClick={() => setDeleteConfirm(true)}>
              Delete
            </ActionButton>
          </div>

          <div className="mt-4">
            <DescriptionEditor
              id="playlist-description"
              label="Description"
              value={descriptionValue}
              onChange={(v) => setDescDraft(v)}
              placeholder="What this playlist is about…"
              variables={PLAYLIST_JINJA_VARS}
            />
            {descriptionValue.trim() !== "" && (
              <div className="mt-3 rounded-xl border border-border bg-muted/20 px-3 py-2.5">
                <p className="mb-1.5 text-[10px] leading-snug text-muted-foreground/60">Public look</p>
                <FormattedText text={descriptionPreview} className="text-sm leading-relaxed text-muted-foreground" />
              </div>
            )}
            {descDraft !== null && (
              <div className="mt-2">
                <ActionButton
                  size="sm"
                  isPending={saveDesc.isPending}
                  onClick={() => saveDesc.mutate(/^\s*$/.test(descDraft) ? null : descDraft)}
                >
                  Save description
                </ActionButton>
              </div>
            )}
          </div>
        </section>

        <aside className="min-w-0 lg:col-start-2 lg:row-span-2 lg:sticky lg:top-6 lg:self-start">
          <PlaylistAccessCard
            playlist={playlist}
            publicUrl={publicUrl}
            copied={copied}
            enablePending={enableShare.isPending}
            onCopy={() => void copyLink()}
            onEnable={() => enableShare.mutate()}
            onDisable={() => setDisableConfirm(true)}
            onRotate={() => setRotateConfirm(true)}
          />
        </aside>

        <SectionCard
          title="Videos"
          description={canDrag ? "Drag to change the watch order." : "Clear filters to reorder."}
          density="compact"
          className="min-w-0 lg:col-start-1"
          action={
            <ActionButton size="sm" variant="secondary" icon={<Plus size={12} />} onClick={() => setAddOpen(true)}>
              Add recordings
            </ActionButton>
          }
        >
        <FilterBar
          search={
            <SearchInput
              id="playlist-items-search"
              value={q}
              onChange={(v) => setFilter("q", v)}
              placeholder="By recording name…"
            />
          }
          controls={[
            <div key="dates">
              <span className={FILTER_LABEL}>Recording start date</span>
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <input type="date" aria-label="From date" value={fromDate} onChange={(e) => setFilter("from_date", e.target.value)} className={cn(FILTER_CONTROL, "min-w-0 sm:max-w-[11rem]")} />
                <span className="text-muted-foreground">—</span>
                <input type="date" aria-label="To date" value={toDate} onChange={(e) => setFilter("to_date", e.target.value)} className={cn(FILTER_CONTROL, "min-w-0 sm:max-w-[11rem]")} />
              </div>
            </div>,
          ]}
          chips={<FilterChips chips={chips} />}
        />

        {itemsQuery.isLoading && <p className="text-xs text-muted-foreground">Loading videos…</p>}
        {!itemsQuery.isLoading && items.length === 0 && (
          <EmptyState
            icon={ListVideo}
            title={q || fromDate || toDate ? "No videos match" : "No videos yet"}
            description={q || fromDate || toDate ? "Try different filters." : "Add recordings to this playlist."}
            action={
              !(q || fromDate || toDate) ? (
                <ActionButton size="sm" variant="secondary" icon={<Plus size={12} />} onClick={() => setAddOpen(true)}>
                  Add recordings
                </ActionButton>
              ) : undefined
            }
          />
        )}
        {items.length > 0 && (
          <ul className="divide-y divide-border">
            {items.map((item, index) => (
              <li
                key={item.id}
                onDragOver={
                  canDrag
                    ? (e) => {
                        e.preventDefault();
                        if (overId !== item.id) setOverId(item.id);
                      }
                    : undefined
                }
                onDrop={
                  canDrag
                    ? (e) => {
                        e.preventDefault();
                        const fromData = Number(e.dataTransfer.getData("text/plain"));
                        void dropOn(item.id, Number.isFinite(fromData) ? fromData : undefined);
                      }
                    : undefined
                }
                onDragLeave={() => { if (overId === item.id) setOverId(null); }}
                className={cn(
                  "flex min-w-0 flex-col gap-2 py-3 sm:flex-row sm:items-center sm:gap-3",
                  draggingId === item.id && "opacity-50",
                  overId === item.id && draggingId !== item.id && "bg-muted/60",
                )}
              >
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  {canDrag && (
                    <button
                      type="button"
                      draggable
                      aria-label="Reorder. Drag, or use arrow keys."
                      onDragStart={(e) => {
                        setDraggingId(item.id);
                        e.dataTransfer.effectAllowed = "move";
                        e.dataTransfer.setData("text/plain", String(item.id));
                      }}
                      onDragEnd={() => { setDraggingId(null); setOverId(null); }}
                      onKeyDown={(e) => {
                        if (e.key === "ArrowUp") { e.preventDefault(); void move(item, -1); }
                        if (e.key === "ArrowDown") { e.preventDefault(); void move(item, 1); }
                      }}
                      className="flex size-11 shrink-0 cursor-grab items-center justify-center rounded-lg text-muted-foreground hover:bg-muted active:cursor-grabbing"
                    >
                      <GripVertical size={16} />
                    </button>
                  )}
                  <span className="w-5 shrink-0 text-center text-xs tabular-nums text-muted-foreground">{index + 1}</span>
                  <RecordingPoster
                    recordingId={item.recording_id}
                    posterUrl={item.poster_url}
                    duration={item.duration}
                    className="aspect-video w-16 shrink-0"
                  />
                  <div className="min-w-0 flex-1">
                    <Link href={`/recordings/${item.recording_id}`} className="line-clamp-1 text-sm font-medium text-foreground hover:underline">
                      {item.display_name}
                    </Link>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {formatDate(item.start_time)}
                      {item.deleted && <span className="ms-2 text-danger-fg">Deleted</span>}
                      {!item.playable && !item.deleted && <span className="ms-2 text-muted-foreground">Processing</span>}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center justify-end">
                  <button
                    type="button"
                    aria-label="Remove from playlist"
                    onClick={() => removeItem.mutate(item.id)}
                    className="flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-danger-fg"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
      </div>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} label="Add recordings" panelClassName="max-w-lg">
        <div className="space-y-4 p-6">
          <h2 className="text-sm font-semibold">Add recordings</h2>
          <SearchInput id="add-recordings" value={addSearch} onChange={setAddSearch} placeholder="Search recordings…" />
          <div className="max-h-80 space-y-2 overflow-y-auto">
            {(recordingsQuery.data ?? []).map((rec) => {
              const already = inPlaylist.has(rec.id);
              const checked = already || addSelected.has(rec.id);
              return (
                <label key={rec.id} className="flex cursor-pointer items-center gap-3 rounded-xl border border-border p-3">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={already}
                    onChange={(e) => {
                      setAddSelected((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(rec.id);
                        else next.delete(rec.id);
                        return next;
                      });
                    }}
                    className="rounded accent-primary"
                  />
                  <span className="min-w-0 flex-1 truncate text-sm">{rec.display_name}</span>
                </label>
              );
            })}
          </div>
          <div className="flex justify-end gap-2">
            <ActionButton variant="secondary" onClick={() => setAddOpen(false)}>Cancel</ActionButton>
            <ActionButton
              disabled={addSelected.size === 0}
              isPending={addItems.isPending}
              onClick={() => addItems.mutate([...addSelected])}
            >
              Apply
            </ActionButton>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={disableConfirm}
        title="Disable link?"
        description="The link will stop working. Enabling it again uses the same URL."
        confirmLabel="Disable link"
        cancelLabel="Cancel"
        danger
        onConfirm={() => disableShare.mutate()}
        onCancel={() => setDisableConfirm(false)}
      />
      <ConfirmDialog
        open={rotateConfirm}
        title="Rotate link?"
        description="The current URL will stop working. Anyone with the old link loses access."
        confirmLabel="Rotate link"
        cancelLabel="Cancel"
        danger
        onConfirm={() => rotateShare.mutate()}
        onCancel={() => setRotateConfirm(false)}
      />
      <ConfirmDialog
        open={deleteConfirm}
        title="Delete playlist?"
        description="The public link will stop working. Recordings stay in your library."
        confirmLabel="Delete playlist"
        cancelLabel="Cancel"
        danger
        onConfirm={() => destroy.mutate()}
        onCancel={() => setDeleteConfirm(false)}
      />

      {toast && <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismiss} />}
    </div>
  );
}

function PlaylistAccessCard({
  playlist,
  publicUrl,
  copied,
  enablePending,
  onCopy,
  onEnable,
  onDisable,
  onRotate,
}: {
  playlist: PlaylistDetail;
  publicUrl: string | null;
  copied: boolean;
  enablePending: boolean;
  onCopy: () => void;
  onEnable: () => void;
  onDisable: () => void;
  onRotate: () => void;
}) {
  const active = playlist.share_enabled && !!playlist.share_token;

  return (
    <section aria-labelledby="playlist-access-heading" className={cn(CARD_SHELL, "overflow-hidden p-4")}>
      <div className="flex items-start gap-2.5">
        {active ? (
          <Check size={14} className="mt-0.5 shrink-0 text-success-fg" aria-hidden />
        ) : (
          <LinkIcon size={14} className="mt-0.5 shrink-0 text-muted-foreground" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <h2 id="playlist-access-heading" className="text-xs font-semibold text-foreground">
            LEAP Link
          </h2>
          <p className={cn("text-xs", active ? "text-success-fg" : "text-muted-foreground")}>
            {active ? "Active" : "Not shared"}
          </p>
          {publicUrl && (
            <p className="mt-1.5 truncate font-mono text-xs text-muted-foreground" title={publicUrl}>
              {publicUrl}
            </p>
          )}
          {!playlist.share_enabled && (
            <div className="mt-3">
              <ActionButton
                size="sm"
                variant="primary"
                icon={<LinkIcon size={12} />}
                isPending={enablePending}
                onClick={onEnable}
                className="w-full justify-center"
              >
                Enable link
              </ActionButton>
            </div>
          )}
          {(active || playlist.share_token) && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5">
              {active && publicUrl && (
                <>
                  <button type="button" onClick={onCopy} className={ACCESS_LINK}>
                    {copied ? "Copied" : "Copy"}
                  </button>
                  <a href={publicUrl} target="_blank" rel="noopener noreferrer" className={ACCESS_LINK}>
                    Open <ExternalLink size={10} aria-hidden />
                  </a>
                  <button type="button" onClick={onDisable} className={ACCESS_ACTION}>
                    Disable link
                  </button>
                </>
              )}
              {playlist.share_token && (
                <button type="button" onClick={onRotate} className={ACCESS_ACTION}>
                  Rotate link
                </button>
              )}
            </div>
          )}
          <p className="mt-3 text-xs leading-snug text-muted-foreground">
            {active
              ? "Students watch this playlist here. Disable keeps the same URL."
              : playlist.share_token
                ? "Enabling again uses the same URL."
                : "One URL for the whole playlist."}
          </p>
        </div>
      </div>
    </section>
  );
}
