"use client";

import { forwardRef, useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import Plyr from "plyr";
import "plyr/dist/plyr.css";
import { cn } from "@/lib/utils";

export interface VideoPlayerMarker {
  time: number;
  label: string;
}

interface VideoPlayerProps {
  src: string;
  vttBlobUrl?: string | null;
  markers?: VideoPlayerMarker[];
  onTimeUpdate?: (currentTime: number) => void;
}

export const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
  function VideoPlayer({ src, vttBlobUrl, markers, onTimeUpdate }, forwardedRef) {
    const [ready, setReady] = useState(false);
    const localRef = useRef<HTMLVideoElement>(null);
    const onTimeUpdateRef = useRef(onTimeUpdate);
    useEffect(() => { onTimeUpdateRef.current = onTimeUpdate; }, [onTimeUpdate]);

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
      let cancelled = false;

      const player = new Plyr(el, {
        seekTime: 5,
        invertTime: false,
        speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
        tooltips: { controls: true, seek: true },
        keyboard: { focused: true, global: false },
        captions: { active: false, language: "auto", update: true },
        // markers.enabled stays false at init — duration is 0 until loadedmetadata,
        // which would pin all dots at left:0%. Injected via DOM below instead.
        markers: { enabled: false, points: [] as { time: number; label: string }[] },
        // i18n omitted — Plyr's built-in labels are already English.
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

      // Live "now playing" chapter label, injected next to Plyr's own time
      // display — Plyr has no built-in slot for this, same DOM-injection
      // approach as the progress markers above.
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

      player.on("timeupdate", () => {
        const ct = player.currentTime;
        onTimeUpdateRef.current?.(ct);
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
      player.on("canplay", () => { if (!cancelled) setReady(true); });

      return () => {
        cancelled = true;
        player.destroy();
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [src]);

    return (
      <div className="relative aspect-video w-full overflow-hidden rounded-xl">
        <video ref={setRef} src={src} preload="metadata" className="block w-full">
          {vttBlobUrl && <track kind="subtitles" src={vttBlobUrl} label="Subtitles" default />}
        </video>
        <div
          className={cn(
            "pointer-events-none absolute inset-0 flex items-center justify-center bg-black transition-opacity duration-300",
            ready ? "opacity-0" : "opacity-100",
          )}
        >
          <Loader2 size={24} className="animate-spin text-white/40" />
        </div>
      </div>
    );
  }
);
