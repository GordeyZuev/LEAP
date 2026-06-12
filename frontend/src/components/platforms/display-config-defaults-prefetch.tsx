"use client";

import { useDisplayConfigDefaults } from "@/hooks/use-references";

/** Warm React Query cache for display-config defaults (used by preset/template editors). */
export function DisplayConfigDefaultsPrefetch() {
  useDisplayConfigDefaults();
  return null;
}
