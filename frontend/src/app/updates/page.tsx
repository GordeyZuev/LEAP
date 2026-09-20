"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState, useSyncExternalStore } from "react";
import { ArrowRight, ChevronDown, Mail, MessageSquareText, Sparkles } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { fetchProductUpdates, type ProductUpdate } from "@/api/product-updates";
import { PublicThemeButton } from "@/components/ui/theme-toggle";
import { Footer } from "@/components/layout/footer";
import { markProductNewsSeen } from "@/lib/product-news-storage";
import { extractApiError, formatDate } from "@/lib/utils";
import { hasSessionCookie } from "@/lib/auth";

const subscribeToSessionCookie = () => () => {};
const VISIBLE_UPDATE_COUNT = 5;

function UpdateCard({ update }: { update: ProductUpdate }) {
  const hasReleaseNotes = update.audience_bullets.length > 0 || update.creator_bullets.length > 0;

  return (
    <article id={update.id} className="scroll-mt-6 rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {update.version && <span className="rounded-full bg-primary/10 px-2.5 py-1 font-medium text-primary">v{update.version}</span>}
        {update.release_date && <time dateTime={update.release_date}>{formatDate(`${update.release_date}T12:00:00Z`)}</time>}
      </div>
      <h2 className="mt-3 text-lg font-semibold text-foreground">{update.title}</h2>
      <p className="mt-3 text-sm leading-relaxed text-secondary-foreground">{update.summary}</p>
      {hasReleaseNotes && (
        <details className="group mt-4 border-t border-border pt-3">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-primary">
            <span>Release notes</span>
            <ChevronDown size={16} className="transition-transform group-open:rotate-180" />
          </summary>
          <div className="mt-4 grid gap-5 sm:grid-cols-2">
            {update.audience_bullets.length > 0 && (
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">For Audience</h3>
                <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-relaxed text-secondary-foreground">
                  {update.audience_bullets.map((bullet, index) => <li key={index}>{bullet}</li>)}
                </ul>
              </section>
            )}
            {update.creator_bullets.length > 0 && (
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">For Creators</h3>
                <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-relaxed text-secondary-foreground">
                  {update.creator_bullets.map((bullet, index) => <li key={index}>{bullet}</li>)}
                </ul>
              </section>
            )}
          </div>
        </details>
      )}
    </article>
  );
}

export default function UpdatesPage() {
  const query = useQuery({ queryKey: ["product-updates", "archive"], queryFn: () => fetchProductUpdates(200), staleTime: 5 * 60_000 });
  const isSignedIn = useSyncExternalStore(subscribeToSessionCookie, hasSessionCookie, () => false);
  const [showAll, setShowAll] = useState(false);
  const updates = query.data ?? [];
  const latest = updates[0];
  const firstUpdates = updates.slice(0, VISIBLE_UPDATE_COUNT);
  const olderUpdates = updates.slice(VISIBLE_UPDATE_COUNT);

  useEffect(() => {
    if (latest) markProductNewsSeen(latest.id);
  }, [latest]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <Link href={isSignedIn ? "/home" : "/"} className="flex items-center gap-2 text-sm font-semibold tracking-wider text-primary">
            <Image src="/logo_symb.svg" alt="" width={24} height={24} /> LEAP
          </Link>
          {isSignedIn && <Link href="/home" className="mr-auto ml-5 text-xs font-medium text-muted-foreground hover:text-primary">Back to LEAP</Link>}
          <PublicThemeButton />
        </div>
      </header>

      <main id="top" className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
        <div className="mb-8 flex items-center gap-3">
          <span className="flex size-11 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Sparkles size={21} /></span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">News &amp; Release Notes from LEAP</h1>
          </div>
        </div>

        <div className="mb-8 grid gap-3 sm:grid-cols-2">
          <Link href="/updates/subscribe" className="group flex items-center gap-3 rounded-2xl border border-border bg-card p-4 transition-colors hover:border-primary/35 hover:bg-primary/[0.03]">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><Mail size={18} /></span>
            <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-foreground">Email updates</span><span className="mt-0.5 block text-xs text-muted-foreground">Occasional notes about major changes.</span></span>
            <ArrowRight size={16} className="text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
          </Link>
          <Link href="/updates/feedback" className="group flex items-center gap-3 rounded-2xl border border-border bg-card p-4 transition-colors hover:border-primary/35 hover:bg-primary/[0.03]">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><MessageSquareText size={18} /></span>
            <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-foreground">Share feedback</span><span className="mt-0.5 block text-xs text-muted-foreground">Tell us what would make LEAP better.</span></span>
            <ArrowRight size={16} className="text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
          </Link>
        </div>

        <section aria-label="Product updates" className="space-y-4">
          {query.isPending && <div role="status" className="rounded-2xl border border-border bg-card p-6 text-sm text-muted-foreground">Loading updates…</div>}
          {query.isError && <div role="alert" className="rounded-2xl border border-danger-fg/30 bg-card p-6 text-sm text-danger-fg">{extractApiError(query.error, "Could not load product updates. Refresh the page to try again.")}</div>}
          {query.data?.length === 0 && <div className="rounded-2xl border border-border bg-card p-6 text-sm text-muted-foreground">No product updates yet.</div>}
          {firstUpdates.map((update) => <UpdateCard key={update.id} update={update} />)}
          {olderUpdates.length > 0 && (
            <>
              <div
                className={`space-y-4 overflow-hidden transition-[max-height] duration-500 ease-in-out ${showAll ? "max-h-[10000px]" : "max-h-80"}`}
                style={!showAll ? { maskImage: "linear-gradient(to bottom, black 55%, transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom, black 55%, transparent 100%)" } : undefined}
                aria-hidden={!showAll}
                inert={!showAll}
                id="older-updates"
              >
                {olderUpdates.map((update) => <UpdateCard key={update.id} update={update} />)}
              </div>
              <button
                type="button"
                onClick={() => setShowAll((value) => !value)}
                aria-expanded={showAll}
                aria-controls="older-updates"
                className="mx-auto flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-secondary-foreground transition-colors hover:border-primary/35 hover:text-primary"
              >
                {showAll ? "Show fewer updates" : `Show all ${updates.length} updates`}
                <ChevronDown size={15} className={`transition-transform ${showAll ? "rotate-180" : ""}`} />
              </button>
            </>
          )}
        </section>
        {latest && <p className="mt-8 text-center text-xs text-muted-foreground"><Link href="#top" className="inline-flex items-center gap-1 hover:text-primary">Back to top <ArrowRight size={12} className="-rotate-90" /></Link></p>}
      </main>
      <Footer variant="public" />
    </div>
  );
}
