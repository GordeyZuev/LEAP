import type { PlayerKeyAction } from "@/components/ui/video-player-keys";

export const HUD_STACK_MS = 600;
export const HUD_HIDE_MS = 700;

export type HudView =
  | { kind: "seek"; dir: 1 | -1; seconds: number }
  | { kind: "speed"; value: number }
  | { kind: "volume"; percent: number; muted: boolean }
  | { kind: "jump"; percent: number };

export function applyHudAction(
  prev: HudView | null,
  lastAt: number,
  now: number,
  action: PlayerKeyAction,
): HudView {
  if (action.type === "seek") {
    const dir: 1 | -1 = action.seconds >= 0 ? 1 : -1;
    const add = Math.abs(action.seconds);
    if (prev?.kind === "seek" && prev.dir === dir && now - lastAt < HUD_STACK_MS) {
      return { kind: "seek", dir, seconds: prev.seconds + add };
    }
    return { kind: "seek", dir, seconds: add };
  }
  if (action.type === "speed") {
    return { kind: "speed", value: action.value };
  }
  if (action.type === "volume") {
    return { kind: "volume", percent: action.percent, muted: action.muted };
  }
  if (action.type === "mute") {
    return { kind: "volume", percent: action.muted ? 0 : 100, muted: action.muted };
  }
  return { kind: "jump", percent: action.percent };
}
