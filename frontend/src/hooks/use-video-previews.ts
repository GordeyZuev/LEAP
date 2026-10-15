"use client";

import { useEffect, useState } from "react";
import { resolveStorageUrl } from "@/api/client";

export interface PreviewFrame {
  start: number;
  image: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

function parseFrames(vtt: string, url: string): PreviewFrame[] {
  const frames: PreviewFrame[] = [];
  const pattern = /(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->[^\n]*\n([^\n#]+)#xywh=(\d+),(\d+),(\d+),(\d+)/g;
  for (const match of vtt.matchAll(pattern)) {
    const [, hours, minutes, seconds, millis, image, x, y, width, height] = match;
    frames.push({
      start: Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds) + Number(millis) / 1000,
      image: new URL(image, url).href,
      x: Number(x), y: Number(y), width: Number(width), height: Number(height),
    });
  }
  return frames;
}

/** One public VTT powers both Plyr's hover previews and chapter images. */
export function useVideoPreviews(basePath: string | null) {
  const [previews, setPreviews] = useState<{ basePath: string; url: string; frames: PreviewFrame[] } | null>(null);
  useEffect(() => {
    if (!basePath) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;
    let attempts = 0;
    const startedAt = Date.now();
    const url = resolveStorageUrl(`/api/v1${basePath}/preview.vtt`);
    const fetchPreview = async () => {
      if (document.visibilityState === "hidden" || inFlight || cancelled) return;
      inFlight = true;
      try {
        // Completed VTTs are cacheable for one minute; 202 responses are no-store.
        // Plyr fetches the same URL, so let it reuse the ready response.
        const response = await fetch(url, { credentials: "include" });
        if (cancelled) return;
        if (response.status === 202) {
          attempts += 1;
          if (Date.now() - startedAt < 65 * 60 * 1000) {
            timer = setTimeout(fetchPreview, Math.min(60_000, 5000 + attempts * 2000));
          }
          return;
        }
        if (!response.ok) return;
        const frames = parseFrames(await response.text(), url);
        if (!cancelled && frames.length) setPreviews({ basePath, url, frames });
      } catch {
        // A failed storyboard never interrupts video playback.
      } finally {
        inFlight = false;
      }
    };
    const onVisible = () => {
      if (document.visibilityState !== "visible" || cancelled) return;
      if (timer) clearTimeout(timer);
      timer = null;
      void fetchPreview();
    };
    document.addEventListener("visibilitychange", onVisible);
    void fetchPreview();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [basePath]);
  return previews?.basePath === basePath ? previews : null;
}

export function frameAt(frames: PreviewFrame[] | undefined, time: number): PreviewFrame | null {
  if (!frames?.length) return null;
  const next = frames.findIndex((frame) => frame.start > time);
  const index = next < 0 ? frames.length - 1 : Math.max(0, next - 1);
  return frames[index] ?? frames[frames.length - 1] ?? null;
}
