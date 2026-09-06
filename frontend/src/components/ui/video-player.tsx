"use client";

import { forwardRef, useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, RotateCcw } from "lucide-react";
import Plyr from "plyr";
import "plyr/dist/plyr.css";
import { VIDEO_PLAYER_FRAME } from "@/components/ui/video-player-frame";
import { PLAYER_SHORTCUTS, PLAYER_SPEEDS, handlePlayerKey } from "@/components/ui/video-player-keys";
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

function markerSignature(markers?: VideoPlayerMarker[]): string {
  if (!markers?.length) return "";
  return markers.map((m) => `${m.time}\t${m.label}`).join("\n");
}

function syncMarkers(player: Plyr, markers: VideoPlayerMarker[] | undefined) {
  const bar = player.elements.container?.querySelector(".plyr__progress");
  if (!bar) return;
  bar.querySelectorAll(".plyr__progress__marker").forEach((n: Element) => n.remove());
  const duration = player.duration;
  if (!duration || !markers?.length) return;
  markers.forEach((m) => {
    const dot = document.createElement("span");
    dot.className = "plyr__progress__marker";
    dot.title = m.label;
    dot.setAttribute("aria-hidden", "true");
    dot.style.left = `${(m.time / duration) * 100}%`;
    bar.appendChild(dot);
  });
}

function ensureChapterLabel(player: Plyr): HTMLSpanElement | null {
  const existing = player.elements.controls?.querySelector(".plyr__chapter-label");
  if (existing instanceof HTMLSpanElement) return existing;
  const timeEl =
    player.elements.controls?.querySelector(".plyr__time--duration")
    ?? player.elements.controls?.querySelector(".plyr__time--current");
  if (!timeEl) return null;
  const el = document.createElement("span");
  el.className = "plyr__chapter-label plyr__chapter-label--hidden";
  timeEl.insertAdjacentElement("afterend", el);
  return el;
}

export const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
  function VideoPlayer({ src, resumeKey, vttBlobUrl, markers, onTimeUpdate, onEnded, onReload }, forwardedRef) {
    const [ready, setReady] = useState(false);
    const [failure, setFailure] = useState<string | null>(null);
    const [instanceId, setInstanceId] = useState(0);
    const [helpOpen, setHelpOpen] = useState(false);
    const localRef = useRef<HTMLVideoElement>(null);
    const playerRef = useRef<Plyr | null>(null);
    const chapterLabelRef = useRef<HTMLSpanElement | null>(null);
    const lastLabelRef = useRef<string | null>(null);
    const markersRef = useRef(markers);
    markersRef.current = markers;
    const onTimeUpdateRef = useRef(onTimeUpdate);
    const onEndedRef = useRef(onEnded);
    const onReloadRef = useRef(onReload);
    const helpOpenRef = useRef(false);
    helpOpenRef.current = helpOpen;
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
      setHelpOpen(false);
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
        speed: { selected: 1, options: [...PLAYER_SPEEDS] },
        tooltips: { controls: true, seek: true },
        keyboard: { focused: false, global: false },
        captions: { active: false, language: "auto", update: true },
        settings: ["captions", "speed"],
        // No volume slider — phones use hardware volume; mute is enough.
        controls: [
          "play-large",
          "play",
          "progress",
          "current-time",
          "duration",
          "mute",
          "settings",
          "pip",
          "fullscreen",
        ],
        markers: { enabled: false, points: [] as { time: number; label: string }[] },
      });
      playerRef.current = player;

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
        const list = markersRef.current;
        const labelEl = chapterLabelRef.current;
        if (!labelEl || !list?.length) return;
        const active = list.findLast((m) => m.time <= ct);
        const label = active?.label ?? null;
        if (label !== lastLabelRef.current) {
          labelEl.textContent = label ?? "";
          labelEl.classList.toggle("plyr__chapter-label--hidden", !label);
          lastLabelRef.current = label;
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

      const onKeyDown = (event: KeyboardEvent) => {
        handlePlayerKey(event, player, {
          isOpen: () => helpOpenRef.current,
          toggle: () => setHelpOpen((open) => !open),
          close: () => setHelpOpen(false),
        });
      };
      window.addEventListener("keydown", onKeyDown);

      return () => {
        cancelled = true;
        clearTimers();
        persistNow();
        saver?.cancel();
        window.removeEventListener("pagehide", persistNow);
        window.removeEventListener("keydown", onKeyDown);
        el.removeEventListener("loadedmetadata", applyResume);
        el.removeEventListener("loadedmetadata", markReady);
        el.removeEventListener("loadeddata", markReady);
        el.removeEventListener("canplay", markReady);
        el.removeEventListener("error", onMediaError);
        playerRef.current = null;
        chapterLabelRef.current = null;
        lastLabelRef.current = null;
        player.destroy();
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [src, resumeKey, instanceId]);

    const markersKey = markerSignature(markers);
    useEffect(() => {
      const player = playerRef.current;
      if (!player || !ready) return;
      const apply = () => {
        syncMarkers(player, markersRef.current);
        const list = markersRef.current;
        if (list?.length) {
          chapterLabelRef.current = ensureChapterLabel(player);
        } else {
          chapterLabelRef.current?.remove();
          chapterLabelRef.current = null;
          lastLabelRef.current = null;
        }
      };
      apply();
      const el = localRef.current;
      el?.addEventListener("loadedmetadata", apply);
      return () => el?.removeEventListener("loadedmetadata", apply);
    }, [markersKey, ready]);

    useEffect(() => {
      const el = localRef.current;
      if (!el) return;
      el.querySelectorAll('track[data-leap="1"]').forEach((n) => n.remove());
      if (!vttBlobUrl) return;
      const track = document.createElement("track");
      track.kind = "subtitles";
      track.label = "Subtitles";
      track.srclang = "und";
      track.src = vttBlobUrl;
      track.dataset.leap = "1";
      el.appendChild(track);
    }, [vttBlobUrl, src, instanceId]);

    return (
      <div className={cn(VIDEO_PLAYER_FRAME, "video-fill-landscape")}>
        <video
          ref={setRef}
          src={src}
          preload="metadata"
          playsInline
          className="block h-full w-full"
        />
        {helpOpen && (
          <div className="video-player-help" role="region" aria-label="Keyboard shortcuts">
            <dl>
              {PLAYER_SHORTCUTS.map((row) => (
                <div key={row.keys}>
                  <dt>{row.keys}</dt>
                  <dd>{row.label}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
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
