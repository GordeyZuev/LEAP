"use client";

import { forwardRef, useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, RotateCcw } from "lucide-react";
import Plyr from "plyr";
import "plyr/dist/plyr.css";
import { VIDEO_PLAYER_FRAME } from "@/components/ui/video-player-frame";
import { cn } from "@/lib/utils";
import { createResumeSaver, readResumeTime, resumeTimeWithinDuration } from "@/lib/video-resume";

export interface VideoPlayerMarker {
  time: number;
  label: string;
}

interface VideoPlayerProps {
  src: string;
  /** localStorage key; position is restored after metadata loads. */
  resumeKey?: string;
  vttBlobUrl?: string | null;
  markers?: VideoPlayerMarker[];
  onTimeUpdate?: (currentTime: number) => void;
  /** Fired once when playback reaches the end. */
  onEnded?: () => void;
  /** Refresh a signed media URL after an expiry or transport failure. */
  onReload?: () => void | Promise<unknown>;
}

export const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
  function VideoPlayer({ src, resumeKey, vttBlobUrl, markers, onTimeUpdate, onEnded, onReload }, forwardedRef) {
    const [ready, setReady] = useState(false);
    const [failure, setFailure] = useState<string | null>(null);
    const [instanceId, setInstanceId] = useState(0);
    const localRef = useRef<HTMLVideoElement>(null);
    const onTimeUpdateRef = useRef(onTimeUpdate);
    const onEndedRef = useRef(onEnded);
    const onReloadRef = useRef(onReload);
    useEffect(() => { onTimeUpdateRef.current = onTimeUpdate; }, [onTimeUpdate]);
    useEffect(() => { onEndedRef.current = onEnded; }, [onEnded]);
    useEffect(() => { onReloadRef.current = onReload; }, [onReload]);

    useEffect(() => {
      const mq = window.matchMedia("(orientation: landscape) and (hover: none) and (max-height: 540px)");
      const sync = () => document.body.classList.toggle("video-landscape-lock", mq.matches);
      sync();
      mq.addEventListener("change", sync);
      return () => {
        mq.removeEventListener("change", sync);
        document.body.classList.remove("video-landscape-lock");
      };
    }, []);

    const setRef = useCallback((el: HTMLVideoElement | null) => {
      (localRef as React.RefObject<HTMLVideoElement | null>).current = el;
      if (typeof forwardedRef === "function") forwardedRef(el);
      else if (forwardedRef) (forwardedRef as React.RefObject<HTMLVideoElement | null>).current = el;
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
      const el = localRef.current;
      if (!el) return;

      setReady(false);
      setFailure(null);
      let cancelled = false;
      let refreshAttempted = false;
      let startupTimer: ReturnType<typeof setTimeout> | null = null;

      const clearTimers = () => {
        if (startupTimer) clearTimeout(startupTimer);
        startupTimer = null;
      };

      const player = new Plyr(el, {
        seekTime: 5,
        invertTime: false,
        hideControls: true,
        speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
        tooltips: { controls: true, seek: true },
        keyboard: { focused: true, global: true },
        captions: { active: false, language: "auto", update: true },
        // No volume slider — phones use hardware volume; mute is enough.
        controls: [
          "play-large",
          "play",
          "progress",
          "current-time",
          "mute",
          "captions",
          "settings",
          "pip",
          "fullscreen",
        ],
        markers: { enabled: false, points: [] as { time: number; label: string }[] },
      });

      if (markers?.length) {
        const injectMarkers = () => {
          const duration = player.duration;
          if (!duration) return;
          const bar = player.elements.container?.querySelector(".plyr__progress");
          if (!bar) return;
          bar.querySelectorAll(".plyr__progress__marker").forEach((n: Element) => n.remove());
          markers.forEach((m) => {
            const dot = document.createElement("span");
            dot.className = "plyr__progress__marker";
            dot.title = m.label;
            dot.setAttribute("aria-hidden", "true");
            dot.style.left = `${(m.time / duration) * 100}%`;
            bar.appendChild(dot);
          });
        };
        if (el.readyState >= 1) injectMarkers();
        else el.addEventListener("loadedmetadata", injectMarkers, { once: true });
      }

      let chapterLabelEl: HTMLSpanElement | null = null;
      let lastLabel: string | null = null;
      if (markers?.length) {
        const injectChapterLabel = () => {
          const timeEl = player.elements.controls?.querySelector(".plyr__time--duration")
            ?? player.elements.controls?.querySelector(".plyr__time--current");
          if (!timeEl) return;
          chapterLabelEl = document.createElement("span");
          chapterLabelEl.className = "plyr__chapter-label plyr__chapter-label--hidden";
          timeEl.insertAdjacentElement("afterend", chapterLabelEl);
        };
        if (el.readyState >= 1) injectChapterLabel();
        else el.addEventListener("loadedmetadata", injectChapterLabel, { once: true });
      }

      const markReady = () => {
        if (cancelled) return;
        clearTimers();
        setFailure(null);
        setReady(true);
      };
      const markFailed = (message = "Video could not be loaded") => {
        if (cancelled) return;
        clearTimers();
        setReady(false);
        setFailure(message);
        if (!refreshAttempted) {
          refreshAttempted = true;
          void onReloadRef.current?.();
        }
      };

      const saver = resumeKey ? createResumeSaver(resumeKey) : null;
      const applyResume = () => {
        if (!resumeKey || cancelled) return;
        const saved = readResumeTime(resumeKey);
        if (saved == null) return;
        const duration = player.duration || el.duration;
        const t = resumeTimeWithinDuration(saved, duration);
        if (t == null) return;
        player.currentTime = t;
        el.currentTime = t;
      };
      if (el.readyState >= 1) applyResume();
      else el.addEventListener("loadedmetadata", applyResume, { once: true });

      player.on("timeupdate", () => {
        const ct = player.currentTime;
        onTimeUpdateRef.current?.(ct);
        saver?.save(ct);
        if (chapterLabelEl && markers?.length) {
          const active = markers.findLast((m) => m.time <= ct);
          const label = active?.label ?? null;
          if (label !== lastLabel) {
            chapterLabelEl.textContent = label ?? "";
            chapterLabelEl.classList.toggle("plyr__chapter-label--hidden", !label);
            lastLabel = label;
          }
        }
      });
      player.on("ready", applyResume);
      player.on("canplay", markReady);
      player.on("playing", markReady);
      player.on("loadeddata", markReady);
      player.on("loadedmetadata", markReady);
      const onMediaError = () => markFailed();
      player.on("error", onMediaError);
      el.addEventListener("loadedmetadata", markReady);
      el.addEventListener("loadeddata", markReady);
      el.addEventListener("canplay", markReady);
      el.addEventListener("error", onMediaError);
      if (el.readyState >= 1) markReady();
      else startupTimer = setTimeout(() => markFailed("Video is taking too long to load"), 20_000);

      const persistNow = () => saver?.flush(player.currentTime || el.currentTime || 0);
      player.on("pause", persistNow);
      player.on("ended", () => onEndedRef.current?.());
      window.addEventListener("pagehide", persistNow);

      return () => {
        cancelled = true;
        clearTimers();
        persistNow();
        saver?.cancel();
        window.removeEventListener("pagehide", persistNow);
        el.removeEventListener("loadedmetadata", applyResume);
        el.removeEventListener("loadedmetadata", markReady);
        el.removeEventListener("loadeddata", markReady);
        el.removeEventListener("canplay", markReady);
        el.removeEventListener("error", onMediaError);
        player.destroy();
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [src, resumeKey, instanceId]);

    return (
      <div className={cn(VIDEO_PLAYER_FRAME, "video-fill-landscape")}>
        <video
          ref={setRef}
          src={src}
          preload="metadata"
          playsInline
          className="block h-full w-full"
        >
          {vttBlobUrl && <track kind="subtitles" src={vttBlobUrl} label="Subtitles" default />}
        </video>
        {Boolean(src) && !ready && (
          <div className="absolute inset-0 z-10 overflow-hidden rounded-xl">
            {failure ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 bg-muted/90">
                <AlertCircle size={24} className="text-danger-fg" />
                <p className="text-sm text-muted-foreground">{failure}</p>
                <button
                  type="button"
                  onClick={() => {
                    setFailure(null);
                    setInstanceId((n) => n + 1);
                  }}
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
                >
                  <RotateCcw size={14} /> Retry
                </button>
              </div>
            ) : (
              <div className="h-full w-full animate-pulse bg-muted" role="status" aria-label="Loading video" />
            )}
          </div>
        )}
      </div>
    );
  }
);
