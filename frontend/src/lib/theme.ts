export type ThemeMode = "light" | "dark" | "system";

export const THEME_KEY = "theme";
export const THEME_DARK_COOKIE = "leap-theme-dark";

function persistResolvedDark(dark: boolean) {
  document.cookie = `${THEME_DARK_COOKIE}=${dark ? "1" : "0"};path=/;max-age=31536000;SameSite=Lax`;
}

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

/**
 * Next mode for the public sun/moon button.
 *
 * Switches to the other appearance. When that appearance is what the OS is
 * already doing, store "system" so a later OS change keeps following it.
 * Two clicks from an automatic page return to automatic.
 */
export function nextPublicTheme(current: ThemeMode, systemDark: boolean): ThemeMode {
  const resolvedDark = current === "dark" || (current === "system" && systemDark);
  const next: ThemeMode = resolvedDark ? "light" : "dark";
  return (next === "dark") === systemDark ? "system" : next;
}

/** Toggle the `dark` class on <html> to match the given mode. */
export function applyTheme(mode: ThemeMode): void {
  if (typeof document === "undefined") return;
  const dark = resolveDark(mode);
  document.documentElement.classList.toggle("dark", dark);
  persistResolvedDark(dark);
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
