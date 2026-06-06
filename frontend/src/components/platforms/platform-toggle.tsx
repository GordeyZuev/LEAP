"use client";

import { cn } from "@/lib/utils";

// Shared boolean toggle row used across platform / display-config forms.
// Lives in its own module so both platform-fields and display-config-fields can
// import it without creating a circular dependency.
export function PlatformToggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between py-1.5">
      <span className="text-sm text-gray-700">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
          checked ? "bg-[#224C87]" : "bg-gray-200"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all duration-150",
            checked ? "left-[1.125rem]" : "left-0.5"
          )}
        />
      </button>
    </label>
  );
}
