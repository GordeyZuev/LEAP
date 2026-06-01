"use client";

import Link from "next/link";
import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

// Segment-level error boundary for the (app) section. Catches render crashes
// inside the authenticated shell so the sidebar stays put and the user can
// recover without a full page reload.
export default function AppSectionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("(app) error boundary caught:", error);
  }, [error]);

  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="w-full max-w-md rounded-2xl border border-red-100 bg-white p-6 shadow-sm">
        <div className="flex items-start gap-3">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-red-500" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-900">Something went wrong</p>
            <p className="mt-1 text-sm text-gray-500">
              This page failed to render. Retry, or jump back to recordings.
            </p>
            <div className="mt-4 flex gap-2">
              <button
                type="button"
                onClick={reset}
                className="rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1a3d6e]"
              >
                Try again
              </button>
              <Link
                href="/recordings"
                className="rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Recordings
              </Link>
            </div>
            {error.digest && (
              <p className="mt-4 font-mono text-[11px] text-gray-300">ref: {error.digest}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
