import { formatRelative } from "@/lib/utils";

export interface ShareStatsSummary {
  view_count: number;
  download_count: number;
  last_viewed_at: string | null;
  last_downloaded_at: string | null;
}

export function lastShareActivity(summary: ShareStatsSummary): string | null {
  const candidates = [summary.last_viewed_at, summary.last_downloaded_at].filter(
    (value): value is string => Boolean(value),
  );
  if (candidates.length === 0) return null;
  return candidates.reduce((latest, current) =>
    new Date(current) > new Date(latest) ? current : latest,
  );
}

function formatCount(count: number, singular: string, plural: string): string {
  return count === 1 ? `1 ${singular}` : `${count} ${plural}`;
}

/** One-line summary for Publications row and list tooltips. */
export function formatShareStatsSummary(summary: ShareStatsSummary | null | undefined): string {
  if (!summary) return "";

  const views = summary.view_count ?? 0;
  const downloads = summary.download_count ?? 0;

  if (views === 0 && downloads === 0) {
    return "No activity yet";
  }

  const parts: string[] = [];
  if (views > 0) {
    parts.push(formatCount(views, "view", "views"));
  }
  if (downloads > 0) {
    parts.push(formatCount(downloads, "download", "downloads"));
  }

  const activity = lastShareActivity(summary);
  if (activity) {
    const label =
      views > 0 && downloads > 0
        ? "Last activity"
        : views > 0
          ? "Last viewed"
          : "Last download";
    parts.push(`${label} ${formatRelative(activity)}`);
  }

  return parts.join(" · ");
}
