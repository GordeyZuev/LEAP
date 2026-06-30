"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Logo } from "@/components/layout/logo";

// Root error boundary. Catches render-time crashes anywhere below the root
// layout that aren't caught by a more specific (segment-level) error.tsx.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Root error boundary caught:", error);
  }, [error]);

  return (
    <div className="flex min-h-full items-center justify-center bg-background px-4">
      <div className="flex w-full max-w-md flex-col items-center text-center">
        <Logo size={40} />
        <p className="mt-8 text-lg font-semibold text-foreground">Something went wrong</p>
        <p className="mt-2 text-sm text-muted-foreground">
          The app hit an unexpected error. You can retry, or go back to the recordings list.
        </p>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={reset}
            className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
          >
            Try again
          </button>
          <Link
            href="/recordings"
            className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-medium text-secondary-foreground transition-colors hover:bg-muted"
          >
            Go home
          </Link>
        </div>
        {error.digest && (
          <p className="mt-6 font-mono text-[11px] text-gray-300">ref: {error.digest}</p>
        )}
      </div>
    </div>
  );
}
