"use client";

import { useCallback, useEffect, useState } from "react";
import { applyTheme, getStoredTheme, THEME_KEY, type ThemeMode } from "@/lib/theme";

/**
 * Read/write the theme preference. The `dark` class is applied pre-paint by the
 * inline ThemeScript; this hook keeps it in sync on change and reacts to OS
 * theme changes while in "system" mode.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>("system");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setThemeState(getStoredTheme());
  }, []);

  const setTheme = useCallback((mode: ThemeMode) => {
    setThemeState(mode);
    window.localStorage.setItem(THEME_KEY, mode);
    applyTheme(mode);
  }, []);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  return { theme, setTheme };
}
