"use client";

import { Field } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { CreatePlaceholder } from "@/components/ui/create-placeholder";
import { PlaylistPicker } from "@/components/playlists/playlist-picker";
import { ChannelPicker } from "@/components/playlists/channel-picker";
import type { LeapFieldsValue } from "@/components/platforms/platform-fields";

export type LeapConfigVariant = "template" | "run";

export interface LeapPresetOption {
  id: number;
  name: string;
}

export interface LeapPresetMetadata {
  title_template?: string;
  description_template?: string;
  thumbnail_name?: string;
  auto_share?: boolean;
  playlist_ids?: number[];
  channel_ids?: number[];
}

export function leapPresetMetadataFromApi(raw: unknown): LeapPresetMetadata {
  const obj = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const playlistIds = Array.isArray(obj.playlist_ids)
    ? obj.playlist_ids.filter((n): n is number => typeof n === "number" && n > 0)
    : [];
  const channelIds = Array.isArray(obj.channel_ids)
    ? obj.channel_ids.filter((n): n is number => typeof n === "number" && n > 0)
    : [];
  return {
    title_template: typeof obj.title_template === "string" ? obj.title_template : undefined,
    description_template: typeof obj.description_template === "string" ? obj.description_template : undefined,
    thumbnail_name: typeof obj.thumbnail_name === "string" ? obj.thumbnail_name : undefined,
    auto_share: typeof obj.auto_share === "boolean" ? obj.auto_share : undefined,
    playlist_ids: playlistIds.length > 0 ? playlistIds : undefined,
    channel_ids: channelIds.length > 0 ? channelIds : undefined,
  };
}

export function filterLeapPresets<T extends { platform: string; name: string }>(items: T[]): T[] {
  return items.filter((p) => p.platform === "leap").sort((a, b) => a.name.localeCompare(b.name));
}

export interface LeapConfigFieldsProps {
  variant: LeapConfigVariant;
  showCourses?: boolean;
  playlistIds: number[];
  onPlaylistIdsChange: (ids: number[]) => void;
  channelIds?: number[];
  onChannelIdsChange?: (ids: number[]) => void;
  leapPresets: LeapPresetOption[];
  selectedLeapPresetId: number | null;
  onLeapPresetIdChange: (id: number | null) => void;
  lookDisabled?: boolean;
}

/**
 * LEAP output block: courses + look preset (+ optional metadata overrides).
 * Used in template editor, Run with config, and per-recording config (same modal).
 */
export function LeapConfigFields({
  variant,
  showCourses = true,
  playlistIds,
  onPlaylistIdsChange,
  channelIds = [],
  onChannelIdsChange,
  leapPresets,
  selectedLeapPresetId,
  onLeapPresetIdChange,
  lookDisabled = false,
}: LeapConfigFieldsProps) {
  const noneLabel =
    variant === "template" ? "None — use global metadata templates" : "None — inherit from template";

  const hasLeapPresets = leapPresets.length > 0;
  const playlistHint =
    variant === "template"
      ? "After processing, adds recordings to these LEAP courses. Leave empty to use the preset’s playlists."
      : "After processing, replaces template courses when LEAP output is overridden.";
  const channelHint =
    variant === "template"
      ? "After processing the recording is added to the Videos tab. Viewers see it only if the recording has a share link (LEAP auto_share or Enable link). Empty list = same as the preset."
      : "Replaces template channels when LEAP output is overridden. Empty = inherit.";

  const presetHint =
    !hasLeapPresets
      ? "Create a LEAP preset first."
      : lookDisabled
        ? "Bulk: enable LEAP override."
        : variant === "template"
          ? "Look for title, description, and cover on LEAP. Optional if you rely on global metadata."
          : "Look preset for this run. Clear to inherit from the template.";

  return (
    <>
      <Field label="LEAP preset" hint={presetHint}>
        {!hasLeapPresets ? (
          <CreatePlaceholder href="/presets/new" label="New LEAP preset" />
        ) : (
          <NativeSelect
            ariaLabel="LEAP preset"
            value={selectedLeapPresetId ?? ""}
            disabled={lookDisabled}
            onChange={(e) => onLeapPresetIdChange(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{noneLabel}</option>
            {leapPresets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>

      {showCourses ? (
        <>
          <Field label="LEAP playlists" hint={playlistHint}>
            <PlaylistPicker mode="form" selectedIds={playlistIds} onChange={onPlaylistIdsChange} />
          </Field>
          {onChannelIdsChange ? (
            <Field label="LEAP channels" hint={channelHint}>
              <ChannelPicker mode="form" selectedIds={channelIds} onChange={onChannelIdsChange} />
            </Field>
          ) : null}
        </>
      ) : null}
    </>
  );
}

export function LeapFillFromPresetButton({
  metadata,
  onApply,
}: {
  metadata?: LeapPresetMetadata | null;
  onApply: (patch: Partial<LeapFieldsValue>) => void;
}) {
  if (!metadata) return null;
  const hasTemplate = Boolean(metadata.title_template?.trim() || metadata.description_template?.trim());
  if (!hasTemplate) return null;

  return (
    <button
      type="button"
      onClick={() =>
        onApply({
          title_template: metadata.title_template ?? "",
          description_template: metadata.description_template ?? "",
          thumbnail_name: metadata.thumbnail_name ?? "",
          ...(metadata.auto_share !== undefined ? { auto_share: metadata.auto_share } : {}),
        })
      }
      className="text-xs font-medium text-primary hover:underline"
    >
      Fill from LEAP preset
    </button>
  );
}
