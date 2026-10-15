"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, ExternalLink, Loader2, Pencil, Plus, Search, X } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { Modal } from "@/components/ui/modal";
import { NativeSelect } from "@/components/ui/native-select";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { cn } from "@/lib/utils";
import {
  createYouTubePlaylist,
  getYouTubePlaylist,
  listYouTubePlaylists,
  updateYouTubePlaylist,
  type YouTubePlaylist,
  type YouTubePlaylistInput,
} from "@/api/youtube-playlists";

const PRIVACY_OPTIONS: { value: YouTubePlaylist["privacy_status"]; label: string }[] = [
  { value: "unlisted", label: "Unlisted" },
  { value: "private", label: "Private" },
  { value: "public", label: "Public" },
];

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "YouTube API request failed. Try again.";
}

function isCredentialError(error: unknown): boolean {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response;
  return response?.status === 403
    && typeof response.data?.detail === "string"
    && response.data.detail.toLowerCase().includes("reconnect this account");
}

function canRetryPlaylistRequest(error: unknown): boolean {
  const requestStatus = (error as { response?: { status?: number } })?.response?.status;
  return requestStatus === undefined || requestStatus === 500 || requestStatus === 502;
}

function retryPlaylistRequest(failureCount: number, error: unknown): boolean {
  return canRetryPlaylistRequest(error) && failureCount < 1;
}

export function YouTubePlaylistPicker({
  credentialId,
  value,
  onChange,
  disabled = false,
}: {
  credentialId: number | null;
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [editing, setEditing] = useState<YouTubePlaylist | "new" | null>(null);
  const [form, setForm] = useState<YouTubePlaylistInput>({ title: "", description: "", privacy_status: "unlisted" });
  const [formError, setFormError] = useState("");
  const titleId = useId();
  const searchId = useId();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const formTitleRef = useRef<HTMLInputElement>(null);
  const hasCredential = typeof credentialId === "number" && credentialId > 0;

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      (editing === null ? searchInputRef.current : formTitleRef.current)?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [editing, open]);

  const query = useInfiniteQuery({
    queryKey: ["youtube-playlists", credentialId, debouncedSearch],
    queryFn: ({ pageParam, signal }) => listYouTubePlaylists(credentialId!, {
      q: debouncedSearch || undefined,
      page_token: pageParam || undefined,
    }, signal),
    initialPageParam: "" as string,
    getNextPageParam: (lastPage) => lastPage.next_page_token ?? undefined,
    enabled: open && hasCredential,
    retry: retryPlaylistRequest,
  });

  const items = useMemo(() => query.data?.pages.flatMap((page) => page.items) ?? [], [query.data]);
  const selectedInList = items.find((item) => item.id === value);
  const selectedQuery = useQuery({
    queryKey: ["youtube-playlist", credentialId, value],
    queryFn: ({ signal }) => getYouTubePlaylist(credentialId!, value, signal),
    enabled: hasCredential && !!value && !selectedInList,
    staleTime: 60_000,
    retry: retryPlaylistRequest,
  });
  const selected = selectedInList ?? selectedQuery.data;

  const save = useMutation({
    mutationFn: () => editing && editing !== "new"
      ? updateYouTubePlaylist(credentialId!, editing.id, form)
      : createYouTubePlaylist(credentialId!, form),
    onSuccess: (playlist) => {
      const created = editing === "new";
      if (created || editing?.id === value) onChange(playlist.id);
      setEditing(null);
      setFormError("");
      setSearch("");
      setDebouncedSearch("");
      if (created) setOpen(false);
      void qc.invalidateQueries({ queryKey: ["youtube-playlists", credentialId] });
      void qc.invalidateQueries({ queryKey: ["youtube-playlist", credentialId, playlist.id] });
    },
    onError: (error) => setFormError(errorMessage(error)),
  });

  function openDialog() {
    setOpen(true);
    setSearch("");
    setDebouncedSearch("");
    setFormError("");
  }

  function startCreate() {
    setEditing("new");
    setForm({ title: "", description: "", privacy_status: "unlisted" });
    setFormError("");
  }

  function startEdit(playlist: YouTubePlaylist) {
    setEditing(playlist);
    setForm({ title: playlist.title, description: playlist.description, privacy_status: playlist.privacy_status });
    setFormError("");
  }

  function selectPlaylist(playlist: YouTubePlaylist) {
    onChange(playlist.id);
    setOpen(false);
    setEditing(null);
  }

  const statusText = query.error ? errorMessage(query.error) : "";

  return (
    <div className="space-y-1">
      <span className={FILTER_LABEL}>YouTube playlist</span>
      <div className="flex items-center gap-2">
        <div className={cn(FILTER_CONTROL, "flex min-w-0 flex-1 items-center gap-2 p-0 pr-2")}>
          <button
            type="button"
            disabled={disabled || !hasCredential}
            aria-haspopup="dialog"
            aria-expanded={open}
            onClick={openDialog}
            className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span className={cn("flex-1 truncate", selected || value ? "text-foreground" : "text-muted-foreground")}>
              {selected?.title || (value ? `Playlist ${value}` : "Choose a playlist…")}
            </span>
            <ChevronDown size={14} className="shrink-0 text-muted-foreground" />
          </button>
          {value && !disabled && <button type="button" onClick={() => onChange("")} aria-label="Clear YouTube playlist" className="rounded p-1.5 text-muted-foreground hover:text-foreground"><X size={14} /></button>}
        </div>
        {value && (
          <a
            href={`https://www.youtube.com/playlist?list=${encodeURIComponent(value)}`}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg p-2 text-muted-foreground hover:text-foreground"
            aria-label="Open playlist on YouTube"
          ><ExternalLink size={15} /></a>
        )}
      </div>
      {!hasCredential && <p className="text-xs text-muted-foreground">Select a YouTube credential in the linked preset to browse and manage playlists.</p>}
      {selectedQuery.isError && <p role="alert" className="text-xs text-destructive">{errorMessage(selectedQuery.error)}{isCredentialError(selectedQuery.error) && <> <a className="underline" href="/credentials">Reconnect in Credentials</a></>}</p>}

      <Modal open={open} onClose={() => { if (save.isPending) return; setOpen(false); setEditing(null); setFormError(""); }} closeOnBackdrop={!save.isPending} closeOnEsc={!save.isPending} labelledBy={titleId} initialFocusRef={searchInputRef} panelClassName="max-w-xl overflow-hidden">
        <div className="flex max-h-[min(85vh,700px)] flex-col">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 id={titleId} className="text-sm font-semibold">{editing ? (editing === "new" ? "Create YouTube playlist" : "Edit YouTube playlist") : "Choose YouTube playlist"}</h2>
            <button type="button" disabled={save.isPending} onClick={() => { setOpen(false); setEditing(null); setFormError(""); }} aria-label="Close dialog" className="text-muted-foreground hover:text-foreground disabled:opacity-50"><X size={16} /></button>
          </div>

          {editing !== null ? (
            <form className="space-y-4 overflow-y-auto p-5" onSubmit={(event) => { event.preventDefault(); if (!form.title.trim()) { setFormError("Enter a playlist title."); return; } save.mutate(); }}>
              <label className="block space-y-1"><span className={FILTER_LABEL}>Title</span><input ref={formTitleRef} required maxLength={150} value={form.title} onChange={(e) => { setFormError(""); setForm((old) => ({ ...old, title: e.target.value })); }} className={FILTER_CONTROL} /></label>
              <label className="block space-y-1"><span className={FILTER_LABEL}>Description</span><textarea maxLength={5000} rows={4} value={form.description} onChange={(e) => { setFormError(""); setForm((old) => ({ ...old, description: e.target.value })); }} className={cn(FILTER_CONTROL, "resize-y")} /></label>
              <label className="block space-y-1"><span className={FILTER_LABEL}>Visibility</span><NativeSelect value={form.privacy_status} onChange={(e) => { setFormError(""); setForm((old) => ({ ...old, privacy_status: e.target.value as YouTubePlaylistInput["privacy_status"] })); }}>{PRIVACY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</NativeSelect><span className="block text-xs text-muted-foreground">{form.privacy_status === "public" ? "Anyone can find and watch this playlist." : form.privacy_status === "private" ? "Only you can view this playlist." : "Anyone with the link can watch; it will not appear in search."}</span></label>
              {formError && <p role="alert" className="text-sm text-destructive">{formError}</p>}
              <div className="flex justify-end gap-2"><ActionButton type="button" variant="secondary" disabled={save.isPending} onClick={() => { setEditing(null); setFormError(""); }}>Back to playlists</ActionButton><ActionButton type="submit" isPending={save.isPending} icon={<Check size={14} />} pendingLabel="Saving…">Save</ActionButton></div>
            </form>
          ) : (
            <>
              <div className="flex gap-2 border-b border-border p-4">
                <label htmlFor={searchId} className="sr-only">Search all YouTube playlists</label>
                <div className="relative min-w-0 flex-1"><Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><input ref={searchInputRef} id={searchId} type="search" maxLength={100} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by playlist name or description…" className={cn(FILTER_CONTROL, "pl-9")} /></div>
                <ActionButton size="sm" onClick={startCreate} icon={<Plus size={14} />}>Create</ActionButton>
              </div>
              {formError && <p role="alert" className="px-5 pt-3 text-sm text-destructive">{formError}</p>}
              <div className="min-h-36 flex-1 overflow-y-auto p-2">
                {query.isLoading ? <div className="flex justify-center p-8"><Loader2 size={18} className="animate-spin text-muted-foreground" /></div> : null}
                {query.isFetching && !query.isLoading && !query.isFetchingNextPage ? <p role="status" className="flex items-center justify-center gap-2 p-3 text-xs text-muted-foreground"><Loader2 size={14} className="animate-spin" />Searching playlists…</p> : null}
              {query.error ? <div className="space-y-3 p-5 text-center"><p role="alert" className="text-sm text-destructive">{statusText}{isCredentialError(query.error) && <> <a className="underline" href="/credentials">Reconnect in Credentials</a></>}</p>{canRetryPlaylistRequest(query.error) && <ActionButton size="sm" variant="secondary" isPending={query.isFetching} onClick={() => void query.refetch()}>Retry</ActionButton>}</div> : null}
                {!query.isLoading && !query.error && items.length === 0 ? <p className="p-8 text-center text-sm text-muted-foreground">{debouncedSearch ? "No matching playlists. Try another search or create a new playlist." : "No playlists yet. Create one to use it for uploads."}</p> : null}
                {items.map((playlist) => (
                  <div key={playlist.id} className="flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-muted/60">
                    <button type="button" onClick={() => selectPlaylist(playlist)} className="min-w-0 flex-1 text-left">
                      <span className="block truncate text-sm font-medium">{playlist.title}</span>
                      <span className="block truncate text-xs text-muted-foreground">{playlist.item_count} {playlist.item_count === 1 ? "video" : "videos"} · {playlist.privacy_status[0].toUpperCase() + playlist.privacy_status.slice(1)}</span>
                    </button>
                    <button type="button" aria-label={`Edit ${playlist.title}`} onClick={() => startEdit(playlist)} className="rounded p-2 text-muted-foreground hover:text-foreground"><Pencil size={14} /></button>
                  </div>
                ))}
                {query.hasNextPage && !debouncedSearch && <div className="flex justify-center p-3"><ActionButton size="sm" variant="secondary" isPending={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>{query.isFetchingNextPage ? "Loading…" : "Load more"}</ActionButton></div>}
              </div>
            </>
          )}
        </div>
      </Modal>
    </div>
  );
}
