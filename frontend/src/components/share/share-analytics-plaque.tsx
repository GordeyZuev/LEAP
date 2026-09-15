"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";

import { fetchChannelShareAnalytics } from "@/api/channels";
import { fetchPlaylistShareAnalytics } from "@/api/playlists";
import { ActionButton } from "@/components/ui/action-button";
import { CARD_SHELL } from "@/components/ui/section-card";
import { Skeleton } from "@/components/ui/skeleton";
import { defaultAnalyticsRange } from "@/lib/analytics-date-range";
import { cn } from "@/lib/utils";

export function ShareAnalyticsPlaque({
  subject,
  onOpenDetails,
}: {
  subject: { kind: "channel" | "playlist"; id: number };
  onOpenDetails: () => void;
}) {
  const range = defaultAnalyticsRange();
  const { data, isPending } = useQuery({
    queryKey: ["share-analytics", subject.kind, subject.id, "plaque"],
    queryFn: () =>
      subject.kind === "playlist"
        ? fetchPlaylistShareAnalytics(subject.id, range)
        : fetchChannelShareAnalytics(subject.id, range),
  });

  const opens = data?.summary.open_count ?? 0;
  const views = data?.summary.view_count ?? 0;
  const downloads = data?.summary.download_count ?? 0;

  return (
    <section aria-labelledby="share-analytics-plaque" className={cn(CARD_SHELL, "mt-4 overflow-hidden p-4")}>
      <h2 id="share-analytics-plaque" className="text-sm font-semibold text-foreground">
        Analytics
      </h2>
      <p className="mt-0.5 text-xs text-muted-foreground">All time</p>
      {isPending ? (
        <Skeleton className="mt-3 h-12 rounded-lg" />
      ) : (
        <dl className="mt-3 grid grid-cols-3 gap-2">
          <div>
            <dt className="text-xs text-muted-foreground">Opens</dt>
            <dd className="mt-0.5 text-lg font-semibold tabular-nums text-foreground">{opens}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Views</dt>
            <dd className="mt-0.5 text-lg font-semibold tabular-nums text-foreground">{views}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Downloads</dt>
            <dd className="mt-0.5 text-lg font-semibold tabular-nums text-foreground">{downloads}</dd>
          </div>
        </dl>
      )}
      {!isPending && data?.engagement?.completion_rate != null && (
        <p className="mt-3 text-xs text-muted-foreground">
          Completion (28d) · {Math.round((data.engagement.completion_rate ?? 0) * 1000) / 10}%
        </p>
      )}
      <ActionButton
        className="mt-4 w-full justify-center"
        icon={<BarChart3 />}
        onClick={onOpenDetails}
      >
        View analytics
      </ActionButton>
    </section>
  );
}
