"use client";

import { isAxiosError } from "axios";
import { useQuery } from "@tanstack/react-query";

import { fetchShareAnalytics, type ShareAnalyticsResponse } from "@/api/share";
import { getShareArtifactLabel } from "@/components/recordings/artefact-list";
import { SegmentedFilter } from "@/components/filters/segmented-filter";
import { StatRow } from "@/components/settings/shared";
import { ActionButton } from "@/components/ui/action-button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative } from "@/lib/utils";

const PERIOD_OPTIONS = [
  { value: 7 as const, label: "7 days" },
  { value: 28 as const, label: "28 days" },
];

function sumDailyMetric(
  daily: ShareAnalyticsResponse["daily"],
  key: "views" | "downloads",
): number {
  return daily.reduce((sum, point) => sum + point[key], 0);
}

function ShareViewsChart({
  daily,
  days,
}: {
  daily: ShareAnalyticsResponse["daily"];
  days: 7 | 28;
}) {
  const maxViews = Math.max(1, ...daily.map((point) => point.views));
  const hasViews = daily.some((point) => point.views > 0);

  if (!hasViews) {
    return (
      <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
        No views in this period
      </p>
    );
  }

  return (
    <div
      role="img"
      aria-label={`Views per day, last ${days} days`}
      className="rounded-xl border border-border bg-card px-3 py-3"
    >
      <div className="flex h-16 items-end gap-px sm:gap-0.5">
        {daily.map((point) => {
          const height = point.views > 0 ? Math.max(8, (point.views / maxViews) * 100) : 0;
          return (
            <div
              key={point.date}
              title={`${point.date}: ${point.views} views`}
              className="min-w-0 flex-1 rounded-sm bg-primary/70"
              style={{ height: `${height}%` }}
            />
          );
        })}
      </div>
    </div>
  );
}

function analyticsErrorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    if (error.response?.status === 404) {
      return "Statistics are not available for this recording.";
    }
  }
  return "Unable to load statistics.";
}

export function ShareAnalyticsPanel({
  recordingId,
  open,
  days,
  onDaysChange,
  showRevokedBanner,
}: {
  recordingId: number;
  open: boolean;
  days: 7 | 28;
  onDaysChange: (days: 7 | 28) => void;
  showRevokedBanner: boolean;
}) {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["share-analytics", recordingId, days],
    queryFn: () => fetchShareAnalytics(recordingId, days),
    enabled: open && recordingId > 0,
    staleTime: 30_000,
    refetchOnMount: "always",
  });

  const breakdown = data?.downloads_by_type
    ? Object.entries(data.downloads_by_type)
        .filter(([, count]) => count > 0)
        .sort((a, b) => b[1] - a[1])
    : [];

  const periodViews = data ? sumDailyMetric(data.daily, "views") : 0;
  const periodDownloads = data ? sumDailyMetric(data.daily, "downloads") : 0;

  return (
    <div className="space-y-5">
      {showRevokedBanner && (
        <p className="rounded-xl border border-border bg-muted/40 px-3 py-2.5 text-xs text-muted-foreground">
          Link revoked · activity history kept
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Analytics</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">Anonymous views and file downloads</p>
        </div>
        <SegmentedFilter
          label="Date range"
          labelHidden
          value={days}
          options={PERIOD_OPTIONS}
          onChange={onDaysChange}
        />
      </div>

      {isPending && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Skeleton className="h-20 rounded-xl" />
            <Skeleton className="h-20 rounded-xl" />
          </div>
          <Skeleton className="h-24 rounded-xl" />
        </div>
      )}

      {isError && !isPending && (
        <div className="rounded-xl border border-border bg-muted/30 px-4 py-4">
          <p className="text-xs text-muted-foreground">{analyticsErrorMessage(error)}</p>
          <ActionButton
            size="sm"
            variant="secondary"
            className="mt-3"
            isPending={isFetching}
            pendingLabel="Retrying…"
            onClick={() => void refetch()}
          >
            Retry
          </ActionButton>
        </div>
      )}

      {data && !isPending && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-border bg-card px-4 py-3">
              <p className="text-xs font-medium text-muted-foreground">Views</p>
              <p className="text-xs text-muted-foreground/80">Last {days} days</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-foreground">{periodViews}</p>
            </div>
            <div className="rounded-xl border border-border bg-card px-4 py-3">
              <p className="text-xs font-medium text-muted-foreground">Downloads</p>
              <p className="text-xs text-muted-foreground/80">Last {days} days</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-foreground">{periodDownloads}</p>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-foreground">Views per day</p>
            <ShareViewsChart daily={data.daily} days={days} />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-foreground">Downloads by file type</p>
            {breakdown.length > 0 ? (
              <div className="rounded-xl border border-border bg-card px-4 py-1">
                {breakdown.map(([type, count]) => (
                  <StatRow key={type} label={getShareArtifactLabel(type)} value={count} />
                ))}
              </div>
            ) : (
              <p className="rounded-xl border border-dashed border-border px-4 py-4 text-center text-xs text-muted-foreground">
                No file downloads in this period
              </p>
            )}
          </div>

          <div className="space-y-1 border-t border-border pt-4 text-xs text-muted-foreground">
            {data.summary.last_viewed_at && (
              <p>Last viewed · {formatRelative(data.summary.last_viewed_at)}</p>
            )}
            {data.summary.last_downloaded_at && (
              <p>Last download · {formatRelative(data.summary.last_downloaded_at)}</p>
            )}
            <p className="tabular-nums">
              All time · {data.summary.view_count} views · {data.summary.download_count} downloads
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
