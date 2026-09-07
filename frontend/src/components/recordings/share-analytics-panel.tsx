"use client";

import { useState } from "react";
import { isAxiosError } from "axios";
import { useQuery } from "@tanstack/react-query";

import {
  fetchShareAnalytics,
  type ShareAnalyticsResponse,
} from "@/api/share";
import { getShareArtifactLabel } from "@/components/recordings/artefact-list";
import { AnalyticsSummaryCards } from "@/components/charts/analytics-summary-cards";
import { ChartCard } from "@/components/charts/chart-card";
import { DailyBarChart } from "@/components/charts/daily-bar-chart";
import { DateRangeFilter } from "@/components/filters/date-range-filter";
import { StatRow } from "@/components/settings/shared";
import { ActionButton } from "@/components/ui/action-button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  defaultAnalyticsRange,
  presetRange,
  type AnalyticsDateRange,
  type DateRangePreset,
  validateRange,
} from "@/lib/analytics-date-range";
import { formatRelative } from "@/lib/utils";

function sumDailyMetric(
  daily: ShareAnalyticsResponse["daily"],
  key: "views" | "downloads",
): number {
  return daily.reduce((sum, point) => sum + point[key], 0);
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
  showRevokedBanner,
}: {
  recordingId: number;
  open: boolean;
  showRevokedBanner: boolean;
}) {
  const [range, setRangeState] = useState<AnalyticsDateRange>(() => defaultAnalyticsRange());
  const [preset, setPreset] = useState<DateRangePreset>("28d");
  const validationError = validateRange(range.from, range.to);
  const isValid = validationError === null;

  const setRange = (next: AnalyticsDateRange, nextPreset: DateRangePreset = "custom") => {
    setRangeState(next);
    setPreset(nextPreset);
  };

  const applyPreset = (p: Exclude<DateRangePreset, "custom">) => {
    setRange(presetRange(p), p);
  };

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["share-analytics", recordingId, range.from, range.to],
    queryFn: () => fetchShareAnalytics(recordingId, { from: range.from, to: range.to }),
    enabled: open && recordingId > 0 && isValid,
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

  const viewsChart = data?.daily.map((point) => ({ date: point.date, value: point.views })) ?? [];
  const downloadsChart = data?.daily.map((point) => ({ date: point.date, value: point.downloads })) ?? [];

  return (
    <div className="space-y-5">
      {showRevokedBanner && (
        <p className="rounded-xl border border-border bg-muted/40 px-3 py-2.5 text-xs text-muted-foreground">
          Link disabled · activity history kept
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Analytics</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">Anonymous views and file downloads</p>
        </div>
      </div>

      <DateRangeFilter
        range={range}
        preset={preset}
        onRangeChange={(next) => setRange(next, "custom")}
        onPresetChange={applyPreset}
        validationError={validationError}
      />

      {isPending && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Skeleton className="h-20 rounded-xl" />
            <Skeleton className="h-20 rounded-xl" />
          </div>
          <Skeleton className="h-48 rounded-xl" />
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

      {data && !isPending && isValid && (
        <div className="space-y-5">
          <AnalyticsSummaryCards
            items={[
              { label: "Views", value: String(periodViews), hint: "Selected period" },
              { label: "Downloads", value: String(periodDownloads), hint: "Selected period" },
            ]}
          />

          <ChartCard
            title="Views per day"
            isEmpty={viewsChart.every((p) => p.value === 0)}
            emptyMessage="No views in this period"
          >
            <DailyBarChart data={viewsChart} valueLabel="Views" />
          </ChartCard>

          <ChartCard
            title="Downloads per day"
            isEmpty={downloadsChart.every((p) => p.value === 0)}
            emptyMessage="No downloads in this period"
          >
            <DailyBarChart data={downloadsChart} valueLabel="Downloads" />
          </ChartCard>

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
