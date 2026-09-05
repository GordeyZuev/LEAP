"use client";

import { useState } from "react";
import { ArrowDownToLine, Loader2, Video } from "lucide-react";

import { cn } from "@/lib/utils";

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
      className={cn(
        "flex w-full items-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-medium transition-colors disabled:opacity-50",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
        error
          ? "border-danger-fg/40 bg-danger-fg/10 text-danger-fg hover:bg-danger-fg/15"
          : "border-primary/30 bg-primary/5 text-primary hover:bg-primary/10",
      )}
    >
      {loading ? <Loader2 size={13} className="animate-spin" /> : <Video size={13} />}
      <span className="flex-1 text-left">{error ? "Download failed — retry" : "Download video"}</span>
      <ArrowDownToLine size={11} className="shrink-0" />
    </button>
  );
}
