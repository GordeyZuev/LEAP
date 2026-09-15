"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import {
  addChannelPlaylists,
  addChannelVideos,
  createChannel,
  listChannels,
  removeChannelPlaylist,
  removeChannelVideo,
  type ChannelListItem,
} from "@/api/channels";
import { ActionButton } from "@/components/ui/action-button";
import { ChecklistPicker } from "@/components/ui/checklist-picker";
import { extractApiError } from "@/lib/utils";

const EMPTY: ChannelListItem[] = [];

interface ChannelPickerProps {
  mode: "immediate" | "form";
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  recordingId?: number;
  playlistId?: number;
  onToast?: (message: string, variant?: "success" | "error") => void;
  id?: string;
  "aria-describedby"?: string;
  embedded?: boolean;
}

export function ChannelPicker({
  mode,
  selectedIds,
  onChange,
  recordingId,
  playlistId,
  onToast,
  id,
  "aria-describedby": describedBy,
  embedded = false,
}: ChannelPickerProps) {
  const qc = useQueryClient();
  const [createName, setCreateName] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);

  const { data } = useQuery({
    queryKey: ["channels", "picker"],
    queryFn: () => listChannels({ per_page: 100, sort_by: "name", sort_order: "asc" }),
  });

  const channels = data?.items ?? EMPTY;
  const items = useMemo(
    () =>
      channels.map((c) => ({
        value: c.id,
        label: c.name,
        hint: `/${c.slug}`,
      })),
    [channels],
  );

  async function applyImmediate(next: number[]) {
    if (!recordingId && !playlistId) return;
    const prev = new Set(selectedIds);
    const nextSet = new Set(next);
    const removed = selectedIds.filter((cid) => !nextSet.has(cid));
    const added = next.filter((cid) => !prev.has(cid));
    setBusy(true);
    try {
      for (const channelId of removed) {
        if (recordingId) await removeChannelVideo(channelId, recordingId);
        if (playlistId) await removeChannelPlaylist(channelId, playlistId);
      }
      for (const channelId of added) {
        if (recordingId) await addChannelVideos(channelId, [recordingId]);
        if (playlistId) await addChannelPlaylists(channelId, [playlistId]);
      }
      onChange(next);
      void qc.invalidateQueries({ queryKey: ["channels"] });
      void qc.invalidateQueries({ queryKey: ["recording"] });
      void qc.invalidateQueries({ queryKey: ["playlist"] });
      void qc.invalidateQueries({ queryKey: ["playlist-channels"] });
      if (added.length > 0) onToast?.("Added to channel", "success");
      else if (removed.length > 0) onToast?.("Removed from channel", "success");
    } catch (e) {
      onToast?.(extractApiError(e, "Failed to update channels"), "error");
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
      const created = await createChannel({ name });
      void qc.invalidateQueries({ queryKey: ["channels"] });
      setCreateName("");
      if (mode === "form") {
        onChange([...selectedIds, created.id]);
      } else if (recordingId) {
        await addChannelVideos(created.id, [recordingId]);
        onChange([...selectedIds, created.id]);
        void qc.invalidateQueries({ queryKey: ["recording"] });
        onToast?.("Added to channel", "success");
      } else if (playlistId) {
        await addChannelPlaylists(created.id, [playlistId]);
        onChange([...selectedIds, created.id]);
        void qc.invalidateQueries({ queryKey: ["playlist"] });
        onToast?.("Added to channel", "success");
      }
    } catch (e) {
      onToast?.(extractApiError(e, "Could not create channel."), "error");
    } finally {
      setCreating(false);
    }
  }

  return (
    <ChecklistPicker
      id={id}
      aria-describedby={describedBy}
      title="Select channels"
      ariaLabel="Channels"
      emptyLabel="No channels selected"
      searchPlaceholder="Search channels"
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
            placeholder="New channel name"
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
