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
            dot.style.left = `${(m.time / duration) * 100}%`;
            bar.appendChild(dot);
          });
        };
        if (el.readyState >= 1) injectMarkers();
        else el.addEventListener("loadedmetadata", injectMarkers, { once: true });
      }

      player.on("timeupdate", () => onTimeUpdateRef.current?.(player.currentTime));

      return () => { player.destroy(); };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [src]);

    return (
      <div className="aspect-video w-full">
        <video ref={setRef} src={src} preload="metadata" className="block w-full">
          {vttBlobUrl && <track kind="subtitles" src={vttBlobUrl} label="Субтитры" default />}
        </video>
      </div>
    );
  }
);
