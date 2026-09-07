"use client";

import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";

import { dailyMetric, fetchPlatformAnalytics } from "@/api/analytics";
import { AnalyticsSummaryCards } from "@/components/charts/analytics-summary-cards";
import { ChartCard } from "@/components/charts/chart-card";
import { DailyBarChart } from "@/components/charts/daily-bar-chart";
import { DateRangeFilter } from "@/components/filters/date-range-filter";
import { COUNT_FORMATTER } from "@/components/settings/format";
import { useAnalyticsDateRange } from "@/hooks/use-analytics-date-range";
import { chooseChartGranularity, granularityPeriodLabel } from "@/lib/chart-bucketing";
import { rangeSpanDays } from "@/lib/analytics-date-range";

export function AdminAnalyticsSection() {
  return (
    <Suspense fallback={<div className="h-48 animate-pulse rounded-2xl border border-border bg-card" />}>
      <AdminAnalyticsSectionContent />
    </Suspense>
  );
}

function AdminAnalyticsSectionContent() {
  const { range, preset, validationError, setRange, applyPreset, isValid } = useAnalyticsDateRange("analytics_");

  const analyticsQuery = useQuery({
    queryKey: ["admin-platform-analytics", range.from, range.to],
    queryFn: () => fetchPlatformAnalytics(range.from, range.to),
    enabled: isValid,
    staleTime: 60_000,
  });

  const data = analyticsQuery.data;

  const summaryItems = data
    ? [
        { label: "Recordings", value: COUNT_FORMATTER.format(data.summary.recordings_created) },
        {
          label: "Transcribed content",
          value: `${data.summary.transcription_minutes.toFixed(1)} min`,
        },
        {
          label: "Active users (≥1 recording)",
          value: COUNT_FORMATTER.format(data.summary.active_users_unique ?? 0),
        },
        { label: "Share views", value: COUNT_FORMATTER.format(data.summary.share_views) },
        { label: "Failed recordings", value: COUNT_FORMATTER.format(data.summary.failed_recordings) },
      ]
    : [];

  const chartPeriodLabel = granularityPeriodLabel(
    chooseChartGranularity(rangeSpanDays(range.from, range.to)),
  );

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-foreground">Analytics</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Platform activity for the selected period. Share trends and ops metrics (queues, errors): Grafana
          LEAP Overview dashboard.
        </p>
      </div>

      <DateRangeFilter
        range={range}
        preset={preset}
        onRangeChange={(next) => setRange(next, "custom")}
        onPresetChange={applyPreset}
        validationError={validationError}
      />

      {isValid && (
        <div className="space-y-6">
          {analyticsQuery.isPending && !data ? (
            <div className="h-24 animate-pulse rounded-xl bg-muted/50" />
          ) : (
            summaryItems.length > 0 && <AnalyticsSummaryCards items={summaryItems} />
          )}

          <ChartCard
            title={`Recordings per ${chartPeriodLabel}`}
            isLoading={analyticsQuery.isPending}
            isError={analyticsQuery.isError}
            isEmpty={
              !analyticsQuery.isPending &&
              dailyMetric(data?.daily ?? [], "recordings_created").every((p) => p.value === 0)
            }
          >
            <DailyBarChart
              data={dailyMetric(data?.daily ?? [], "recordings_created")}
              valueLabel="Recordings"
              height={220}
            />
          </ChartCard>

          <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard
              title={`Transcribed content per ${chartPeriodLabel}`}
              isLoading={analyticsQuery.isPending}
              isError={analyticsQuery.isError}
              isEmpty={
                !analyticsQuery.isPending &&
                dailyMetric(data?.daily ?? [], "transcription_minutes").every((p) => p.value === 0)
              }
            >
              <DailyBarChart
                data={dailyMetric(data?.daily ?? [], "transcription_minutes")}
                valueLabel="Minutes"
              />
            </ChartCard>

            <ChartCard
              title={`Active users per ${chartPeriodLabel}`}
              description="Distinct users who created a recording"
              isLoading={analyticsQuery.isPending}
              isError={analyticsQuery.isError}
              isEmpty={
                !analyticsQuery.isPending &&
                dailyMetric(data?.daily ?? [], "active_users").every((p) => p.value === 0)
              }
            >
              <DailyBarChart
                data={dailyMetric(data?.daily ?? [], "active_users")}
                valueLabel="Users"
              />
            </ChartCard>

            <ChartCard
              title={`Share views per ${chartPeriodLabel}`}
              className="lg:col-span-2"
              isLoading={analyticsQuery.isPending}
              isError={analyticsQuery.isError}
              isEmpty={
                !analyticsQuery.isPending &&
                dailyMetric(data?.daily ?? [], "share_views").every((p) => p.value === 0)
              }
            >
              <DailyBarChart
                data={dailyMetric(data?.daily ?? [], "share_views")}
                valueLabel="Views"
                height={200}
              />
            </ChartCard>
          </div>
        </div>
      )}
    </div>
  );
}
