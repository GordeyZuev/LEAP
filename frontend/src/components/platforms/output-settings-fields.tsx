"use client";

import { Toggle } from "@/components/ui/toggle";
import {
  LeapConfigFields,
  type LeapPresetOption,
} from "@/components/platforms/leap-config-section";
import { UploadCopyFields, type UploadCopyPresetOption } from "@/components/platforms/upload-copy-fields";

export interface OutputSettingsFieldsProps {
  publishLeap: boolean;
  onPublishLeapChange: (value: boolean) => void;
  showCourses?: boolean;
  playlistIds: number[];
  onPlaylistIdsChange: (ids: number[]) => void;
  leapPresets: LeapPresetOption[];
  selectedLeapPresetId: number | null;
  onLeapPresetIdChange: (id: number | null) => void;
  copyPresets: UploadCopyPresetOption[];
  selectedCopyPresetIds: number[];
  onSelectedCopyPresetIdsChange: (ids: number[]) => void;
  autoUpload: boolean;
  onAutoUploadChange: (value: boolean) => void;
  uploadCaptions: boolean;
  onUploadCaptionsChange: (value: boolean) => void;
  autoUploadWarning?: string;
}

/** Template editor: LEAP + upload copy in one card. */
export function OutputSettingsFields({
  publishLeap,
  onPublishLeapChange,
  showCourses = true,
  playlistIds,
  onPlaylistIdsChange,
  leapPresets,
  selectedLeapPresetId,
  onLeapPresetIdChange,
  copyPresets,
  selectedCopyPresetIds,
  onSelectedCopyPresetIdsChange,
  autoUpload,
  onAutoUploadChange,
  uploadCaptions,
  onUploadCaptionsChange,
  autoUploadWarning,
}: OutputSettingsFieldsProps) {
  return (
    <>
      <div className="space-y-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">LEAP</p>
        <Toggle
          label="Publish to LEAP after processing"
          checked={publishLeap}
          onChange={onPublishLeapChange}
        />
        {publishLeap ? (
          <LeapConfigFields
            variant="template"
            showCourses={showCourses}
            playlistIds={playlistIds}
            onPlaylistIdsChange={onPlaylistIdsChange}
            leapPresets={leapPresets}
            selectedLeapPresetId={selectedLeapPresetId}
            onLeapPresetIdChange={onLeapPresetIdChange}
          />
        ) : (
          <p className="text-xs text-muted-foreground">Turn on to set look, courses, and share link.</p>
        )}
      </div>

      <div className="space-y-4 border-t border-border pt-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Upload a copy</p>
        <UploadCopyFields
          copyPresets={copyPresets}
          selectedCopyPresetIds={selectedCopyPresetIds}
          onSelectedCopyPresetIdsChange={onSelectedCopyPresetIdsChange}
          autoUpload={autoUpload}
          onAutoUploadChange={onAutoUploadChange}
          uploadCaptions={uploadCaptions}
          onUploadCaptionsChange={onUploadCaptionsChange}
          autoUploadWarning={autoUploadWarning}
        />
      </div>
    </>
  );
}
