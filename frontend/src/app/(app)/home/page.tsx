"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Video } from "lucide-react";
import { apiClient } from "@/api/client";
import { dailyMetric, fetchUserAnalytics } from "@/api/analytics";
import { formatCompactNumber } from "@/lib/format-compact-number";
import { useHydrated } from "@/hooks/use-hydrated";
import { useMe } from "@/lib/react-query";
import { presetRange } from "@/lib/analytics-date-range";
import { cn, formatDateTimeShort } from "@/lib/utils";
import { OPERATIONAL_STATES, OPERATIONAL_STATE_LABEL, operationalStateHref, type OperationalState } from "@/lib/operational-state";
import { AnalyticsSummaryCards } from "@/components/charts/analytics-summary-cards";
import { DailyBarChart } from "@/components/charts/daily-bar-chart";
import { PageHeader } from "@/components/ui/page-header";
import { CARD_SHELL } from "@/components/ui/section-card";
import { Tabs } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge, displayProcessingStatus } from "@/components/ui/status-badge";
import type { RecordingCardData } from "@/components/recordings/recording-card";
import { formatFailedStage } from "@/components/recordings/pipeline-stages";

type HomeSummary = Record<OperationalState, number> & { total: number; published: number };
type RecentRecording = RecordingCardData & { created_at: string; updated_at?: string };
interface RecordingList { items: RecentRecording[]; total: number }

const liveOptions = {
  staleTime: 30_000,
  refetchInterval: 30_000,
  refetchIntervalInBackground: false,
  refetchOnWindowFocus: "always" as const,
  refetchOnMount: "always" as const,
};
const linkClass = "pressable inline-flex min-h-8 shrink-0 items-center gap-2 rounded-md text-sm font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";
const pageClass = "mx-auto w-full min-w-0 max-w-5xl px-5 py-8 sm:px-8 lg:py-12";

function LoadingRows() {
  return <div role="status" aria-label="Loading" className="space-y-3">
    {[0, 1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
  </div>;
}

function RecordingRows({ items, errors }: { items: RecentRecording[]; errors: boolean }) {
  return <ul className="divide-y divide-border">
    {items.map((recording) => <li key={recording.id}>
      <Link href={`/recordings/${recording.id}`} className="pressable flex flex-wrap items-center justify-between gap-3 rounded-lg px-2 py-3.5 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30">
        <div className="min-w-0 flex-1 basis-40">
          <p className="truncate text-sm font-medium text-foreground" title={recording.display_name}>{recording.display_name}</p>
          <p className="mt-1 text-xs text-muted-foreground">{errors ? "Updated" : "Added"} {formatDateTimeShort(errors ? recording.updated_at ?? recording.created_at : recording.created_at)}</p>
        </div>
        {recording.on_pause && !recording.failed ? <span className="text-xs text-muted-foreground">Paused</span> :
          <StatusBadge status={displayProcessingStatus(recording.status, { onAir: recording.on_air && recording.status !== "PENDING_SOURCE", failed: recording.failed })}
            failed={recording.failed} failedStage={formatFailedStage(recording.failed_at_stage)} />}
      </Link>
    </li>)}
  </ul>;
}

export default function HomePage() {
  const hydrated = useHydrated();
  const me = useMe();
  const userId = me.data?.id;
  const [tab, setTab] = useState<"recent" | "errors" | null>(null);
  const range = presetRange("7d");
  const summary = useQuery({
    queryKey: ["home", userId, "summary"],
    queryFn: async () => (await apiClient.get<HomeSummary>("/users/me/home-summary")).data,
    enabled: !!userId,
    ...liveOptions,
  });
  // Choose the initial tab once. Polling must never move the tab while someone is reading.
  if (tab === null && (summary.data || summary.isError)) {
    setTab(summary.data && summary.data.error > 0 ? "errors" : "recent");
  }
  const recordings = useQuery({
    queryKey: ["recordings", "home", userId, tab],
    queryFn: async () => (await apiClient.get<RecordingList>("/recordings", { params: {
      operational_state: tab === "errors" ? "error" : undefined,
      per_page: 5, compact: true, include_posters: false,
      sort_by: tab === "errors" ? "updated_at" : "created_at", sort_order: "desc",
    } })).data,
    enabled: !!userId && tab !== null,
    ...liveOptions,
  });
  const hasPublished = (summary.data?.published ?? 0) > 0;
  const analytics = useQuery({
    queryKey: ["home", userId, "analytics", range.from, range.to],
    queryFn: () => fetchUserAnalytics(range.from, range.to),
    enabled: !!userId && hasPublished,
    staleTime: 300_000,
    refetchInterval: 300_000,
    refetchIntervalInBackground: false,
  });
  // A stale zero summary must not hide recordings returned by the independent list query.
  const empty = summary.data?.total === 0 && !summary.isError && !recordings.data?.items.length;
  const views = dailyMetric(analytics.data?.daily ?? [], "share_views");
  const name = me.data?.full_name?.trim();

  if (!hydrated) {
    return <div className={pageClass}>
      <Skeleton className="mb-5 h-16 w-full" />
      <LoadingRows />
    </div>;
  }

  return (
    <div className={pageClass}>
      <div className="pb-5 sm:pb-7">
        {me.isPending ? <Skeleton className="mb-5 h-16 w-full" /> : (
          <PageHeader title="Home" description={<span className="[overflow-wrap:anywhere]">{name ? `Hello, ${name}!` : "Welcome to LEAP!"}</span>} />
        )}
      </div>
      {me.isError ? <ErrorState title="Could not load your account" error={me.error} onRetry={() => void me.refetch()} /> : (
        <div className="space-y-10">
          <section aria-labelledby="home-recordings-title" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="home-recordings-title" className="text-base font-semibold text-foreground">Your recordings</h2>
              <Link className={linkClass} href="/recordings">Open library <ArrowRight size={16} aria-hidden /></Link>
            </div>
            {summary.isError && <ErrorState title="Could not refresh current status" error={summary.error} onRetry={() => void summary.refetch()} className="py-4" />}
            {!empty && (summary.data ? (
              <nav aria-label="Current recording status">
                <AnalyticsSummaryCards items={OPERATIONAL_STATES.map((state) => ({
                  label: OPERATIONAL_STATE_LABEL[state],
                  value: formatCompactNumber(summary.data[state]),
                  valueTitle: String(summary.data[state]),
                  href: operationalStateHref(state),
                }))} />
              </nav>
            ) : !summary.isError && <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {OPERATIONAL_STATES.map((state) => <Skeleton key={state} className="h-24 rounded-xl" />)}
            </div>)}

            <div className={cn(CARD_SHELL, "min-w-0 p-4 sm:p-6")}>
              {empty ? (
                <EmptyState icon={Video} title="Your video workspace starts here"
                  description="Connect a source to bring your recordings into LEAP, or open your library to get started."
                  action={<Link className={linkClass} href="/sources">Connect a source <ArrowRight size={16} aria-hidden /></Link>} />
              ) : (
                <Tabs label="Recordings" value={tab ?? "recent"} onChange={setTab} items={[
                  { value: "recent", label: "Recently added" },
                  { value: "errors", label: "With errors", badge: summary.data?.error ? <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-danger-fg/10 px-1.5 text-xs tabular-nums text-danger-fg">{summary.data.error}</span> : undefined },
                ]}>
                  {recordings.isError && <ErrorState title="Could not refresh recordings" error={recordings.error} onRetry={() => void recordings.refetch()} className="py-4" />}
                  {recordings.data ? recordings.data.items.length ? <RecordingRows items={recordings.data.items} errors={tab === "errors"} /> : !recordings.isError && (
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      {tab === "errors" ? "No recording errors." : "No recordings yet."}
                    </p>
                  ) : !recordings.isError && <LoadingRows />}
                  {tab === "errors" && !!recordings.data?.total && (
                    <div className="mt-4 border-t border-border pt-4">
                      <Link className={linkClass} href={operationalStateHref("error")}>Review all errors <ArrowRight size={16} aria-hidden /></Link>
                    </div>
                  )}
                </Tabs>
              )}
            </div>
          </section>

          {hasPublished && <section aria-labelledby="home-activity-title" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2 id="home-activity-title" className="text-base font-semibold text-foreground">Activity</h2>
                <p className="text-xs text-muted-foreground" title={`${range.from} – ${range.to} · UTC`}>Last 7 days · UTC</p>
              </div>
              <Link className={linkClass} href="/settings?tab=usage">View analytics <ArrowRight size={16} aria-hidden /></Link>
            </div>
            <div className={cn(CARD_SHELL, "min-w-0 p-4 sm:p-6")}>
              {analytics.isError && <ErrorState title="Could not refresh activity" error={analytics.error} onRetry={() => void analytics.refetch()} className="py-4" />}
              {analytics.data && <dl className="grid grid-cols-3 gap-3 border-b border-border pb-6 sm:gap-6">
                {[
                  { label: "Video views", value: analytics.data.summary.share_views, unit: "" },
                  { label: "Recordings added", value: analytics.data.summary.recordings_created, unit: "" },
                  { label: "Transcribed", value: Number((analytics.data.summary.transcription_minutes / 60).toFixed(1)), unit: " h" },
                ].map((item) => <div key={item.label} className="flex min-w-0 flex-col gap-2">
                  <dt className="text-xs text-muted-foreground">{item.label}</dt>
                  <dd title={`${item.value}${item.unit}`} className="mt-auto whitespace-nowrap text-lg font-semibold tabular-nums text-foreground sm:text-2xl">
                    <span aria-hidden>{formatCompactNumber(item.value)}{item.unit}</span>
                    <span className="sr-only">{item.value}{item.unit}</span>
                  </dd>
                </div>)}
              </dl>}
              {analytics.isPending && <Skeleton className="h-20 w-full" />}
              {(!analytics.isError || analytics.data) && <div className="pt-6">
                <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <h3 className="text-sm font-medium text-foreground">Views per day</h3>
                  <p className="text-xs text-muted-foreground">Public LEAP recordings</p>
                </div>
                {analytics.isPending ? <Skeleton className="h-40 w-full" /> : views.every((point) => point.value === 0) ? (
                  <p className="flex h-40 items-center justify-center text-sm text-muted-foreground">No video views in this period</p>
                ) : <DailyBarChart data={views} valueLabel="Views" height={160} />}
              </div>}
            </div>
          </section>}
        </div>
      )}
    </div>
  );
}
