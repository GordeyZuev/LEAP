"use client";

import { useState } from "react";
import { ArrowDownToLine, Loader2, Video } from "lucide-react";

import { cn } from "@/lib/utils";
import { ARTEFACT_ROW, ARTEFACT_ROW_DEFAULT } from "@/components/recordings/artefact-list";

export function ShareVideoDownloadButton({
  download,
}: {
  download: () => Promise<{ url: string }>;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function handleDownload() {
    setLoading(true);
    setError(false);
    try {
      const res = await download();
      const a = document.createElement("a");
      a.href = res.url;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleDownload}
      disabled={loading}
      aria-label={error ? "Download failed — retry" : "Download video"}
      className={cn(
        ARTEFACT_ROW,
        error
          ? "border-danger-fg/40 bg-danger-fg/10 text-danger-fg hover:bg-danger-fg/15"
          : ARTEFACT_ROW_DEFAULT,
        "disabled:opacity-50",
      )}
    >
      {loading ? <Loader2 size={13} className="shrink-0 animate-spin" /> : <Video size={13} className="shrink-0" />}
      <span className="flex-1 text-left">{error ? "Download failed — retry" : "Video"}</span>
      {!error && (
        <span className="shrink-0 text-[10px] font-semibold uppercase text-muted-foreground">mp4</span>
      )}
      <ArrowDownToLine size={11} className={cn("shrink-0", error ? undefined : "text-muted-foreground")} />
    </button>
  );
}
