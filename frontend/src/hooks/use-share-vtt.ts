"use client";

import { useEffect, useState } from "react";

import { parseVtt, type TranscriptCue } from "@/components/recordings/transcript-panel";

async function fetchVttText(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(String(res.status));
  return res.text();
}

export function useShareVtt({
  enabled,
  vttUrl,
  fallbackUrl,
}: {
  enabled: boolean;
  vttUrl: string | null | undefined;
  fallbackUrl: string | null;
}) {
  const primary = vttUrl || fallbackUrl || null;
  const requestKey = enabled && primary ? primary : null;
  const loadKey = requestKey === null ? null : `${requestKey}\n${fallbackUrl ?? ""}`;
  const [loaded, setLoaded] = useState<{
    key: string;
    blobUrl: string | null;
    transcript: TranscriptCue[];
  } | null>(null);

  useEffect(() => {
    if (!requestKey || !loadKey) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    const run = async () => {
      let text: string;
      try {
        text = await fetchVttText(requestKey);
      } catch {
        if (!fallbackUrl || requestKey === fallbackUrl) throw new Error("vtt");
        text = await fetchVttText(fallbackUrl);
      }
      if (cancelled) return;
      objectUrl = URL.createObjectURL(new Blob([text], { type: "text/vtt" }));
      setLoaded({ key: loadKey, blobUrl: objectUrl, transcript: parseVtt(text) });
    };
    void run().catch(() => {
      if (!cancelled) {
        setLoaded({ key: loadKey, blobUrl: null, transcript: [] });
      }
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setLoaded((prev) => (prev?.key === loadKey ? null : prev));
    };
  }, [requestKey, loadKey, fallbackUrl]);

  if (!loaded || loaded.key !== loadKey) {
    return { vttBlobUrl: null, transcript: [] };
  }
  return { vttBlobUrl: loaded.blobUrl, transcript: loaded.transcript };
}
