"use client";

import Link from "next/link";
import Image from "next/image";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, Mail, X } from "lucide-react";

import { confirmProductNews, unsubscribeProductNews } from "@/api/product-updates";
import { fetchProductNewsPreferences, INTEREST_OPTIONS, updateProductNewsPreferences, type ProductInterest } from "@/api/product-updates";
import { ActionButton } from "@/components/ui/action-button";
import { PublicThemeButton } from "@/components/ui/theme-toggle";
import { extractApiError } from "@/lib/utils";
import { Footer } from "@/components/layout/footer";

function ActionContent({ action }: { action: "confirm" | "unsubscribe" }) {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const done = Boolean(message);

  async function complete() {
    setPending(true);
    setError("");
    try {
      const result = action === "confirm"
        ? await confirmProductNews(token)
        : await unsubscribeProductNews(token);
      setMessage(result.message);
      window.history.replaceState({}, "", `/updates/${action}`);
    } catch (cause) {
      setError(extractApiError(cause, "This link is invalid or has expired."));
    } finally {
      setPending(false);
    }
  }

  const isConfirm = action === "confirm";
  return (
    <section className="mx-auto max-w-lg rounded-2xl border border-border bg-card p-6 text-center shadow-sm sm:p-8">
      <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        {done ? <Check size={22} /> : isConfirm ? <Mail size={22} /> : <X size={22} />}
      </span>
      <h1 className="mt-4 text-xl font-semibold text-foreground">
        {done ? "All set" : isConfirm ? "Confirm your subscription" : "Unsubscribe from LEAP news"}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        {message || (isConfirm
          ? "Confirm your email address to receive occasional emails about notable LEAP updates."
          : "You will stop receiving product-update emails. This will not affect your LEAP account.")}
      </p>
      {error && <p role="alert" className="mt-4 rounded-xl bg-danger-fg/10 px-3 py-2.5 text-left text-sm text-danger-fg">{error}</p>}
      {!done && token && (
        <div className="mt-6 flex justify-center">
          <ActionButton type="button" onClick={() => void complete()} isPending={pending} pendingLabel="Please wait…">
            {isConfirm ? "Confirm subscription" : "Unsubscribe"}
          </ActionButton>
        </div>
      )}
      {!token && !done && <p role="alert" className="mt-4 text-sm text-danger-fg">The email link is incomplete.</p>}
      <Link href="/updates" className="mt-6 inline-block text-sm font-medium text-primary underline-offset-2 hover:underline">Back to LEAP News</Link>
    </section>
  );
}

export function SubscriptionActionPage({ action }: { action: "confirm" | "unsubscribe" }) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <Link href="/updates" className="flex items-center gap-2 text-sm font-semibold tracking-wider text-primary">
            <Image src="/logo_symb.svg" alt="" width={24} height={24} /> LEAP
          </Link>
          <PublicThemeButton />
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center px-5 py-10">
        <Suspense fallback={<p role="status" className="text-sm text-muted-foreground">Loading…</p>}>
          <ActionContent action={action} />
        </Suspense>
      </main>
      <Footer variant="public" />
    </div>
  );
}

function PreferencesContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const managementToken = useRef(token);
  const [hasManagementToken] = useState(Boolean(token));
  const [interests, setInterests] = useState<ProductInterest[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!token) return;
    window.history.replaceState({}, "", "/updates/preferences");
    void fetchProductNewsPreferences(token).then((value) => {
      setInterests(value);
      setLoaded(true);
    }).catch((cause) => setError(extractApiError(cause, "This subscription link is invalid or no longer active.")));
  }, [token]);

  async function save() {
    if (!interests.length) {
      setError("Choose at least one topic, or unsubscribe using the link in your email.");
      return;
    }
    setPending(true);
    setError("");
    try {
      const result = await updateProductNewsPreferences(managementToken.current, interests);
      setMessage(result.message);
    } catch (cause) {
      setError(extractApiError(cause, "Could not update your topics."));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mx-auto max-w-lg rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
      <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Mail size={22} /></span>
      <h1 className="mt-4 text-center text-xl font-semibold text-foreground">Email topics</h1>
      <p className="mt-2 text-center text-sm leading-relaxed text-muted-foreground">Choose which notable LEAP updates you want to hear about.</p>
      {loaded && <fieldset className="mt-6 space-y-3">
        <legend className="sr-only">Topics</legend>
        {INTEREST_OPTIONS.map((option) => <label key={option.value} className="flex cursor-pointer items-center gap-3 text-sm text-secondary-foreground">
          <input type="checkbox" checked={interests.includes(option.value)} onChange={(event) => {
            setInterests(event.target.checked ? [...interests, option.value] : interests.filter((item) => item !== option.value));
            setMessage("");
            setError("");
          }} className="size-4 accent-primary" />
          {option.label}
        </label>)}
      </fieldset>}
      {!loaded && !error && hasManagementToken && <p role="status" className="mt-6 text-center text-sm text-muted-foreground">Loading your topics…</p>}
      {!hasManagementToken && <p role="alert" className="mt-4 rounded-xl bg-danger-fg/10 px-3 py-2.5 text-sm text-danger-fg">The email link is incomplete.</p>}
      {message && <p role="status" className="mt-4 rounded-xl bg-success-fg/10 px-3 py-2.5 text-sm text-success-fg">{message}</p>}
      {error && <p role="alert" className="mt-4 rounded-xl bg-danger-fg/10 px-3 py-2.5 text-sm text-danger-fg">{error}</p>}
      {loaded && !message && <div className="mt-6 flex justify-center"><ActionButton type="button" onClick={() => void save()} isPending={pending} pendingLabel="Saving…">Save topics</ActionButton></div>}
      <div className="text-center"><Link href="/updates" className="mt-6 inline-block text-sm font-medium text-primary underline-offset-2 hover:underline">Back to LEAP News</Link></div>
    </section>
  );
}

export function SubscriptionPreferencesPage() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-border bg-card"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
        <Link href="/updates" className="flex items-center gap-2 text-sm font-semibold tracking-wider text-primary"><Image src="/logo_symb.svg" alt="" width={24} height={24} /> LEAP</Link><PublicThemeButton />
      </div></header>
      <main className="flex flex-1 items-center justify-center px-5 py-10"><Suspense fallback={<p role="status" className="text-sm text-muted-foreground">Loading…</p>}><PreferencesContent /></Suspense></main>
      <Footer variant="public" />
    </div>
  );
}
