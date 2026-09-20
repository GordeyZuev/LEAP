"use client";

import { useCallback, useEffect, useState } from "react";
import { applyThemeInstantly, getStoredTheme, resolveDark, THEME_KEY, type ThemeMode } from "@/lib/theme";

/**
 * Read/write the theme preference. The root layout sets `.dark` from a cookie
 * written here so the first paint matches without an inline script (React 19
 * does not run `<script>` tags rendered from components).
 */
export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>("system");
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const mode = getStoredTheme();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setThemeState(mode);
    setDark(resolveDark(mode));
    applyThemeInstantly(mode);
  }, []);

  const setTheme = useCallback((mode: ThemeMode) => {
    setThemeState(mode);
    setDark(resolveDark(mode));
    window.localStorage.setItem(THEME_KEY, mode);
    applyThemeInstantly(mode);
  }, []);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      applyThemeInstantly("system");
      setDark(resolveDark("system"));
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  return { theme, setTheme, dark };
}
