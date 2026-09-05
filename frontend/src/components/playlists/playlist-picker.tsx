"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import { addPlaylistItems, createPlaylist, listPlaylists, removePlaylistItem, type PlaylistListItem } from "@/api/playlists";
import { ActionButton } from "@/components/ui/action-button";
import { Field } from "@/components/ui/field";
import { extractApiError } from "@/lib/utils";

const EMPTY_PLAYLISTS: PlaylistListItem[] = [];

interface PlaylistPickerProps {
  mode: "immediate" | "form";
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  /** Required in immediate mode to add/remove the current recording. */
  recordingId?: number;
  /** Existing membership item ids by playlist, used to DELETE in immediate mode. */
  membershipItemIds?: Record<number, number>;
  onToast?: (message: string, variant?: "success" | "error") => void;
}

export function PlaylistPicker({
  mode,
  selectedIds,
  onChange,
  recordingId,
  membershipItemIds,
  onToast,
}: PlaylistPickerProps) {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [createName, setCreateName] = useState("");
  const [creating, setCreating] = useState(false);

  const { data } = useQuery({
    queryKey: ["playlists", "picker"],
    queryFn: () => listPlaylists({ per_page: 100, sort_by: "name", sort_order: "asc" }),
  });

  const playlists = data?.items ?? EMPTY_PLAYLISTS;
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return playlists;
    return playlists.filter((p) => p.name.toLowerCase().includes(needle));
  }, [playlists, search]);
  const showSearch = playlists.length > 8;

  const addImmediate = useMutation({
    mutationFn: async (playlistId: number) => {
      if (!recordingId) return;
      await addPlaylistItems(playlistId, [recordingId]);
    },
    onSuccess: (_data, playlistId) => {
      onChange([...selectedIds, playlistId]);
      qc.invalidateQueries({ queryKey: ["playlists"] });
      qc.invalidateQueries({ queryKey: ["recording"] });
      onToast?.("Added to playlist", "success");
    },
    onError: (e) => onToast?.(extractApiError(e, "Failed to add to playlist"), "error"),
  });

  const removeImmediate = useMutation({
    mutationFn: async (playlistId: number) => {
      const itemId = membershipItemIds?.[playlistId];
      if (!itemId) throw new Error("Missing playlist item");
      await removePlaylistItem(playlistId, itemId);
    },
    onSuccess: (_data, playlistId) => {
      onChange(selectedIds.filter((id) => id !== playlistId));
      qc.invalidateQueries({ queryKey: ["playlists"] });
      qc.invalidateQueries({ queryKey: ["recording"] });
      onToast?.("Removed from playlist", "success");
    },
    onError: (e) => onToast?.(extractApiError(e, "Failed to remove from playlist"), "error"),
  });

  async function handleToggle(playlist: PlaylistListItem, checked: boolean) {
    if (mode === "form") {
      onChange(checked ? [...selectedIds, playlist.id] : selectedIds.filter((id) => id !== playlist.id));
      return;
    }
    if (checked) addImmediate.mutate(playlist.id);
    else removeImmediate.mutate(playlist.id);
  }

  async function handleCreate() {
    const name = createName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await createPlaylist({ name });
      qc.invalidateQueries({ queryKey: ["playlists"] });
      setCreateName("");
      if (mode === "form") {
        onChange([...selectedIds, created.id]);
      } else if (recordingId) {
        await addPlaylistItems(created.id, [recordingId]);
        onChange([...selectedIds, created.id]);
        qc.invalidateQueries({ queryKey: ["recording"] });
        onToast?.("Added to playlist", "success");
      }
    } catch (e) {
      onToast?.(extractApiError(e, "A playlist with this name already exists."), "error");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-3">
      {showSearch && (
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search playlists"
          aria-label="Search playlists"
          className="w-full rounded-xl border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
        />
      )}
      {filtered.length === 0 ? (
        <p className="text-xs text-muted-foreground">No playlists yet</p>
      ) : (
        <div className="space-y-2">
          {filtered.map((p) => {
            const checked = selectedIds.includes(p.id);
            return (
              <label
                key={p.id}
                className="flex cursor-pointer items-center gap-3 rounded-xl border border-border p-3 transition-colors hover:bg-muted"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={mode === "immediate" && (addImmediate.isPending || removeImmediate.isPending)}
                  onChange={(e) => void handleToggle(p, e.target.checked)}
                  className="rounded accent-primary"
                />
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{p.name}</span>
                <span className="text-xs tabular-nums text-muted-foreground">{p.video_count}</span>
              </label>
            );
          })}
        </div>
      )}
      <Field label="Create playlist">
        <div className="flex gap-2">
          <input
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void handleCreate();
              }
            }}
            placeholder="Name"
            className="min-w-0 flex-1 rounded-xl border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
          />
          <ActionButton
            variant="secondary"
            size="sm"
            icon={<Plus size={13} />}
            isPending={creating}
            disabled={!createName.trim()}
            onClick={() => void handleCreate()}
          >
            Create playlist
          </ActionButton>
        </div>
      </Field>
    </div>
  );
}
