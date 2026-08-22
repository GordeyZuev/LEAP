/** User-facing label for the account base (default) template. */
export function formatBaseTemplateLabel(name?: string | null): string {
  const trimmed = name?.trim();
  if (!trimmed || trimmed.toLowerCase() === "default") {
    return "Default template";
  }
  return `${trimmed} (Default)`;
}
