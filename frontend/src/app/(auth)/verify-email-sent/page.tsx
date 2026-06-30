"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Mail, ArrowLeft, RotateCcw } from "lucide-react";
import { apiClient } from "@/api/client";
import { extractApiError } from "@/lib/utils";
import { Logo } from "@/components/layout/logo";
import { ActionButton } from "@/components/ui/action-button";

const COOLDOWN_SEC = 60;

export default function VerifyEmailSentPage() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email") ?? "";

  const [cooldown, setCooldown] = useState(0);
  const [resending, setResending] = useState(false);
  const [resendError, setResendError] = useState("");
  const [resendSuccess, setResendSuccess] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Start cooldown right away — we just sent an email on registration.
  useEffect(() => {
    startCooldown();
    return () => clearTimer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startCooldown() {
    clearTimer();
    setCooldown(COOLDOWN_SEC);
    timerRef.current = setInterval(() => {
      setCooldown((prev) => {
        if (prev <= 1) {
          clearTimer();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  function clearTimer() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  async function handleResend() {
    if (resending || cooldown > 0 || !email) return;
    setResendError("");
    setResendSuccess(false);
    setResending(true);
    try {
      await apiClient.post("/auth/resend-verification", { email });
      setResendSuccess(true);
      startCooldown();
    } catch (err: unknown) {
      setResendError(extractApiError(err, "Failed to resend. Please try again later."));
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="min-h-full flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex flex-col items-center mb-10">
          <Logo size={48} />
          <p className="text-sm font-semibold tracking-[0.2em] text-primary mt-5">LEAP</p>
        </div>

        {/* Card */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-8 text-center">

          {/* Icon */}
          <div className="flex justify-center mb-5">
            <div className="w-16 h-16 rounded-full bg-primary/8 flex items-center justify-center">
              <Mail size={32} className="text-primary" strokeWidth={1.5} />
            </div>
          </div>

          {/* Heading */}
          <h1 className="text-xl font-semibold text-foreground mb-2">
            Check your email
          </h1>
          <p className="text-sm text-muted-foreground mb-5 leading-relaxed">
            We sent a verification link to
          </p>

          {/* Email highlight */}
          {email && (
            <div className="bg-accent rounded-xl px-4 py-2.5 mb-6 inline-block w-full">
              <span className="text-sm font-medium text-primary break-all">{email}</span>
            </div>
          )}

          <p className="text-sm text-muted-foreground mb-7 leading-relaxed">
            Click the link in the email to activate your account.
            <br />
            <span className="text-muted-foreground text-xs mt-1 block">
              Don&apos;t see it? Check your spam folder.
            </span>
          </p>

          {/* Resend feedback */}
          {resendSuccess && (
            <p className="text-sm text-green-600 bg-green-50 dark:bg-green-500/10 rounded-xl px-3 py-2 mb-4">
              New link sent! Check your inbox.
            </p>
          )}
          {resendError && (
            <p role="alert" aria-live="polite" className="text-sm text-red-500 bg-red-50 dark:bg-red-500/10 rounded-xl px-3 py-2 mb-4">
              {resendError}
            </p>
          )}

          {/* Resend button */}
          <ActionButton
            variant="secondary"
            onClick={handleResend}
            isPending={resending}
            disabled={cooldown > 0}
            pendingLabel="Sending…"
            className="w-full justify-center py-2.5"
          >
            <RotateCcw size={14} />
            {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend email"}
          </ActionButton>
        </div>

        {/* Back link */}
        <div className="flex justify-center mt-5">
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors"
          >
            <ArrowLeft size={14} />
            Back to login
          </Link>
        </div>

      </div>
    </div>
  );
}
