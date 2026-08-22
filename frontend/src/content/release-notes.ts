import { APP_VERSION } from "@/lib/app-version";

export type ReleaseNotePart =
  | { kind: "text"; value: string }
  | { kind: "link"; label: string; href: string };

export interface ReleaseNoteHighlight {
  parts: ReleaseNotePart[];
}

export interface ReleaseNotesContent {
  title: string;
  highlights: ReleaseNoteHighlight[];
}

/**
 * Release notes keyed by semver. Add a new entry on each user-visible release.
 */
export const RELEASE_NOTES_BY_VERSION: Record<string, ReleaseNotesContent> = {
  "0.10.7.0": {
    title: "Base template, share pages & publications",
    highlights: [
      {
        parts: [
          { kind: "text", value: "Processing, metadata, and upload defaults now live in your " },
          { kind: "link", label: "base template", href: "/settings" },
          { kind: "text", value: ". Open it from " },
          { kind: "link", label: "Settings → Account", href: "/settings" },
          { kind: "text", value: " or " },
          { kind: "link", label: "Templates", href: "/templates" },
          { kind: "text", value: "." },
        ],
      },
      {
        parts: [
          { kind: "text", value: "Need a different base? Go to " },
          { kind: "link", label: "Templates", href: "/templates" },
          {
            kind: "text",
            value: ", open a template, then More → Make base template. Your previous base stays as a named template.",
          },
        ],
      },
      {
        parts: [
          { kind: "text", value: "The Processing tab in Settings is removed — use your base template for pipeline defaults. " },
          { kind: "link", label: "Data retention", href: "/settings" },
          { kind: "text", value: " is now under Settings → Account." },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value: "Public share pages use a new watch layout: video on the left, chapters and topics in a sticky panel beside the player.",
          },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "When a recording has a public link, the active LEAP URL appears in Publications on the recording page and as a green badge in the ",
          },
          { kind: "link", label: "Recordings", href: "/recordings" },
          { kind: "text", value: " list — alongside YouTube and VK links." },
        ],
      },
    ],
  },
};

export function getReleaseNotesForVersion(version: string = APP_VERSION): ReleaseNotesContent | null {
  return RELEASE_NOTES_BY_VERSION[version] ?? null;
}
