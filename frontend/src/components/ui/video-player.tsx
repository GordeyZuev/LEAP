"use client";

import { forwardRef, memo, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, RotateCcw } from "lucide-react";
import Plyr from "plyr";
import "plyr/dist/plyr.css";
import { VIDEO_PLAYER_FRAME } from "@/components/ui/video-player-frame";
import { PLAYER_SHORTCUTS, PLAYER_SPEEDS, bindPlaybackFocus, handlePlayerKey } from "@/components/ui/video-player-keys";
import { applyHudAction, HUD_HIDE_MS, type HudView } from "@/lib/player-hud";
import { cn } from "@/lib/utils";
import { createResumeSaver, readResumeTime, resumeTimeWithinDuration, retryTimeWithinDuration } from "@/lib/video-resume";

const MAX_AUTO_RECOVERIES = 2;

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
  onReload?: () => string | null | Promise<string | null>;
  /** Play after this media element mounts (used when navigating to a playlist item). */
  autoPlayRequested?: boolean;
  onAutoPlayAttempt?: () => void;
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
  markers.filter((m) => Number.isFinite(m.time) && m.time >= 0 && m.time <= duration).forEach((m) => {
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

function setAutoPiPAction(handler: (() => void) | null): void {
  if (!("mediaSession" in navigator)) return;
  try {
    // The action ships in Chromium before TypeScript's MediaSessionAction union.
    const session = navigator.mediaSession;
    const setAction = session.setActionHandler as (action: string, callback: (() => void) | null) => void;
    setAction.call(session, "enterpictureinpicture", handler);
  } catch {
    // This Media Session action is not available in every browser.
  }
}

/**
 * Plyr rewrites DOM around the media node. Keep that tree inside a memoized
 * empty mount: React must not own <video>, or ready/HUD setState pulls it
 * out of `.plyr` and the controls never return.
 * Video + Plyr share one effect so Retry/src remount cannot race two cleanups.
 */
const PlyrMount = memo(function PlyrMount({
  src,
  setRef,
  attach,
}: {
  src: string;
  setRef: (el: HTMLVideoElement | null) => void;
  attach: (el: HTMLVideoElement) => () => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const el = document.createElement("video");
    el.src = src;
    el.preload = "metadata";
    el.playsInline = true;
    el.className = "block h-full w-full";
    root.appendChild(el);
    setRef(el);
    const detach = attach(el);
    return () => {
      detach();
      setRef(null);
      root.replaceChildren();
    };
  }, [src, setRef, attach]);
  return <div ref={rootRef} className="h-full w-full" />;
});

export const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
  function VideoPlayer(
    { src, resumeKey, vttBlobUrl, markers, onTimeUpdate, onEnded, onMarkerSeek, onReload,
      autoPlayRequested, onAutoPlayAttempt, overlay, className },
    forwardedRef,
  ) {
    const [ready, setReady] = useState(false);
    const [failure, setFailure] = useState<string | null>(null);
    const [instanceId, setInstanceId] = useState(0);
    const [retryingScope, setRetryingScope] = useState<string | null>(null);
    const [helpOpen, setHelpOpen] = useState(false);
    const [host, setHost] = useState<HTMLElement | null>(null);
    const [hud, setHud] = useState<HudView | null>(null);
    // A new presigned URL for the same video must not replace a playing media node.
    // Keep it ready for recovery if the current URL later fails a Range request.
    const mediaIdentity = resumeKey ?? src;
    const [source, setSource] = useState({ identity: mediaIdentity, url: src });
    if (source.identity !== mediaIdentity) {
      setSource({ identity: mediaIdentity, url: src });
    }
    const activeSrc = source.identity === mediaIdentity ? source.url : src;
    const playerScope = `${activeSrc}\0${mediaIdentity}\0${instanceId}`;
    const retrying = retryingScope === playerScope;
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
    const onAutoPlayAttemptRef = useRef(onAutoPlayAttempt);
    const helpOpenRef = useRef(false);
    const overlayRef = useRef(Boolean(overlay));
    const hudViewRef = useRef<HudView | null>(null);
    const hudAtRef = useRef(0);
    const hudHideRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const skipHudUntilRef = useRef(0);
    const wasPlayingRef = useRef(false);
    const resumePlaybackRef = useRef(false);
    const retryPositionRef = useRef<{ identity: string; time: number } | null>(null);
    const autoRecoveriesRef = useRef({ identity: mediaIdentity, count: 0 });
    useEffect(() => {
      if (failure && src !== activeSrc) {
        setSource({ identity: mediaIdentity, url: src });
      }
    }, [failure, src, activeSrc, mediaIdentity]);
    useEffect(() => { markersRef.current = markers; }, [markers]);
    useEffect(() => { onTimeUpdateRef.current = onTimeUpdate; }, [onTimeUpdate]);
    useEffect(() => { onEndedRef.current = onEnded; }, [onEnded]);
    useEffect(() => { onMarkerSeekRef.current = onMarkerSeek; }, [onMarkerSeek]);
    useEffect(() => { onReloadRef.current = onReload; }, [onReload]);
    useEffect(() => { onAutoPlayAttemptRef.current = onAutoPlayAttempt; }, [onAutoPlayAttempt]);
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

    const attach = useCallback((el: HTMLVideoElement) => {
      let cancelled = false;
      let refreshAttempted = false;
      let startupTimer: ReturnType<typeof setTimeout> | null = null;
      let stallTimer: ReturnType<typeof setTimeout> | null = null;
      let recoveryResetTimer: ReturnType<typeof setTimeout> | null = null;
      const startedAt = performance.now();
      let firstFrameRecorded = false;
      let bufferingStartedAt: number | null = null;
      let lastProgressTime = Number.isFinite(el.currentTime) ? el.currentTime : 0;
      skipHudUntilRef.current = Date.now() + 500;

      const clearStartupTimer = () => {
        if (startupTimer) clearTimeout(startupTimer);
        startupTimer = null;
      };
      const clearStallTimer = () => {
        if (stallTimer) clearTimeout(stallTimer);
        stallTimer = null;
      };
      const clearTimers = () => {
        clearStartupTimer();
        clearStallTimer();
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
        clearStartupTimer();
        refreshAttempted = false;
        setFailure(null);
        setReady(true);
        if (player.elements.container) setHost(player.elements.container);
      };
      const recordFirstFrame = () => {
        if (firstFrameRecorded) return;
        firstFrameRecorded = true;
        performance.measure("leap:video:first-frame", { start: startedAt, end: performance.now() });
      };
      const markFailed = (message = "Video could not be loaded") => {
        if (cancelled || refreshAttempted) return;
        refreshAttempted = true;
        clearTimers();
        if (recoveryResetTimer) clearTimeout(recoveryResetTimer);
        resumePlaybackRef.current = wasPlayingRef.current;
        const time = player.currentTime || el.currentTime || 0;
        if (time > 0) {
          retryPositionRef.current = { identity: mediaIdentity, time };
          saver?.flush(time);
        }
        const attempts = autoRecoveriesRef.current.identity === mediaIdentity
          ? autoRecoveriesRef.current.count
          : 0;
        const canRecover = attempts < MAX_AUTO_RECOVERIES;
        setReady(false);
        setFailure(canRecover ? message : "Video could not be loaded");
        if (!canRecover) return;
        autoRecoveriesRef.current = { identity: mediaIdentity, count: attempts + 1 };
        void Promise.resolve().then(() => onReloadRef.current?.() ?? null).then((url) => {
          if (cancelled) return;
          if (url && new URL(url, document.baseURI).href !== el.src) setSource({ identity: mediaIdentity, url });
          else setFailure("Video could not be loaded");
        }).catch(() => {
          if (!cancelled) setFailure("Video could not be loaded");
        });
      };
      const playbackVisible = () => !document.hidden || document.pictureInPictureElement === el;
      const startStallTimer = () => {
        if (!playbackVisible() || cancelled || refreshAttempted || el.paused || el.ended || stallTimer) return;
        stallTimer = setTimeout(() => {
          stallTimer = null;
          if (!playbackVisible() || cancelled || el.paused || el.ended) return;
          const time = el.currentTime;
          if (Number.isFinite(time) && Math.abs(time - lastProgressTime) > 0.05) {
            lastProgressTime = time;
            startStallTimer();
          } else {
            markFailed("Video stalled; retrying");
          }
        }, 30_000);
      };
      const recordPlaying = () => {
        clearStallTimer();
        startStallTimer();
        recordFirstFrame();
        if (autoRecoveriesRef.current.identity === mediaIdentity && autoRecoveriesRef.current.count > 0) {
          if (recoveryResetTimer) clearTimeout(recoveryResetTimer);
          const startedAt = el.currentTime;
          recoveryResetTimer = setTimeout(() => {
            if (!cancelled && !el.paused && el.currentTime - startedAt > 0.5) {
              autoRecoveriesRef.current = { identity: mediaIdentity, count: 0 };
            }
          }, 5000);
        }
        if (bufferingStartedAt !== null) {
          performance.measure("leap:video:buffering", {
            start: bufferingStartedAt,
            end: performance.now(),
          });
          bufferingStartedAt = null;
        }
      };

      const saver = resumeKey ? createResumeSaver(resumeKey) : null;
      let resumeApplied = false;
      const applyResume = () => {
        if (cancelled || resumeApplied || el.readyState < 1) return;
        resumeApplied = true;
        const retryPosition = retryPositionRef.current?.identity === mediaIdentity
          ? retryPositionRef.current.time
          : null;
        if (retryPosition !== null) retryPositionRef.current = null;
        const saved = retryPosition ?? (resumeKey ? readResumeTime(resumeKey) : null);
        const duration = player.duration || el.duration;
        const t = saved == null ? null : retryPosition !== null
          ? retryTimeWithinDuration(saved, duration)
          : resumeTimeWithinDuration(saved, duration);
        if (t != null) el.currentTime = t;
        if (resumePlaybackRef.current) {
          resumePlaybackRef.current = false;
          void el.play().catch(() => {});
        }
      };
      if (el.readyState >= 1) applyResume();
      else el.addEventListener("loadedmetadata", applyResume, { once: true });

      player.on("timeupdate", () => {
        const ct = player.currentTime;
        onTimeUpdateRef.current?.(ct);
        if (resumeApplied) saver?.save(ct);
        if (Number.isFinite(ct) && Math.abs(ct - lastProgressTime) > 0.05) {
          lastProgressTime = ct;
          clearStallTimer();
          startStallTimer();
        }
        const list = markersRef.current;
        const labelEl = chapterLabelRef.current;
        if (!labelEl || !list?.length) return;
        const active = list.reduce<VideoPlayerMarker | null>((latest, marker) =>
          Number.isFinite(marker.time) && marker.time >= 0 && marker.time <= ct
            && (!latest || marker.time > latest.time) ? marker : latest, null);
        const label = active?.label ?? null;
        if (label !== lastLabelRef.current) {
          labelEl.textContent = label ?? "";
          labelEl.classList.toggle("plyr__chapter-label--hidden", !label);
          lastLabelRef.current = label;
        }
      });
      player.on("ready", applyResume);
      player.on("play", () => {
        wasPlayingRef.current = true;
        startStallTimer();
      });
      player.on("pause", () => {
        // A fatal media error can pause the element before its error event is delivered.
        // Keep the previous play intent so recovery resumes without another click.
        if (!el.error) wasPlayingRef.current = false;
        clearStallTimer();
      });
      player.on("waiting", () => {
        if (firstFrameRecorded && bufferingStartedAt === null) bufferingStartedAt = performance.now();
        startStallTimer();
      });
      player.on("stalled", startStallTimer);
      player.on("playing", recordPlaying);
      player.on("loadeddata", recordFirstFrame);
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
      const startStartupTimer = () => {
        if (document.hidden || cancelled || refreshAttempted || el.readyState >= 1) return;
        startupTimer = setTimeout(() => markFailed("Video is taking too long to load"), 20_000);
      };
      const onVisibilityChange = () => {
        clearTimers();
        if (!document.hidden && el.readyState < 1) startStartupTimer();
        startStallTimer();
      };
      const onPiPChange = () => {
        clearStallTimer();
        startStallTimer();
      };
      document.addEventListener("visibilitychange", onVisibilityChange);
      el.addEventListener("enterpictureinpicture", onPiPChange);
      el.addEventListener("leavepictureinpicture", onPiPChange);
      // Chromium may ask for PiP when the user leaves an audible playing tab.
      // The browser owns eligibility and permission; visibilitychange alone has no user activation.
      setAutoPiPAction(() => {
        if (!cancelled && !el.paused && !el.ended && document.pictureInPictureEnabled
          && typeof el.requestPictureInPicture === "function") {
          void el.requestPictureInPicture().catch(() => {});
        }
      });
      if (el.readyState >= 1) markReady();
      else startStartupTimer();

      const persistNow = () => {
        const time = player.currentTime || el.currentTime || 0;
        if (time > 0) saver?.flush(time);
      };
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
      const releaseFocus = bindPlaybackFocus(document.body);

      return () => {
        cancelled = true;
        clearTimers();
        if (recoveryResetTimer) clearTimeout(recoveryResetTimer);
        persistNow();
        saver?.cancel();
        if (hudHideRef.current) clearTimeout(hudHideRef.current);
        window.removeEventListener("pagehide", persistNow);
        window.removeEventListener("keydown", onKeyDown);
        releaseFocus();
        document.removeEventListener("visibilitychange", onVisibilityChange);
        el.removeEventListener("enterpictureinpicture", onPiPChange);
        el.removeEventListener("leavepictureinpicture", onPiPChange);
        setAutoPiPAction(null);
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
    }, [mediaIdentity, resumeKey, pushHud]);

    const markersKey = markerSignature(markers);
    useEffect(() => {
      const el = localRef.current;
      if (!autoPlayRequested || !el) return;
      let cancelled = false;
      let attempted = false;
      const tryPlay = () => {
        if (cancelled || attempted) return;
        attempted = true;
        void el.play().catch(() => {}).finally(() => {
          if (!cancelled) onAutoPlayAttemptRef.current?.();
        });
      };
      if (el.readyState >= 2) tryPlay();
      else el.addEventListener("canplay", tryPlay, { once: true });
      const fallback = window.setTimeout(tryPlay, 400);
      return () => {
        cancelled = true;
        el.removeEventListener("canplay", tryPlay);
        window.clearTimeout(fallback);
      };
    }, [autoPlayRequested, playerScope]);

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
    }, [vttBlobUrl, activeSrc, instanceId]);

    const hudBits = hud ? formatHud(hud) : null;

    return (
      <div className={cn(VIDEO_PLAYER_FRAME, "motion-safe:animate-page-in", className)}>
        <PlyrMount key={playerScope} src={activeSrc} setRef={setRef} attach={attach} />
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
        {Boolean(activeSrc) && !ready && (
          <div className="absolute inset-0 z-10 overflow-hidden rounded-[inherit]">
            {failure ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 bg-muted/90">
                <AlertCircle size={24} className="text-danger-fg" />
                <p className="text-sm text-muted-foreground">{failure}</p>
                <button
                  type="button"
                  onClick={() => {
                    if (retrying) return;
                    const retryElement = localRef.current;
                    autoRecoveriesRef.current = { identity: mediaIdentity, count: 0 };
                    setRetryingScope(playerScope);
                    void Promise.resolve().then(() => onReloadRef.current?.() ?? null).catch(() => null).then((url) => {
                      if (localRef.current !== retryElement) return;
                      const nextUrl = url ?? src;
                      if (nextUrl !== activeSrc) {
                        setSource({ identity: mediaIdentity, url: nextUrl });
                        return;
                      }
                      setFailure(null);
                      setInstanceId((n) => n + 1);
                    }).finally(() => setRetryingScope((scope) => scope === playerScope ? null : scope));
                  }}
                  disabled={retrying}
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
                >
                  <RotateCcw size={14} /> {retrying ? "Retrying…" : "Retry"}
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
