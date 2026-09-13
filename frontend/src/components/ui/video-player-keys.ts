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

export type PlayerKeyAction =
  | { type: "seek"; seconds: number }
  | { type: "speed"; value: number }
  | { type: "volume"; percent: number; muted: boolean }
  | { type: "mute"; muted: boolean }
  | { type: "jumpPercent"; percent: number };

export type PlayerKeysTarget = {
  togglePlay: () => void;
  rewind: (amount?: number) => void;
  forward: (amount?: number) => void;
  increaseVolume: (amount: number) => void;
  decreaseVolume: (amount: number) => void;
  muted: boolean;
  volume: number;
  speed: number;
  currentTime: number;
  duration: number;
  fullscreen: { toggle: () => void };
  toggleCaptions: () => void;
};

const TEXT_ENTRY = "input, textarea, select, [contenteditable='true']";
const ACTIVATE_TARGET = "button, a, [role='tab'], [role='menuitem']";
const ARROW_WIDGET = "[role='tablist'], [role='menu'], [role='listbox'], [role='slider'], [role='radiogroup']";

function targetClosest(event: KeyboardEvent, selector: string): boolean {
  const t = event.target;
  if (!t || typeof (t as { closest?: (sel: string) => Element | null }).closest !== "function") {
    return false;
  }
  return Boolean((t as Element).closest(selector));
}

export function shortcutsBlocked(event: KeyboardEvent): boolean {
  if (event.isComposing) return true;
  if (targetClosest(event, TEXT_ENTRY)) return true;
  if (typeof document !== "undefined" && document.querySelector('[role="dialog"], [aria-modal="true"]')) {
    return true;
  }
  return false;
}

export function spaceActivateBlocked(event: KeyboardEvent): boolean {
  return targetClosest(event, ACTIVATE_TARGET);
}

export function arrowWidgetBlocked(event: KeyboardEvent): boolean {
  return targetClosest(event, ARROW_WIDGET);
}

function stepSpeed(player: PlayerKeysTarget, dir: -1 | 1) {
  const i = PLAYER_SPEEDS.findIndex((s) => s === player.speed);
  const idx = i < 0 ? PLAYER_SPEEDS.indexOf(1) : i;
  player.speed = PLAYER_SPEEDS[Math.min(PLAYER_SPEEDS.length - 1, Math.max(0, idx + dir))] ?? 1;
  return player.speed;
}

function volumeAction(player: PlayerKeysTarget): PlayerKeyAction {
  return { type: "volume", percent: Math.round(player.volume * 100), muted: player.muted };
}

export function handlePlayerKey(
  event: KeyboardEvent,
  player: PlayerKeysTarget,
  help: { isOpen: () => boolean; toggle: () => void; close: () => void },
): PlayerKeyAction | undefined {
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
    return { type: "speed", value: stepSpeed(player, key === "<" || key === "," ? -1 : 1) };
  }

  if (shift) return;

  switch (key) {
    case " ":
    case "k":
    case "K":
      if (key === " " && spaceActivateBlocked(event)) return;
      event.preventDefault();
      void player.togglePlay();
      return;
    case "j":
    case "J":
      event.preventDefault();
      player.rewind(10);
      return { type: "seek", seconds: -10 };
    case "l":
    case "L":
      event.preventDefault();
      player.forward(10);
      return { type: "seek", seconds: 10 };
    case "ArrowLeft":
      if (arrowWidgetBlocked(event)) return;
      event.preventDefault();
      player.rewind(5);
      return { type: "seek", seconds: -5 };
    case "ArrowRight":
      if (arrowWidgetBlocked(event)) return;
      event.preventDefault();
      player.forward(5);
      return { type: "seek", seconds: 5 };
    case "ArrowUp":
      if (arrowWidgetBlocked(event)) return;
      event.preventDefault();
      player.increaseVolume(0.1);
      return volumeAction(player);
    case "ArrowDown":
      if (arrowWidgetBlocked(event)) return;
      event.preventDefault();
      player.decreaseVolume(0.1);
      return volumeAction(player);
    case "m":
    case "M":
      event.preventDefault();
      player.muted = !player.muted;
      return { type: "mute", muted: player.muted };
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
      return { type: "speed", value: stepSpeed(player, -1) };
    case "]":
      event.preventDefault();
      return { type: "speed", value: stepSpeed(player, 1) };
    default:
      if (key >= "0" && key <= "9" && player.duration) {
        event.preventDefault();
        const percent = Number(key) * 10;
        player.currentTime = (player.duration / 10) * Number(key);
        return { type: "jumpPercent", percent };
      }
  }
}
