"use client";

import { Field } from "@/components/ui/field";
import { Toggle } from "@/components/ui/toggle";
import { ChecklistPicker } from "@/components/ui/checklist-picker";
import { CreatePlaceholder } from "@/components/ui/create-placeholder";

export interface UploadCopyPresetOption {
  id: number;
  name: string;
  platform: string;
}

export interface UploadCopyFieldsProps {
  copyPresets: UploadCopyPresetOption[];
  selectedCopyPresetIds: number[];
  onSelectedCopyPresetIdsChange: (ids: number[]) => void;
  autoUpload: boolean;
  onAutoUploadChange: (value: boolean) => void;
  uploadCaptions: boolean;
  onUploadCaptionsChange: (value: boolean) => void;
  /** Shown when auto-upload is on but no copy preset is selected. */
  autoUploadWarning?: string;
  autoUploadHint?: string;
}

/** YouTube / Yandex Disk copy upload — paired with LEAP in template and run config. */
export function UploadCopyFields({
  copyPresets,
  selectedCopyPresetIds,
  onSelectedCopyPresetIdsChange,
  autoUpload,
  onAutoUploadChange,
  uploadCaptions,
  onUploadCaptionsChange,
  autoUploadWarning,
  autoUploadHint,
}: UploadCopyFieldsProps) {
  const selectedCopyCount = selectedCopyPresetIds.length;

  return (
    <>
      {copyPresets.length > 0 ? (
        <Field label="Output presets" hint="Copy to YouTube or Yandex Disk.">
          <ChecklistPicker
            title="Select presets"
            ariaLabel="Output presets"
            emptyLabel="No upload presets selected"
            searchPlaceholder="Search presets"
            items={copyPresets.map((p) => ({
              value: p.id,
              label: p.name,
              hint: p.platform,
              group: p.platform,
            }))}
            value={selectedCopyPresetIds}
            onChange={onSelectedCopyPresetIdsChange}
          />
        </Field>
      ) : (
        <Field label="Output presets" hint="Copy to YouTube or Yandex Disk.">
          <CreatePlaceholder href="/presets/new" label="Add upload preset" />
        </Field>
      )}
      <Toggle
        label="Auto-upload after processing"
        hint={autoUploadHint}
        checked={autoUpload}
        onChange={(v) => {
          if (v && selectedCopyCount === 0) return;
          onAutoUploadChange(v);
        }}
      />
      {autoUploadWarning ? <p className="text-sm text-muted-foreground">{autoUploadWarning}</p> : null}
      <Toggle
        label="Upload captions / subtitles"
        checked={uploadCaptions}
        onChange={onUploadCaptionsChange}
      />
    </>
  );
}
