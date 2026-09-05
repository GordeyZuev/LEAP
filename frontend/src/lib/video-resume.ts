const PREFIX = "leap:video-pos:";
const SAVE_MS = 1500;
const SKIP_START_SECONDS = 2;
const END_SECONDS = 5;

export function recordingResumeKey(recordingId: string, variant: "processed" | "original"): string {
  return `${PREFIX}recording:${recordingId}:${variant}`;
}

export function playlistResumeKey(token: string, itemId: number): string {
  return `${PREFIX}playlist:${token}:${itemId}`;
}

export function readResumeTime(key: string): number | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw == null) return null;
    const t = Number(raw);
    return Number.isFinite(t) && t > 0 ? t : null;
  } catch {
    return null;
  }
}

export function writeResumeTime(key: string, time: number): void {
  try {
    if (!Number.isFinite(time) || time < SKIP_START_SECONDS) {
      window.localStorage.removeItem(key);
      return;
    }
    window.localStorage.setItem(key, String(Math.floor(time)));
  } catch {
    /* private mode / quota */
  }
}

export function resumeTimeWithinDuration(saved: number, duration: number): number | null {
  if (!Number.isFinite(duration) || duration <= SKIP_START_SECONDS) return null;
  if (saved < SKIP_START_SECONDS) return null;
  if (saved >= duration - END_SECONDS) return null;
  return Math.min(saved, duration);
}

export function createResumeSaver(key: string): { save: (time: number) => void; flush: (time: number) => void; cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let last = 0;

  const flush = (time: number) => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    last = time;
    writeResumeTime(key, time);
  };

  return {
    save(time: number) {
      last = time;
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        writeResumeTime(key, last);
      }, SAVE_MS);
    },
    flush,
    cancel() {
      if (timer) clearTimeout(timer);
      timer = null;
    },
  };
}
