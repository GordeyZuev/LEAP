"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, XCircle } from "lucide-react";
import { apiClient } from "@/api/client";
import { extractApiError } from "@/lib/utils";
import { PasswordInput } from "@/components/ui/password-input";
import { Logo } from "@/components/layout/logo";
import { ActionButton } from "@/components/ui/action-button";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const redirectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-redirect to login after success
  useEffect(() => {
    if (done) {
      redirectTimer.current = setTimeout(() => router.push("/login"), 3000);
    }
    return () => {
      if (redirectTimer.current) clearTimeout(redirectTimer.current);
    };
  }, [done, router]);

  // Token missing — show error immediately
  if (!token) {
    return (
      <div className="text-center">
        <XCircle size={40} className="text-red-400 mx-auto mb-4" strokeWidth={1.5} />
        <h2 className="text-lg font-semibold text-foreground mb-2">Invalid link</h2>
        <p className="text-sm text-muted-foreground mb-4">
          The password reset link is missing a token. Please request a new one.
        </p>
        <Link href="/forgot-password" className="text-sm text-primary font-medium hover:underline">
          Request new link
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="text-center">
        <CheckCircle2 size={40} className="text-green-500 mx-auto mb-4" strokeWidth={1.5} />
        <h2 className="text-lg font-semibold text-foreground mb-2">Password updated!</h2>
        <p className="text-sm text-muted-foreground">
          Your password has been changed. Redirecting to login…
        </p>
      </div>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await apiClient.post("/auth/reset-password", { token, new_password: password });
      setDone(true);
    } catch (err) {
      setError(extractApiError(err, "Invalid or expired reset link"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <fieldset disabled={loading} className="space-y-4 disabled:opacity-90">
        <div>
          <label htmlFor="rp-password" className="block text-sm font-medium text-secondary-foreground mb-1.5">
            New password
          </label>
          <PasswordInput
            id="rp-password"
            required
            autoFocus
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
            placeholder="••••••••"
          />
          <p className="text-xs text-muted-foreground mt-1.5">At least 8 characters, 1 uppercase, 1 digit.</p>
        </div>

        <div>
          <label htmlFor="rp-confirm" className="block text-sm font-medium text-secondary-foreground mb-1.5">
            Confirm new password
          </label>
          <PasswordInput
            id="rp-confirm"
            required
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
            placeholder="••••••••"
          />
        </div>

        {error && (
          <p role="alert" aria-live="polite" className="text-sm text-red-500 bg-red-50 dark:bg-red-500/10 px-3 py-2 rounded-xl">
            {error}
          </p>
        )}

        <ActionButton
          type="submit"
          isPending={loading}
          pendingLabel="Saving…"
          className="w-full justify-center py-2.5 mt-2"
        >
          Set new password
        </ActionButton>
      </fieldset>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-full flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">

        <div className="flex flex-col items-center mb-10">
          <Logo size={48} />
          <p className="text-sm font-semibold tracking-[0.2em] text-primary mt-5">LEAP</p>
          <p className="text-xs text-muted-foreground mt-1.5">Set a new password</p>
        </div>

        <div className="bg-card rounded-2xl shadow-sm border border-border p-8">
          <Suspense fallback={<div className="h-40" />}>
            <ResetPasswordForm />
          </Suspense>
        </div>

        <div className="flex justify-center mt-5">
          <Link
            href="/login"
            className="text-sm text-muted-foreground hover:text-primary transition-colors"
          >
            Back to login
          </Link>
        </div>

      </div>
    </div>
  );
}
