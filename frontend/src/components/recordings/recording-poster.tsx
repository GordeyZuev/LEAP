"use client";

import { useState } from "react";
import { Film } from "lucide-react";
import { cn, formatDurationCompact } from "@/lib/utils";
import { apiClient, resolveStorageUrl } from "@/api/client";

/**
 * Recordings whose poster we have already asked the backend to generate.
 *
 * The list hands out a URL built by convention, so a missing poster shows up as
 * a failed image load rather than a flag on the row. One request per id per page
 * session is enough: by the next visit the object exists. Module-level so it
 * survives remounts while paging, mirroring the blob cache in thumbnail-picker.
 */
const requested = new Set<number>();

interface RecordingPosterProps {
  recordingId: number;
  /** Presigned URL from the list response; null when there is nothing to show. */
  posterUrl?: string | null;
  /** Frame poster URL when posterUrl is a configured thumbnail. */
  posterFallbackUrl?: string | null;
  /** Seconds — rendered as a badge over the frame. */
  duration?: number;
  className?: string;
}

/** Grid card: fixed height strip (not 16:9 — too tall at column width). */
export const RECORDING_CARD_POSTER = "h-24 w-full";

/** Table row thumb: small 16:9 frame. */
export const RECORDING_TABLE_POSTER = "aspect-video w-16";

export function RecordingPoster({
  recordingId,
  posterUrl,
  posterFallbackUrl,
  duration,
  className,
}: RecordingPosterProps) {
  const [fallbackActive, setFallbackActive] = useState(false);
  const [failed, setFailed] = useState(false);
  const [prevPosterUrl, setPrevPosterUrl] = useState(posterUrl);
  const [prevPosterFallbackUrl, setPrevPosterFallbackUrl] = useState(posterFallbackUrl);

  if (posterUrl !== prevPosterUrl || posterFallbackUrl !== prevPosterFallbackUrl) {
    setPrevPosterUrl(posterUrl);
    setPrevPosterFallbackUrl(posterFallbackUrl);
    setFallbackActive(false);
    setFailed(false);
  }

  const activeUrl = fallbackActive ? posterFallbackUrl : posterUrl;
  const showImage = !!activeUrl && !failed;
  const dur = formatDurationCompact(duration);

  function handleError() {
    if (posterFallbackUrl && !fallbackActive) {
      setFallbackActive(true);
      return;
    }
    setFailed(true);
    if (requested.has(recordingId)) return;
    requested.add(recordingId);
    // Best-effort: a poster is decorative, so a failure here must stay silent.
    void apiClient.post(`/recordings/${recordingId}/poster`).catch(() => {});
  }

  return (
    <div
      className={cn(
        "relative shrink-0 overflow-hidden rounded-lg bg-muted",
        "outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10",
        className
      )}
    >
      {showImage ? (
        // The title next to it is already a link to the same place, so the
        // frame adds nothing for a screen reader.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={resolveStorageUrl(activeUrl)}
          alt=""
          loading="lazy"
          decoding="async"
          onError={handleError}
          className="h-full w-full object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <Film size={16} className="text-muted-foreground/50" aria-hidden="true" />
        </div>
      )}

      {dur && (
        <span className="absolute bottom-1 end-1 rounded bg-black/70 px-1 py-0.5 text-xs font-medium tabular-nums text-white">
          {dur}
        </span>
      )}
    </div>
  );
}
