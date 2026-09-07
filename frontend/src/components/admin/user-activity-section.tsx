"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { dailyMetric, fetchAdminUserAnalytics, fetchAdminUserEvents } from "@/api/analytics";
import { ChartCard } from "@/components/charts/chart-card";
import { DailyBarChart } from "@/components/charts/daily-bar-chart";
import { DateRangeFilter } from "@/components/filters/date-range-filter";
import { ModalSection } from "@/components/ui/section-card";
import { defaultAnalyticsRange, type AnalyticsDateRange, type DateRangePreset, presetRange, validateRange } from "@/lib/analytics-date-range";
import { formatRelative } from "@/lib/utils";

const EVENT_LABELS: Record<string, string> = {
  transcription_completed: "Transcription completed",
  processing_started: "Processing started",
  processing_completed: "Processing completed",
  upload_completed: "Upload completed",
  recording_deleted: "Recording deleted",
};

export function UserActivitySection({ userId }: { userId: string }) {
  const [range, setRangeState] = useState<AnalyticsDateRange>(defaultAnalyticsRange());
  const [preset, setPreset] = useState<DateRangePreset>("28d");
  const validationError = validateRange(range.from, range.to);
  const isValid = validationError === null;

  const setRange = (next: AnalyticsDateRange, nextPreset: DateRangePreset = "custom") => {
    setRangeState(next);
    setPreset(nextPreset);
  };

  const analyticsQuery = useQuery({
    queryKey: ["admin-user-analytics", userId, range.from, range.to],
    queryFn: () => fetchAdminUserAnalytics(userId, range.from, range.to),
    enabled: isValid && Boolean(userId),
    staleTime: 60_000,
  });

  const eventsQuery = useQuery({
    queryKey: ["admin-user-events", userId, range.from, range.to],
    queryFn: () => fetchAdminUserEvents(userId, range.from, range.to, 20),
    enabled: isValid && Boolean(userId),
    staleTime: 60_000,
  });

  const data = analyticsQuery.data;

  return (
    <ModalSection title="Activity">
      <DateRangeFilter
        range={range}
        preset={preset}
        onRangeChange={(next) => setRange(next, "custom")}
        onPresetChange={(p) => setRange(presetRange(p), p)}
        validationError={validationError}
      />

      {isValid && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <ChartCard
              title="Recordings"
              isLoading={analyticsQuery.isPending}
              isError={analyticsQuery.isError}
              isEmpty={
                !analyticsQuery.isPending &&
                dailyMetric(data?.daily ?? [], "recordings_created").every((p) => p.value === 0)
              }
              className="p-3"
            >
              <DailyBarChart
                data={dailyMetric(data?.daily ?? [], "recordings_created")}
                valueLabel="Recordings"
                height={140}
              />
            </ChartCard>
            <ChartCard
              title="Transcribed (min)"
              isLoading={analyticsQuery.isPending}
              isError={analyticsQuery.isError}
              isEmpty={
                !analyticsQuery.isPending &&
                dailyMetric(data?.daily ?? [], "transcription_minutes").every((p) => p.value === 0)
              }
              className="p-3"
            >
              <DailyBarChart
                data={dailyMetric(data?.daily ?? [], "transcription_minutes")}
                valueLabel="Minutes"
                height={140}
              />
            </ChartCard>
            <ChartCard
              title="Share views"
              isLoading={analyticsQuery.isPending}
              isError={analyticsQuery.isError}
              isEmpty={
                !analyticsQuery.isPending &&
                dailyMetric(data?.daily ?? [], "share_views").every((p) => p.value === 0)
              }
              className="p-3"
            >
              <DailyBarChart
                data={dailyMetric(data?.daily ?? [], "share_views")}
                valueLabel="Views"
                height={140}
              />
            </ChartCard>
          </div>

          <div>
            <p className="mb-2 text-xs font-medium text-foreground">Recent events</p>
            {eventsQuery.isPending ? (
              <p className="text-xs text-muted-foreground">Loading events…</p>
            ) : eventsQuery.data && eventsQuery.data.length > 0 ? (
              <ul className="max-h-48 space-y-2 overflow-y-auto rounded-xl border border-border px-3 py-2">
                {eventsQuery.data.map((event) => (
                  <li key={event.id} className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
                    <span className="font-medium text-foreground">
                      {EVENT_LABELS[event.event_type] ?? event.event_type}
                      {event.recording_id != null && (
                        <span className="ml-1 font-normal text-muted-foreground">#{event.recording_id}</span>
                      )}
                    </span>
                    <span className="text-muted-foreground">
                      {formatRelative(event.created_at)}
                      {event.duration_seconds != null && (
                        <span className="ml-1 tabular-nums">
                          · {Math.round(event.duration_seconds / 60)} min
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xl border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
                No events in this period
              </p>
            )}
          </div>
        </div>
      )}
    </ModalSection>
  );
}
