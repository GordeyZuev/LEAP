"use client";

import { useEffect } from "react";

const REFRESH_BEFORE_EXPIRY_SEC = 120;
const MIN_LONG_LIVED_REFRESH_MS = 30_000;
const RETRY_REFRESH_MS = 60_000;
const MIN_RETRY_MS = 1_000;
const MAX_REFRESH_RETRIES = 3;

export function presignedRefreshDelayMs(expiresIn: number, ageMs = 0): number {
  const refreshAfterSec = expiresIn > REFRESH_BEFORE_EXPIRY_SEC
    ? expiresIn - REFRESH_BEFORE_EXPIRY_SEC
    : expiresIn / 2;
  const refreshAfterMs = expiresIn > REFRESH_BEFORE_EXPIRY_SEC
    ? Math.max(MIN_LONG_LIVED_REFRESH_MS, refreshAfterSec * 1000)
    : refreshAfterSec * 1000;
  return Math.max(0, refreshAfterMs - ageMs);
}

export function presignedRetryDelayMs(expiresIn: number, ageMs: number): number {
  const remainingMs = expiresIn * 1000 - ageMs;
  return Math.max(MIN_RETRY_MS, Math.min(RETRY_REFRESH_MS, remainingMs / 2));
}

export function usePresignedMediaRefresh({
  expiresIn,
  enabled,
  url,
  issuedAtMs,
  onRefresh,
}: {
  expiresIn: number | null | undefined;
  enabled: boolean;
  url: string | null | undefined;
  issuedAtMs: number;
  onRefresh: () => Promise<boolean | string | null>;
}) {
  useEffect(() => {
    if (!enabled || !url || !expiresIn || !Number.isFinite(expiresIn) || expiresIn < 0 || !issuedAtMs) return;
    const delayMs = presignedRefreshDelayMs(expiresIn, Math.max(0, Date.now() - issuedAtMs));
    let cancelled = false;
    let retries = 0;
    let timer: number;
    const refresh = async () => {
      const succeeded = await onRefresh().catch(() => false);
      if (!cancelled && !succeeded && retries < MAX_REFRESH_RETRIES) {
        retries += 1;
        timer = window.setTimeout(refresh, presignedRetryDelayMs(expiresIn, Date.now() - issuedAtMs));
      }
    };
    timer = window.setTimeout(refresh, delayMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [enabled, expiresIn, url, issuedAtMs, onRefresh]);
}
