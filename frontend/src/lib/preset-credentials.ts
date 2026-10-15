export interface PresetCredentialReference {
  platform: string;
  credential_id?: number | null;
}

export function firstCredentialForPlatform(
  presetIds: readonly number[],
  presetDetails: Readonly<Record<number, PresetCredentialReference>>,
  platform: string,
): number | null {
  for (const presetId of presetIds) {
    const preset = presetDetails[presetId];
    if (preset?.platform === platform && preset.credential_id != null) return preset.credential_id;
  }
  return null;
}
