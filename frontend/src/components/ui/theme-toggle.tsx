"use client";

import { Moon, Sun } from "lucide-react";

import { SegmentedField } from "@/components/ui/segmented-field";
import { useTheme } from "@/hooks/use-theme";
import { nextPublicTheme, systemPrefersDark, type ThemeMode } from "@/lib/theme";

/** Square chip matching the public Copy link control. */
const PUBLIC_THEME_BUTTON =
  "pressable flex size-9 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-secondary-foreground " +
  "hover:border-primary/40 hover:bg-primary/5 hover:text-primary " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";

const OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

/** Segmented Light / Dark / System control bound to the persisted theme. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <SegmentedField
      label="Theme"
      labelHidden
      value={theme}
      options={OPTIONS}
      onChange={setTheme}
    />
  );
}

/**
 * Sun/moon switch for public pages. The icon is the appearance the click
 * applies. A choice that matches the OS is stored as system.
 */
export function PublicThemeButton() {
  const { theme, setTheme, dark } = useTheme();
  const label = dark ? "Switch to light theme" : "Switch to dark theme";
  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => setTheme(nextPublicTheme(theme, systemPrefersDark()))}
      className={PUBLIC_THEME_BUTTON}
    >
      {dark ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
    </button>
  );
}
