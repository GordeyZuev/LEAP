"use client";

import { useState } from "react";
import { Check, Mail, MessageSquareText } from "lucide-react";

import {
  INTEREST_OPTIONS,
  submitProductFeedback,
  subscribeProductNews,
  type FeedbackKind,
  type ProductInterest,
} from "@/api/product-updates";
import { ActionButton } from "@/components/ui/action-button";
import { NativeSelect } from "@/components/ui/native-select";
import { extractApiError } from "@/lib/utils";

const INPUT_CLASS = "w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 aria-invalid:border-danger-fg/50 aria-invalid:focus-visible:ring-danger-fg/30";
const KIND_OPTIONS: { value: FeedbackKind; label: string }[] = [
  { value: "idea", label: "Idea" },
  { value: "problem", label: "Problem" },
  { value: "question", label: "Question" },
  { value: "other", label: "Something else" },
];

function FormNotice({ tone, children }: { tone: "error" | "success"; children: React.ReactNode }) {
  const colors = tone === "error"
    ? "border-danger-fg/20 bg-danger-fg/[0.04] text-danger-fg"
    : "border-success-fg/20 bg-success-fg/[0.04] text-success-fg";
  return <div role={tone === "error" ? "alert" : "status"} className={`rounded-xl border px-3.5 py-3 text-sm ${colors}`}>{children}</div>;
}

function InterestChoices({ value, onChange }: {
  value: ProductInterest[];
  onChange: (next: ProductInterest[]) => void;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="mb-2 text-sm font-medium text-foreground">What do you use LEAP for?</legend>
      {INTEREST_OPTIONS.map((option) => (
        <label key={option.value} className="flex cursor-pointer items-center gap-2.5 text-sm text-secondary-foreground">
          <input
            type="checkbox"
            checked={value.includes(option.value)}
            onChange={(event) => onChange(
              event.target.checked
                ? [...value, option.value]
                : value.filter((item) => item !== option.value),
            )}
            className="size-4 rounded border-border accent-primary"
          />
          {option.label}
        </label>
      ))}
    </fieldset>
  );
}

export function SubscribeForm() {
  const [email, setEmail] = useState("");
  const [interests, setInterests] = useState<ProductInterest[]>(INTEREST_OPTIONS.map((item) => item.value));
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setError("");
    if (!interests.length) {
      setError("Choose at least one topic.");
      return;
    }
    setPending(true);
    try {
      await subscribeProductNews(email, interests);
      setMessage("Check your inbox to confirm your subscription.");
      setEmail("");
    } catch (cause) {
      setError(extractApiError(cause, "Could not start the subscription. Please try again."));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="mx-auto max-w-xl space-y-5 rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-7">
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-foreground">Email address</span>
        <input required type="email" maxLength={320} autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className={INPUT_CLASS} placeholder="you@example.com" />
      </label>
      <InterestChoices value={interests} onChange={setInterests} />
      <p className="text-xs leading-relaxed text-muted-foreground">Confirm by email. Change topics or unsubscribe at any time.</p>
      {message && <FormNotice tone="success">{message}</FormNotice>}
      {error && <FormNotice tone="error">{error}</FormNotice>}
      <ActionButton type="submit" isPending={pending} pendingLabel="Sending…" icon={<Mail size={16} />}>Subscribe</ActionButton>
    </form>
  );
}

export function FeedbackForm() {
  const [interests, setInterests] = useState<ProductInterest[]>([]);
  const [kind, setKind] = useState<FeedbackKind>("idea");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const messageInvalid = error === "Please enter a message of at least 10 characters.";
  const replyEmailInvalid = error === "Enter a valid reply email address, or leave the field blank.";

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const cleanMessage = message.trim();
    if (!interests.length) {
      setError("Choose at least one way you use LEAP.");
      return;
    }
    if (cleanMessage.length < 10) {
      setError("Please enter a message of at least 10 characters.");
      return;
    }
    const replyEmailInput = event.currentTarget.elements.namedItem("replyEmail") as HTMLInputElement;
    if (email.trim() && !replyEmailInput.validity.valid) {
      setError("Enter a valid reply email address, or leave the field blank.");
      return;
    }
    setPending(true);
    try {
      await submitProductFeedback({ interests, kind, message: cleanMessage, reply_email: email.trim() || null });
      setSent(true);
      setMessage("");
      setEmail("");
    } catch (cause) {
      setError(extractApiError(cause, "Could not send your feedback. Please try again."));
    } finally {
      setPending(false);
    }
  }

  if (sent) {
    return (
      <div role="status" className="mx-auto flex max-w-xl items-start gap-3 rounded-2xl border border-border bg-card p-5 text-sm text-success-fg shadow-sm sm:p-7">
        <Check size={18} className="mt-0.5 shrink-0" />
        <div><p className="font-medium">Thank you for your feedback.</p><button type="button" onClick={() => setSent(false)} className="mt-1 underline underline-offset-2">Send another note</button></div>
      </div>
    );
  }

  return (
    <form noValidate onSubmit={(event) => void submit(event)} className="mx-auto max-w-xl space-y-5 rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-7">
      <InterestChoices value={interests} onChange={setInterests} />
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-foreground">Type of feedback</span>
        <NativeSelect value={kind} onChange={(event) => setKind(event.target.value as FeedbackKind)} className={INPUT_CLASS}>
          {KIND_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </NativeSelect>
      </label>
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-foreground">Your message</span>
        <textarea maxLength={5000} rows={5} value={message} onChange={(event) => setMessage(event.target.value)} aria-invalid={messageInvalid} className={`${INPUT_CLASS} resize-y`} placeholder="What were you trying to do? What would help?" />
      </label>
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-foreground">Email for a reply <span className="font-normal text-muted-foreground">(optional)</span></span>
        <input name="replyEmail" type="email" maxLength={320} autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} aria-invalid={replyEmailInvalid} className={INPUT_CLASS} placeholder="you@example.com" />
      </label>
      {error && <FormNotice tone="error">{error}</FormNotice>}
      <ActionButton type="submit" isPending={pending} pendingLabel="Sending…" icon={<MessageSquareText size={16} />}>Send feedback</ActionButton>
    </form>
  );
}
