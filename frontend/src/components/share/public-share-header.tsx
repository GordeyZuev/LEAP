"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";

import { AgeRatingBadge } from "@/components/ui/age-rating-badge";
import { PublicThemeButton } from "@/components/ui/theme-toggle";
import { cn } from "@/lib/utils";
import { fetchLatestProductUpdate } from "@/api/product-updates";
import { hasSeenProductNews, markProductNewsSeen } from "@/lib/product-news-storage";

export const PUBLIC_PAGE_SHELL = "mx-auto w-full max-w-[110rem] px-4 sm:px-6 lg:px-8";
export const PUBLIC_PAGE_MAIN = cn(PUBLIC_PAGE_SHELL, "py-4 sm:py-8");
export const PUBLIC_PAGE_HEADER_INNER = cn(
  PUBLIC_PAGE_SHELL,
  "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3 sm:py-4",
);

export const COPY_LINK_CHIP =
  "pressable flex min-h-9 items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";
export const COPY_LINK_CHIP_COPIED = "border-success-fg/40 bg-success-fg/10 text-success-fg";
export const COPY_LINK_CHIP_IDLE =
  "border-border bg-card text-secondary-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-primary";

/**
 * Public share chrome: LEAP mark, 12+, optional context, theme, Copy link.
 * Same shell as recording, playlist, and channel watch.
 */
export function PublicShareHeader({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const newsQuery = useQuery({ queryKey: ["product-updates", "latest"], queryFn: fetchLatestProductUpdate, staleTime: 5 * 60_000 });
  const latestNews = newsQuery.data;
  const newsUnread = Boolean(latestNews && !hasSeenProductNews(latestNews.id));

  useEffect(
    () => () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    },
    [],
  );

  async function onCopy() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete("from");
      await navigator.clipboard.writeText(url.toString());
    } catch {
      return;
    }
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), 2000);
  }

  return (
    <header className="border-b border-border bg-card">
      <div className={PUBLIC_PAGE_HEADER_INNER}>
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex shrink-0 items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo_symb.svg" alt="" aria-hidden="true" className="h-6 w-6" />
            <span className="text-sm font-semibold text-foreground">LEAP</span>
          </span>
          <AgeRatingBadge />
          {children}
        </div>
        <div className="flex items-center gap-2">
          {latestNews && (
            <Link
              href={`/updates#${latestNews.id}`}
              target="_blank"
              rel="noreferrer"
              onClick={() => markProductNewsSeen(latestNews.id)}
              aria-label={newsUnread ? "News & Updates, new release" : "News & Updates"}
              title="News & Updates from LEAP"
              className={cn(
                COPY_LINK_CHIP,
                "max-w-[38vw] sm:max-w-[18rem]",
                "mr-2",
                "border-primary/15 bg-primary/[0.045] text-secondary-foreground hover:border-primary/30 hover:bg-primary/[0.08]",
              )}
            >
              <span className="shrink-0 text-xs font-semibold text-primary">News &amp; Updates</span>
              {newsUnread && <span className="size-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />}
            </Link>
          )}
          <PublicThemeButton />
          <button
            type="button"
            suppressHydrationWarning
            onClick={() => void onCopy()}
            className={cn(COPY_LINK_CHIP, copied ? COPY_LINK_CHIP_COPIED : COPY_LINK_CHIP_IDLE)}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? "Copied" : "Copy link"}
          </button>
      </div>
      </div>
      <span role="status" className="sr-only">
        {copied ? "Link copied to clipboard" : ""}
      </span>
    </header>
  );
}
