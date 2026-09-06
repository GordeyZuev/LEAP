/** Shared speed ladder and shortcut copy for the listener and the `?` overlay. */

export const PLAYER_SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;

export const PLAYER_SHORTCUTS: { keys: string; label: string }[] = [
  { keys: "Space / K", label: "Play or pause" },
  { keys: "J / L", label: "Back / forward 10 seconds" },
  { keys: "← / →", label: "Back / forward 5 seconds" },
  { keys: "↑ / ↓", label: "Volume" },
  { keys: "M", label: "Mute" },
  { keys: "F", label: "Fullscreen" },
  { keys: "C", label: "Captions" },
  { keys: "0–9", label: "Jump to 0%–90%" },
  { keys: "[ / ]", label: "Slower / faster" },
  { keys: "Shift + , / .", label: "Slower / faster" },
  { keys: "?", label: "This list" },
];

type PlayerKeysTarget = {
  togglePlay: () => void;
  rewind: (amount?: number) => void;
  forward: (amount?: number) => void;
  increaseVolume: (amount: number) => void;
  decreaseVolume: (amount: number) => void;
  muted: boolean;
  speed: number;
  currentTime: number;
  duration: number;
  fullscreen: { toggle: () => void };
  toggleCaptions: () => void;
};

function shortcutsBlocked(event: KeyboardEvent): boolean {
  if (event.isComposing) return true;
  const t = event.target;
  if (t instanceof Element && t.closest("input, textarea, select, [contenteditable='true']")) {
    return true;
  }
  if (document.querySelector('[role="dialog"], [aria-modal="true"]')) return true;
  return false;
}

function stepSpeed(player: PlayerKeysTarget, dir: -1 | 1) {
  const i = PLAYER_SPEEDS.findIndex((s) => s === player.speed);
  const idx = i < 0 ? PLAYER_SPEEDS.indexOf(1) : i;
  player.speed = PLAYER_SPEEDS[Math.min(PLAYER_SPEEDS.length - 1, Math.max(0, idx + dir))] ?? 1;
}

export function handlePlayerKey(
  event: KeyboardEvent,
  player: PlayerKeysTarget,
  help: { isOpen: () => boolean; toggle: () => void; close: () => void },
): void {
  if (event.ctrlKey || event.metaKey || event.altKey) return;

  if (event.key === "Escape") {
    if (help.isOpen()) {
      event.preventDefault();
      help.close();
    }
    return;
  }

  const shift = event.shiftKey;
  const key = event.key;

  if (key === "?" || (shift && key === "/")) {
    if (shortcutsBlocked(event) && !help.isOpen()) return;
    event.preventDefault();
    help.toggle();
    return;
  }

  if (shortcutsBlocked(event)) return;

  if (shift && (key === "<" || key === ">" || key === "," || key === ".")) {
    event.preventDefault();
    stepSpeed(player, key === "<" || key === "," ? -1 : 1);
    return;
  }

  if (shift) return;

  switch (key) {
    case " ":
    case "k":
    case "K":
      event.preventDefault();
      void player.togglePlay();
      return;
    case "j":
    case "J":
      event.preventDefault();
      player.rewind(10);
      return;
    case "l":
    case "L":
      event.preventDefault();
      player.forward(10);
      return;
    case "ArrowLeft":
      event.preventDefault();
      player.rewind(5);
      return;
    case "ArrowRight":
      event.preventDefault();
      player.forward(5);
      return;
    case "ArrowUp":
      event.preventDefault();
      player.increaseVolume(0.1);
      return;
    case "ArrowDown":
      event.preventDefault();
      player.decreaseVolume(0.1);
      return;
    case "m":
    case "M":
      event.preventDefault();
      player.muted = !player.muted;
      return;
    case "f":
    case "F":
      event.preventDefault();
      player.fullscreen.toggle();
      return;
    case "c":
    case "C":
      event.preventDefault();
      player.toggleCaptions();
      return;
    case "[":
      event.preventDefault();
      stepSpeed(player, -1);
      return;
    case "]":
      event.preventDefault();
      stepSpeed(player, 1);
      return;
    default:
      if (key >= "0" && key <= "9" && player.duration) {
        event.preventDefault();
        player.currentTime = (player.duration / 10) * Number(key);
      }
  }
}
