"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";

import { createEngagementTracker, type EngagementEventName, type EngagementEventPayload } from "@/lib/share-engagement";

export function useShareEngagement(ingestPath: string | null) {
  const tracker = useMemo(
    () => (ingestPath ? createEngagementTracker(ingestPath) : null),
    [ingestPath],
  );
  const trackerRef = useRef(tracker);
  useEffect(() => {
    // After previous cleanups, so watch_exit still flushes to the last ingest path.
    trackerRef.current = tracker;
  }, [tracker]);

  const track = useCallback((name: EngagementEventName, payload: EngagementEventPayload = {}) => {
    trackerRef.current?.track(name, payload);
  }, []);

  const flush = useCallback(() => {
    trackerRef.current?.flush();
  }, []);

  useEffect(() => {
    if (!tracker) return;
    const activeTracker = tracker;
    const onPageHide = () => activeTracker.flush();
    window.addEventListener("pagehide", onPageHide);
    const timer = window.setInterval(() => {
      activeTracker.flush();
    }, 5000);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      window.clearInterval(timer);
      activeTracker.flush();
    };
  }, [ingestPath, tracker]);

  return { track, flush };
}
