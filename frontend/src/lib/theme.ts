export type ThemeMode = "light" | "dark" | "system";

export const THEME_KEY = "theme";

/** Read the persisted preference; defaults to "system". */
export function getStoredTheme(): ThemeMode {
  if (typeof window === "undefined") return "system";
  const v = window.localStorage.getItem(THEME_KEY);
  return v === "light" || v === "dark" || v === "system" ? v : "system";
}

export function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Resolve a mode to a concrete light/dark decision. */
export function resolveDark(mode: ThemeMode): boolean {
  return mode === "dark" || (mode === "system" && systemPrefersDark());
}

/** Toggle the `dark` class on <html> to match the given mode. */
export function applyTheme(mode: ThemeMode): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", resolveDark(mode));
}

/**
 * Apply a theme without the cross-fade smear.
 *
 * A theme flip changes color, background, border and shadow on nearly every
 * element at once, so every `transition-colors` in the tree fires together and
 * the switch drags instead of snapping. Kill transitions, force a reflow so the
 * new colors commit while that still applies, then restore on the next frame.
 */
export function applyThemeInstantly(mode: ThemeMode): void {
  if (typeof document === "undefined") return;
  const style = document.createElement("style");
  style.append(document.createTextNode("*,*::before,*::after{transition:none !important}"));
  document.head.append(style);

  applyTheme(mode);

  // Reading a layout property flushes the pending style recalculation.
  void document.body.offsetHeight;

  requestAnimationFrame(() => {
    requestAnimationFrame(() => style.remove());
  });
}
