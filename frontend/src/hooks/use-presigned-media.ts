"use client";

import { useEffect } from "react";

const REFRESH_BEFORE_EXPIRY_SEC = 120;
const MIN_REFRESH_MS = 30_000;

export function usePresignedMediaRefresh({
  expiresIn,
  enabled,
  onRefresh,
}: {
  expiresIn: number | null | undefined;
  enabled: boolean;
  onRefresh: () => void;
}) {
  useEffect(() => {
    if (!enabled || !expiresIn || expiresIn <= REFRESH_BEFORE_EXPIRY_SEC) return;
    const delayMs = Math.max(MIN_REFRESH_MS, (expiresIn - REFRESH_BEFORE_EXPIRY_SEC) * 1000);
    const id = window.setTimeout(() => onRefresh(), delayMs);
    return () => window.clearTimeout(id);
  }, [enabled, expiresIn, onRefresh]);
}
