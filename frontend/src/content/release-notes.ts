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
  "0.10.8.3": {
    title: "Usage, analytics, and polish",
    highlights: [
      {
        parts: [
          { kind: "text", value: "Open " },
          { kind: "link", label: "Settings → Usage", href: "/settings?tab=usage" },
          {
            kind: "text",
            value:
              " to see all plan quotas as used / limit (including automation jobs) and activity charts for any period up to 366 days.",
          },
        ],
      },
      {
        parts: [
          { kind: "text", value: "Charts cover new recordings, transcribed minutes, uploads by platform, and share views; long ranges group by week or month automatically." },
        ],
      },
      {
        parts: [
          { kind: "text", value: "Admins: platform " },
          { kind: "link", label: "Analytics", href: "/admin" },
          {
            kind: "text",
            value:
              " and per-user Activity in the user editor (same charts plus recent account events). Share link stats support custom date ranges.",
          },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "Lists (playlists, templates, sources, and more) load faster and no longer flash empty when you switch pages.",
          },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "Recording and playlist thumbnails stay steady while statuses update in the background — no more flickering posters every few seconds.",
          },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "MTS Link trim removes long silent tail at the end of a slot so you are not billed for hours of empty audio.",
          },
        ],
      },
      {
        parts: [
          { kind: "text", value: "On " },
          { kind: "link", label: "Automations", href: "/automation" },
          {
            kind: "text",
            value:
              ", Dry run syncs sources and lists which recordings would start — it does not run the pipeline. Manual Run asks first. Open a history row to see recordings from that run.",
          },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "Opening a public share while signed in to LEAP still counts as a view on Manage share and Usage charts.",
          },
        ],
      },
      {
        parts: [
          { kind: "link", label: "Documentation", href: "/docs" },
          { kind: "text", value: " in the app now has searchable FAQ and a 12+ age rating on public pages." },
        ],
      },
    ],
  },
  "0.10.8.2": {
    title: "Courses, configs, and MTS Link",
    highlights: [
      {
        parts: [
          { kind: "text", value: "Playlist and Overview text can be bold, italic, underlined, or linked. On a public " },
          { kind: "link", label: "playlist", href: "/playlists" },
          {
            kind: "text",
            value:
              " page, video count, total length, and the item list fill in automatically. From the playlist list you can open or copy the share link. YouTube and VK still get plain text.",
          },
        ],
      },
      {
        parts: [
          { kind: "text", value: "A " },
          { kind: "link", label: "LEAP look", href: "/presets" },
          {
            kind: "text",
            value:
              " preset sets title, description, and cover for LEAP without uploading a copy. Courses stay on the recording, separate from Upload a copy.",
          },
        ],
      },
      {
        parts: [
          { kind: "text", value: "MTS Link lectures shorter than 10 minutes are marked blank and skipped. Sync no longer creates duplicate rows." },
        ],
      },
      {
        parts: [
          { kind: "text", value: "Template, preset, automation, and Run with config share the same editors: inherit a whole block or override it, timestamps live under Extra timestamps, and processing extras sit in Advanced." },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "Lists show duration after trim. Public share can include chat and materials from the source when file download is allowed. In the player, J and L skip ten seconds, and the question-mark key lists shortcuts.",
          },
        ],
      },
    ],
  },
  "0.10.8.1": {
    title: "Playlists and player stability",
    highlights: [
      {
        parts: [
          { kind: "text", value: "Build a course from your recordings in " },
          { kind: "link", label: "Playlists", href: "/playlists" },
          {
            kind: "text",
            value:
              " — one public link for the whole set. Enable, disable (same URL), or rotate the link. Named templates can add new recordings automatically.",
          },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "On a phone the player is easier to use: a short control bar, video fills the screen when you rotate to landscape, and the same loading frame as on desktop.",
          },
        ],
      },
      {
        parts: [
          { kind: "text", value: "Paste a video URL in " },
          { kind: "link", label: "Recordings", href: "/recordings" },
          {
            kind: "text",
            value: " → Add video and you get a thumbnail, title, duration, and the qualities that URL actually has.",
          },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "A public share link pasted into Telegram (or another chat) shows a card with the recording poster and title.",
          },
        ],
      },
    ],
  },
  "0.10.8.0": {
    title: "MTS Link recordings & connection checks",
    highlights: [
      {
        parts: [
          {
            kind: "text",
            value:
              "Share links track views and downloads — open Manage share on a recording for counts and a 7/28-day chart.",
          },
        ],
      },
      {
        parts: [
          { kind: "text", value: "MTS Link is now an input source: add the organization API key in " },
          { kind: "link", label: "Credentials", href: "/credentials" },
          { kind: "text", value: ", then list the lecturers to sync in " },
          { kind: "link", label: "Sources", href: "/sources" },
          {
            kind: "text",
            value:
              ". LEAP orders the MP4 from them when you download a recording, and the session chat and materials come along with it.",
          },
        ],
      },
      {
        parts: [
          { kind: "text", value: "Every connection in " },
          { kind: "link", label: "Credentials", href: "/credentials" },
          {
            kind: "text",
            value: " has a Check button that asks the platform whether the key still works.",
          },
        ],
      },
      {
        parts: [
          {
            kind: "text",
            value:
              "Smaller UI fixes: secret fields have a reveal toggle, and typing in a dialog no longer loses focus after each character.",
          },
        ],
      },
    ],
  },
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
