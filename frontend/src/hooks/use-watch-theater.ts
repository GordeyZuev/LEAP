"use client";

import { useLocalStorageState } from "@/hooks/use-local-storage-state";

const STORAGE_KEY = "leap-watch-theater";

function parseTheater(raw: string | null) {
  if (raw === "1") return true;
  if (raw === "0") return false;
  return undefined;
}

function serializeTheater(value: boolean) {
  return value ? "1" : "0";
}

/** Wide-player preference for public watch pages. Server snapshot is off (SSR). */
export function useWatchTheater() {
  const [theater, setTheater] = useLocalStorageState(
    STORAGE_KEY,
    false,
    parseTheater,
    serializeTheater,
  );
  return { theater, setTheater };
}
