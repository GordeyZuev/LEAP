"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addChannelPlaylists,
  addChannelVideos,
  listChannels,
  removeChannelPlaylist,
  removeChannelVideo,
  type ChannelListItem,
} from "@/api/channels";
import { ChecklistPicker } from "@/components/ui/checklist-picker";
import { extractApiError } from "@/lib/utils";

const EMPTY: ChannelListItem[] = [];

function sameIdSet(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  const right = new Set(b);
  return a.every((id) => right.has(id));
}

/** The requested add/remove is visible in the server selection, which may also contain other ids. */
function selectionSettled(from: number[], next: number[], server: number[]): boolean {
  const have = new Set(server);
  const base = new Set(from);
  const want = new Set(next);
  for (const id of want) {
    if (!base.has(id) && !have.has(id)) return false;
  }
  for (const id of base) {
    if (!want.has(id) && have.has(id)) return false;
  }
  return true;
}

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
  const inflight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ from: number[]; next: number[] } | null>(null);
  const caughtUp = pending !== null && selectionSettled(pending.from, pending.next, selectedIds);
  if (caughtUp) setPending(null);
  const shownIds = pending && !caughtUp ? pending.next : selectedIds;

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

  async function applyImmediate(prevIds: number[], next: number[]) {
    const prev = new Set(prevIds);
    const nextSet = new Set(next);
    const removed = prevIds.filter((cid) => !nextSet.has(cid));
    const added = next.filter((cid) => !prev.has(cid));
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
      if (added.length > 0) onToast?.("Added to channel", "success");
      else if (removed.length > 0) onToast?.("Removed from channel", "success");
    } catch (e) {
      setPending(null);
      onToast?.(extractApiError(e, "Failed to update channels"), "error");
    } finally {
      inflight.current = false;
      setBusy(false);
      void qc.invalidateQueries({ queryKey: ["channels"] });
      void qc.invalidateQueries({ queryKey: ["recording"] });
      void qc.invalidateQueries({ queryKey: ["playlist"] });
      void qc.invalidateQueries({ queryKey: ["playlist-channels"] });
    }
  }

  function handleChange(next: number[]) {
    if (mode === "form") {
      onChange(next);
      return;
    }
    if (inflight.current || (!recordingId && !playlistId)) return;
    if (sameIdSet(shownIds, next)) return;
    // Set before await so a second click in this turn cannot start another request.
    inflight.current = true;
    setPending({ from: selectedIds, next });
    setBusy(true);
    void applyImmediate(shownIds, next);
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
      value={shownIds}
      onChange={handleChange}
      disabled={busy}
      embedded={embedded}
      footer={
        <Link
          href="/channels?create=1"
          className="inline-flex min-h-11 items-center text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
        >
          New channel
        </Link>
      }
    />
  );
}
