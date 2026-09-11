"use client";

import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/api/client";

/** Subset of `GET /presets/:id` used for override preload and Yandex browse. */
export interface PresetDetail {
  id: number;
  platform: string;
  credential_id?: number;
  preset_metadata?: Record<string, unknown>;
}

export function usePresetDetails(presetIds: number[]): Record<number, PresetDetail> {
  const [presetDetails, setPresetDetails] = useState<Record<number, PresetDetail>>({});
  const fetchedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    const idsToFetch = presetIds.filter((id) => id > 0 && !fetchedRef.current.has(id));
    if (idsToFetch.length === 0) return;
    idsToFetch.forEach((id) => fetchedRef.current.add(id));

    Promise.allSettled(
      idsToFetch.map((pid) => apiClient.get(`/presets/${pid}`).then((r) => r.data as PresetDetail)),
    ).then((results) => {
      const loaded = results
        .filter((r): r is PromiseFulfilledResult<PresetDetail> => r.status === "fulfilled")
        .map((r) => r.value);
      if (loaded.length === 0) return;
      setPresetDetails((prev) => {
        const next = { ...prev };
        loaded.forEach((d) => {
          next[d.id] = d;
        });
        return next;
      });
    });
  }, [presetIds]);

  return presetDetails;
}
