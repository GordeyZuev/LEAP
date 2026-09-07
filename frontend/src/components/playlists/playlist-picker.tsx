"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import { addPlaylistItems, createPlaylist, listPlaylists, removePlaylistItem, type PlaylistListItem } from "@/api/playlists";
import { ActionButton } from "@/components/ui/action-button";
import { ChecklistPicker } from "@/components/ui/checklist-picker";
import { extractApiError } from "@/lib/utils";

const EMPTY_PLAYLISTS: PlaylistListItem[] = [];

interface PlaylistPickerProps {
  mode: "immediate" | "form";
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  recordingId?: number;
  membershipItemIds?: Record<number, number>;
  onToast?: (message: string, variant?: "success" | "error") => void;
  id?: string;
  "aria-describedby"?: string;
  /** Parent already shows a dialog (recording page). */
  embedded?: boolean;
}

export function PlaylistPicker({
  mode,
  selectedIds,
  onChange,
  recordingId,
  membershipItemIds,
  onToast,
  id,
  "aria-describedby": describedBy,
  embedded = false,
}: PlaylistPickerProps) {
  const qc = useQueryClient();
  const [createName, setCreateName] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);

  const { data } = useQuery({
    queryKey: ["playlists", "picker"],
    queryFn: () => listPlaylists({ per_page: 100, sort_by: "name", sort_order: "asc" }),
  });

  const playlists = data?.items ?? EMPTY_PLAYLISTS;
  const items = useMemo(
    () =>
      playlists.map((p) => ({
        value: p.id,
        label: p.name,
        hint: `${p.video_count} ${p.video_count === 1 ? "video" : "videos"}`,
      })),
    [playlists],
  );

  async function applyImmediate(next: number[]) {
    if (!recordingId) return;
    const prev = new Set(selectedIds);
    const nextSet = new Set(next);
    const removed = selectedIds.filter((pid) => !nextSet.has(pid));
    const added = next.filter((pid) => !prev.has(pid));
    setBusy(true);
    try {
      for (const playlistId of removed) {
        const itemId = membershipItemIds?.[playlistId];
        if (!itemId) continue;
        await removePlaylistItem(playlistId, itemId);
      }
      for (const playlistId of added) {
        await addPlaylistItems(playlistId, [recordingId]);
      }
      onChange(next);
      void qc.invalidateQueries({ queryKey: ["playlists"] });
      void qc.invalidateQueries({ queryKey: ["recording"] });
      if (added.length > 0) onToast?.("Added to playlist", "success");
      else if (removed.length > 0) onToast?.("Removed from playlist", "success");
    } catch (e) {
      onToast?.(extractApiError(e, "Failed to update playlists"), "error");
    } finally {
      setBusy(false);
    }
  }

  function handleChange(next: number[]) {
    if (mode === "form") {
      onChange(next);
      return;
    }
    void applyImmediate(next);
  }

  async function handleCreate() {
    const name = createName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await createPlaylist({ name });
      void qc.invalidateQueries({ queryKey: ["playlists"] });
      setCreateName("");
      if (mode === "form") {
        onChange([...selectedIds, created.id]);
      } else if (recordingId) {
        await addPlaylistItems(created.id, [recordingId]);
        onChange([...selectedIds, created.id]);
        void qc.invalidateQueries({ queryKey: ["recording"] });
        onToast?.("Added to playlist", "success");
      }
    } catch (e) {
      onToast?.(extractApiError(e, "A playlist with this name already exists."), "error");
    } finally {
      setCreating(false);
    }
  }

  return (
    <ChecklistPicker
      id={id}
      aria-describedby={describedBy}
      title="Select courses"
      ariaLabel="Courses"
      emptyLabel="No courses selected"
      searchPlaceholder="Search courses"
      items={items}
      value={selectedIds}
      onChange={handleChange}
      disabled={busy}
      embedded={embedded}
      footer={
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
            placeholder="New course name"
            className="min-w-0 flex-1 rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
          />
          <ActionButton
            variant="secondary"
            size="sm"
            icon={<Plus size={13} />}
            isPending={creating}
            disabled={!createName.trim()}
            onClick={() => void handleCreate()}
          >
            Create
          </ActionButton>
        </div>
      }
    />
  );
}
