"use client";

import { Suspense, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  buildStackedUploadRows,
  dailyMetric,
  fetchUserAnalytics,
} from "@/api/analytics";
import { apiClient } from "@/api/client";
import { AnalyticsSummaryCards, type SummaryCardItem } from "@/components/charts/analytics-summary-cards";
import { ChartCard } from "@/components/charts/chart-card";
import { DailyBarChart } from "@/components/charts/daily-bar-chart";
import { DailyStackedBarChart } from "@/components/charts/daily-stacked-bar-chart";
import { HorizontalBreakdownChart } from "@/components/charts/horizontal-breakdown-chart";
import { DateRangeFilter, USAGE_DATE_PRESETS } from "@/components/filters/date-range-filter";
import { StatRow } from "@/components/settings/shared";
import type { QuotaStatus } from "@/components/settings/types";
import { COUNT_FORMATTER, fmtQuotaPair } from "@/components/settings/format";
import { useAnalyticsDateRange } from "@/hooks/use-analytics-date-range";
import { chooseChartGranularity, granularityPeriodLabel } from "@/lib/chart-bucketing";
import { rangeSpanDays } from "@/lib/analytics-date-range";
import { useMe } from "@/lib/react-query";
import { cn } from "@/lib/utils";

interface QuotaRowConfig {
  label: string;
  used: number;
  limit: number | null | undefined;
  unit?: string;
  decimals?: number;
}

function buildQuotaRows(quota: QuotaStatus): QuotaRowConfig[] {
  return [
    {
      label: "Recordings / month",
      used: quota.recordings?.used ?? 0,
      limit: quota.recordings?.limit ?? null,
    },
    {
      label: "Storage",
      used: quota.storage?.used_gb ?? 0,
      limit: quota.storage?.limit_gb ?? null,
      unit: "GB",
      decimals: 2,
    },
    {
      label: "Concurrent tasks",
      used: quota.concurrent_tasks?.used ?? 0,
      limit: quota.concurrent_tasks?.limit ?? null,
    },
    {
      label: "Automation jobs",
      used: quota.automation_jobs?.used ?? 0,
      limit: quota.automation_jobs?.limit ?? null,
    },
    {
      label: "Transcriptions / month",
      used: quota.transcriptions?.used ?? 0,
      limit: quota.transcriptions?.limit ?? null,
    },
    {
      label: "Processing / month",
      used: quota.processing?.used ?? 0,
      limit: quota.processing?.limit ?? null,
    },
    {
      label: "Templates",
      used: quota.templates?.used ?? 0,
      limit: quota.templates?.limit ?? null,
    },
    {
      label: "Credentials",
      used: quota.credentials?.used ?? 0,
      limit: quota.credentials?.limit ?? null,
    },
  ];
}

function QuotaRow({ label, used, limit, unit, decimals }: QuotaRowConfig) {
  return (
    <div>
      <StatRow label={label} value={fmtQuotaPair(used, limit, { unit, decimals })} />
      <QuotaProgress used={used} limit={limit} />
    </div>
  );
}

function QuotaProgress({ used, limit }: { used: number; limit: number | null | undefined }) {
  if (limit == null || limit <= 0) return null;
  const pct = Math.min(100, (used / limit) * 100);
  const over = used > limit;
  return (
    <div className="mb-2 h-1 w-full overflow-hidden rounded-full bg-muted">
      <div
        className={cn("h-full rounded-full transition-[width]", over ? "bg-amber-500" : "bg-primary")}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function UsagePanelContent() {
  const { data: userData } = useMe();
  const { range, preset, validationError, setRange, applyPreset, isValid } = useAnalyticsDateRange(
    "",
    true,
    { accountCreatedAt: userData?.created_at },
  );

  const { data: quotaData, isPending: quotaPending, isError: quotaError } = useQuery<QuotaStatus>({
    queryKey: ["user-quota"],
    queryFn: async () => (await apiClient.get<QuotaStatus>("/users/me/quota")).data,
  });

  const analyticsQuery = useQuery({
    queryKey: ["user-analytics", range.from, range.to],
    queryFn: () => fetchUserAnalytics(range.from, range.to),
    enabled: isValid,
    staleTime: 60_000,
  });

  const data = analyticsQuery.data;
  const uploadChart = data ? buildStackedUploadRows(data.daily_uploads) : { rows: [], seriesKeys: [] };
  const hasShareViews = (data?.summary.share_views ?? 0) > 0;
  const statusBreakdown = data
    ? Object.entries(data.breakdown.recordings_by_status).map(([label, value]) => ({ label, value }))
    : [];
  const templateBreakdown = data
    ? data.breakdown.top_templates.map((t) => ({
        label: t.template_name ?? `Template #${t.template_id}`,
        value: t.count,
      }))
    : [];

  const periodSummary = useMemo((): SummaryCardItem[] => {
    if (!data) return [];
    return [
      { label: "Recordings", value: COUNT_FORMATTER.format(data.summary.recordings_created) },
      {
        label: "Transcribed content",
        value: `${data.summary.transcription_minutes.toFixed(1)} min`,
      },
      {
        label: "Transcription jobs",
        value: COUNT_FORMATTER.format(data.summary.transcription_jobs),
      },
      { label: "Uploads", value: COUNT_FORMATTER.format(data.summary.uploads_total) },
      ...(hasShareViews
        ? [{ label: "Share views", value: COUNT_FORMATTER.format(data.summary.share_views) }]
        : []),
    ];
  }, [data, hasShareViews]);

  const chartPeriodLabel = granularityPeriodLabel(
    chooseChartGranularity(rangeSpanDays(range.from, range.to)),
  );

  const activityDescription = "Totals and daily trends for the selected period.";
  const quotaRows = useMemo(() => (quotaData ? buildQuotaRows(quotaData) : []), [quotaData]);
  const quotaColumnSize = Math.ceil(quotaRows.length / 2);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">Quota</h2>
        {quotaPending && !quotaData ? (
          <div className="h-48 animate-pulse rounded-2xl border border-border bg-muted/40" />
        ) : quotaError ? (
          <p className="text-sm text-muted-foreground">Could not load quota. Refresh the page to try again.</p>
        ) : quotaData ? (
          <div className="rounded-2xl border border-border bg-card px-5 py-4 shadow-sm">
            <div className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
              {[0, 1].map((columnIndex) => {
                const columnRows = quotaRows.slice(
                  columnIndex * quotaColumnSize,
                  (columnIndex + 1) * quotaColumnSize,
                );
                return (
                  <div key={columnIndex}>
                    {columnRows.map((row) => (
                      <QuotaRow key={row.label} {...row} />
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>

      <div className="space-y-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Activity</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">{activityDescription}</p>
        </div>

        <DateRangeFilter
          presets={USAGE_DATE_PRESETS}
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
              periodSummary.length > 0 && <AnalyticsSummaryCards items={periodSummary} />
            )}

            <ChartCard
              title={`Recordings per ${chartPeriodLabel}`}
              description="New recordings created"
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
                description="Minutes of content after transcription"
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
                title={`Uploads per ${chartPeriodLabel}`}
                description="Successful uploads by platform"
                isLoading={analyticsQuery.isPending}
                isError={analyticsQuery.isError}
                isEmpty={uploadChart.seriesKeys.length === 0}
                emptyMessage="No uploads in this period"
              >
                <DailyStackedBarChart data={uploadChart.rows} seriesKeys={uploadChart.seriesKeys} />
              </ChartCard>

              {hasShareViews && (
                <ChartCard
                  title={`Share views per ${chartPeriodLabel}`}
                  className="lg:col-span-2"
                  isLoading={analyticsQuery.isPending}
                  isError={analyticsQuery.isError}
                >
                  <DailyBarChart
                    data={dailyMetric(data?.daily ?? [], "share_views")}
                    valueLabel="Views"
                    height={200}
                  />
                </ChartCard>
              )}
            </div>

            {(statusBreakdown.length > 0 || templateBreakdown.length > 0) && (
              <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
                {statusBreakdown.length > 0 && (
                  <ChartCard title="Recordings by status" description="In selected period">
                    <HorizontalBreakdownChart data={statusBreakdown} />
                  </ChartCard>
                )}
                {templateBreakdown.length > 0 && (
                  <ChartCard title="Top templates" description="In selected period">
                    <HorizontalBreakdownChart data={templateBreakdown} />
                  </ChartCard>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function UsagePanel() {
  return (
    <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl border border-border bg-card" />}>
      <UsagePanelContent />
    </Suspense>
  );
}
