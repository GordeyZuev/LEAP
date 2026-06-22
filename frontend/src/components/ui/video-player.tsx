"use client";

import { forwardRef, useCallback, useEffect, useRef } from "react";
import Plyr from "plyr";
import "plyr/dist/plyr.css";

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
    const localRef = useRef<HTMLVideoElement>(null);
    // Keep callback in a ref so Plyr's listener is never stale across re-renders
    const onTimeUpdateRef = useRef(onTimeUpdate);
    useEffect(() => { onTimeUpdateRef.current = onTimeUpdate; }, [onTimeUpdate]);

    // Stable ref callback: merges local ref + forwarded ref without recreating on each render
    const setRef = useCallback((el: HTMLVideoElement | null) => {
      (localRef as React.MutableRefObject<HTMLVideoElement | null>).current = el;
      if (typeof forwardedRef === "function") forwardedRef(el);
      else if (forwardedRef) (forwardedRef as React.MutableRefObject<HTMLVideoElement | null>).current = el;
    // forwardedRef from useRef() is stable for the lifetime of the parent component
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
      const el = localRef.current;
      if (!el) return;

      const player = new Plyr(el, {
        // Seek 5s per arrow key — better granularity for lecture navigation
        seekTime: 5,
        // Show elapsed time (not countdown) — more intuitive for long videos
        invertTime: false,
        speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
        tooltips: { controls: true, seek: true },
        keyboard: { focused: true, global: false },
        // update: true — re-scans tracks after mount, needed for async VTT blob URLs
        captions: { active: false, language: "auto", update: true },
        // Visual chapter markers on the progress bar with HTML labels
        markers: {
          enabled: (markers?.length ?? 0) > 0,
          points: (markers ?? []).map((m) => ({ time: m.time, label: m.label })),
        },
        i18n: {
          restart: "Сначала",
          rewind: "Назад {seektime}с",
          play: "Воспроизвести",
          pause: "Пауза",
          fastForward: "Вперёд {seektime}с",
          seek: "Перемотка",
          seekLabel: "{currentTime} из {duration}",
          played: "Воспроизведено",
          buffered: "Буферизовано",
          currentTime: "Текущее время",
          duration: "Длительность",
          volume: "Громкость",
          mute: "Выключить звук",
          unmute: "Включить звук",
          enableCaptions: "Включить субтитры",
          disableCaptions: "Выключить субтитры",
          download: "Скачать",
          enterFullscreen: "Полный экран",
          exitFullscreen: "Выйти из полного экрана",
          frameTitle: "Плеер",
          captions: "Субтитры",
          settings: "Настройки",
          pip: "Картинка в картинке",
          speed: "Скорость",
          normal: "Обычная",
          quality: "Качество",
          loop: "Повтор",
          start: "Начало",
          end: "Конец",
          all: "Все",
          reset: "Сброс",
          disabled: "Выкл",
          enabled: "Вкл",
          advertisement: "",
          qualityBadge: { 2160: "4K", 1440: "HD", 1080: "HD", 720: "HD", 576: "SD", 480: "SD" },
        },
      });

      player.on("timeupdate", () => onTimeUpdateRef.current?.(player.currentTime));

      return () => { player.destroy(); };
      // Reinit only when src changes; markers/vttBlobUrl handled by track/config above
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [src]);

    return (
      <div className="aspect-video w-full overflow-hidden rounded-xl bg-black">
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video ref={setRef} src={src} preload="metadata" className="h-full w-full">
          {vttBlobUrl && <track kind="subtitles" src={vttBlobUrl} label="Субтитры" default />}
        </video>
      </div>
    );
  }
);
