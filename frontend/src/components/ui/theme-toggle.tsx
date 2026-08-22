"use client";

import { SegmentedField } from "@/components/ui/segmented-field";
import { useTheme } from "@/hooks/use-theme";
import type { ThemeMode } from "@/lib/theme";

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
