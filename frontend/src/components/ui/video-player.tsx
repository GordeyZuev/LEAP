"use client";

import { forwardRef, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, RotateCcw } from "lucide-react";
import Plyr from "plyr";
import "plyr/dist/plyr.css";
import { VIDEO_PLAYER_FRAME } from "@/components/ui/video-player-frame";
import { PLAYER_SHORTCUTS, PLAYER_SPEEDS, handlePlayerKey } from "@/components/ui/video-player-keys";
import { applyHudAction, HUD_HIDE_MS, type HudView } from "@/lib/player-hud";
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
  /** Fired when user clicks a progress-bar chapter marker. */
  onMarkerSeek?: (time: number, label: string) => void;
  /** Refresh a signed media URL after an expiry or transport failure. */
  onReload?: () => void | Promise<unknown>;
  /** Layered on the Plyr container (fullscreen-safe): playlist end card, etc. */
  overlay?: ReactNode;
  className?: string;
}

function markerSignature(markers?: VideoPlayerMarker[]): string {
  if (!markers?.length) return "";
  return markers.map((m) => `${m.time}\t${m.label}`).join("\n");
}

function syncMarkers(
  player: Plyr,
  markers: VideoPlayerMarker[] | undefined,
  onMarkerSeek?: (time: number, label: string) => void,
) {
  const bar = player.elements.container?.querySelector(".plyr__progress");
  if (!bar) return;
  bar.querySelectorAll(".plyr__progress__marker").forEach((n: Element) => n.remove());
  const duration = player.duration;
  if (!duration || !markers?.length) return;
  markers.forEach((m) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "plyr__progress__marker";
    btn.setAttribute("aria-label", m.label);
    btn.title = m.label;
    btn.style.left = `${(m.time / duration) * 100}%`;
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      player.currentTime = m.time;
      onMarkerSeek?.(m.time, m.label);
    });
    bar.appendChild(btn);
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

function formatHud(view: HudView): { className: string; text: string } {
  if (view.kind === "seek") {
    return {
      className: view.dir < 0 ? "plyr__leap-hud--seek-back" : "plyr__leap-hud--seek-fwd",
      text: `${view.seconds}s`,
    };
  }
  if (view.kind === "speed") {
    return { className: "plyr__leap-hud--center", text: `${view.value}×` };
  }
  if (view.kind === "jump") {
    return { className: "plyr__leap-hud--center", text: `${view.percent}%` };
  }
  return {
    className: "plyr__leap-hud--center",
    text: view.muted ? "Muted" : `${view.percent}%`,
  };
}

function liveHud(view: HudView): string {
  if (view.kind === "seek") {
    return view.dir < 0 ? `Back ${view.seconds} seconds` : `Forward ${view.seconds} seconds`;
  }
  if (view.kind === "speed") return `Playback speed ${view.value}×`;
  if (view.kind === "jump") return `Jump to ${view.percent}%`;
  return view.muted ? "Muted" : `Volume ${view.percent}%`;
}

export const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
  function VideoPlayer(
    { src, resumeKey, vttBlobUrl, markers, onTimeUpdate, onEnded, onMarkerSeek, onReload, overlay, className },
    forwardedRef,
  ) {
    const [ready, setReady] = useState(false);
    const [failure, setFailure] = useState<string | null>(null);
    const [instanceId, setInstanceId] = useState(0);
    const [helpOpen, setHelpOpen] = useState(false);
    const [host, setHost] = useState<HTMLElement | null>(null);
    const [hud, setHud] = useState<HudView | null>(null);
    const playerScope = `${src}\0${resumeKey ?? ""}\0${instanceId}`;
    const [playerScopeSeen, setPlayerScopeSeen] = useState(playerScope);
    if (playerScopeSeen !== playerScope) {
      setPlayerScopeSeen(playerScope);
      setReady(false);
      setFailure(null);
      setHelpOpen(false);
      setHost(null);
      setHud(null);
    }
    const localRef = useRef<HTMLVideoElement>(null);
    const playerRef = useRef<Plyr | null>(null);
    const chapterLabelRef = useRef<HTMLSpanElement | null>(null);
    const lastLabelRef = useRef<string | null>(null);
    const markersRef = useRef(markers);
    const onTimeUpdateRef = useRef(onTimeUpdate);
    const onEndedRef = useRef(onEnded);
    const onMarkerSeekRef = useRef(onMarkerSeek);
    const onReloadRef = useRef(onReload);
    const helpOpenRef = useRef(false);
    const overlayRef = useRef(Boolean(overlay));
    const hudViewRef = useRef<HudView | null>(null);
    const hudAtRef = useRef(0);
    const hudHideRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const skipHudUntilRef = useRef(0);
    useEffect(() => { markersRef.current = markers; }, [markers]);
    useEffect(() => { onTimeUpdateRef.current = onTimeUpdate; }, [onTimeUpdate]);
    useEffect(() => { onEndedRef.current = onEnded; }, [onEnded]);
    useEffect(() => { onMarkerSeekRef.current = onMarkerSeek; }, [onMarkerSeek]);
    useEffect(() => { onReloadRef.current = onReload; }, [onReload]);
    useEffect(() => { helpOpenRef.current = helpOpen; }, [helpOpen]);
    useEffect(() => { overlayRef.current = Boolean(overlay); }, [overlay]);

    const pushHud = useCallback((view: HudView) => {
      if (overlayRef.current) return;
      hudViewRef.current = view;
      hudAtRef.current = Date.now();
      setHud(view);
      if (hudHideRef.current) clearTimeout(hudHideRef.current);
      hudHideRef.current = setTimeout(() => {
        hudViewRef.current = null;
        setHud(null);
      }, HUD_HIDE_MS);
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

      let cancelled = false;
      let refreshAttempted = false;
      let startupTimer: ReturnType<typeof setTimeout> | null = null;
      skipHudUntilRef.current = Date.now() + 500;

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
      if (player.elements.container) setHost(player.elements.container);

      const helpBtn = document.createElement("button");
      helpBtn.type = "button";
      helpBtn.className = "plyr__control";
      helpBtn.setAttribute("aria-label", "Keyboard shortcuts");
      helpBtn.setAttribute("data-plyr", "help");
      helpBtn.innerHTML = "<span aria-hidden=\"true\">?</span>";
      helpBtn.addEventListener("click", (event) => {
        event.preventDefault();
        setHelpOpen((open) => !open);
      });
      player.elements.controls?.appendChild(helpBtn);

      const markReady = () => {
        if (cancelled) return;
        clearTimers();
        setFailure(null);
        setReady(true);
        if (player.elements.container) setHost(player.elements.container);
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
      player.on("ratechange", () => {
        if (cancelled || Date.now() < skipHudUntilRef.current) return;
        pushHud({ kind: "speed", value: player.speed });
      });
      player.on("volumechange", () => {
        if (cancelled || Date.now() < skipHudUntilRef.current) return;
        pushHud({
          kind: "volume",
          percent: Math.round(player.volume * 100),
          muted: player.muted,
        });
      });
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
        const action = handlePlayerKey(event, player, {
          isOpen: () => helpOpenRef.current,
          toggle: () => setHelpOpen((open) => !open),
          close: () => setHelpOpen(false),
        });
        if (action) {
          pushHud(applyHudAction(hudViewRef.current, hudAtRef.current, Date.now(), action));
        }
      };
      window.addEventListener("keydown", onKeyDown);

      return () => {
        cancelled = true;
        clearTimers();
        persistNow();
        saver?.cancel();
        if (hudHideRef.current) clearTimeout(hudHideRef.current);
        window.removeEventListener("pagehide", persistNow);
        window.removeEventListener("keydown", onKeyDown);
        el.removeEventListener("loadedmetadata", applyResume);
        el.removeEventListener("loadedmetadata", markReady);
        el.removeEventListener("loadeddata", markReady);
        el.removeEventListener("canplay", markReady);
        el.removeEventListener("error", onMediaError);
        helpBtn.remove();
        playerRef.current = null;
        chapterLabelRef.current = null;
        lastLabelRef.current = null;
        player.destroy();
      };
    }, [src, resumeKey, instanceId, pushHud]);

    const markersKey = markerSignature(markers);
    useEffect(() => {
      const player = playerRef.current;
      if (!player || !ready) return;
      const apply = () => {
        syncMarkers(player, markersRef.current, (time, label) => onMarkerSeekRef.current?.(time, label));
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

    const hudBits = hud ? formatHud(hud) : null;

    return (
      <div className={cn(VIDEO_PLAYER_FRAME, "motion-safe:animate-page-in", className)}>
        <video
          ref={setRef}
          src={src}
          preload="metadata"
          playsInline
          className="block h-full w-full"
        />
        {host && createPortal(
          <>
            {hudBits && !overlay && (
              <div className={cn("plyr__leap-hud motion-safe:plyr__leap-hud-in", hudBits.className)} aria-hidden>
                {hudBits.text}
              </div>
            )}
            <div className="sr-only" role="status" aria-live="polite">
              {hud && !overlay ? liveHud(hud) : ""}
            </div>
            {overlay && <div className="plyr__leap-overlay">{overlay}</div>}
            {helpOpen && (
              <div
                className="video-player-help"
                role="dialog"
                aria-modal="true"
                aria-label="Keyboard shortcuts"
                onClick={() => setHelpOpen(false)}
              >
                <dl onClick={(event) => event.stopPropagation()}>
                  {PLAYER_SHORTCUTS.map((row) => (
                    <div key={row.keys}>
                      <dt>{row.keys}</dt>
                      <dd>{row.label}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </>,
          host,
        )}
        {Boolean(src) && !ready && (
          <div className="absolute inset-0 z-10 overflow-hidden rounded-[inherit]">
            {failure ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 bg-muted/90">
                <AlertCircle size={24} className="text-danger-fg" />
                <p className="text-sm text-muted-foreground">{failure}</p>
                <button
                  type="button"
                  onClick={() => {
                    setFailure(null);
                    void onReloadRef.current?.();
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
  },
);
