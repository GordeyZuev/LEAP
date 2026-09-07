"use client";

import { useCallback, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import {
  defaultAnalyticsRange,
  type AnalyticsDateRange,
  type DateRangePreset,
  presetRange,
  validateRange,
} from "@/lib/analytics-date-range";

export function useAnalyticsDateRange(
  paramPrefix = "",
  syncToUrl = true,
  options?: { accountCreatedAt?: string },
) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const fromKey = `${paramPrefix}from`;
  const toKey = `${paramPrefix}to`;

  const urlFrom = syncToUrl ? (searchParams.get(fromKey) ?? "") : "";
  const urlTo = syncToUrl ? (searchParams.get(toKey) ?? "") : "";

  const initial = useMemo(() => {
    if (syncToUrl && urlFrom && urlTo && !validateRange(urlFrom, urlTo)) {
      return { from: urlFrom, to: urlTo, preset: "custom" as const };
    }
    const d = defaultAnalyticsRange();
    return { ...d, preset: "28d" as const };
  }, [syncToUrl, urlFrom, urlTo]);

  const [range, setRangeState] = useState<AnalyticsDateRange>({ from: initial.from, to: initial.to });
  const [preset, setPreset] = useState<DateRangePreset>(initial.preset);

  const validationError = useMemo(() => validateRange(range.from, range.to), [range.from, range.to]);

  const syncUrl = useCallback(
    (next: AnalyticsDateRange) => {
      if (!syncToUrl) return;
      const params = new URLSearchParams(searchParams.toString());
      params.set(fromKey, next.from);
      params.set(toKey, next.to);
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [fromKey, pathname, router, searchParams, syncToUrl, toKey],
  );

  const setRange = useCallback(
    (next: AnalyticsDateRange, nextPreset: DateRangePreset = "custom") => {
      setRangeState(next);
      setPreset(nextPreset);
      if (validateRange(next.from, next.to) === null) {
        syncUrl(next);
      }
    },
    [syncUrl],
  );

  const applyPreset = useCallback(
    (p: Exclude<DateRangePreset, "custom">) => {
      const next = presetRange(p, options?.accountCreatedAt);
      setRange(next, p);
    },
    [options?.accountCreatedAt, setRange],
  );

  return {
    range,
    preset,
    validationError,
    setRange,
    applyPreset,
    isValid: validationError === null,
  };
}
