"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Mail } from "lucide-react";
import { apiClient } from "@/api/client";
import { Logo } from "@/components/layout/logo";
import { ActionButton } from "@/components/ui/action-button";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError("");
    setLoading(true);
    try {
      await apiClient.post("/auth/forgot-password", { email });
      // Always show the "check your email" state — server is anti-enumeration.
      setSent(true);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-full flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">

        <div className="flex flex-col items-center mb-10">
          <Logo size={48} />
          <p className="text-sm font-semibold tracking-[0.2em] text-primary mt-5">LEAP</p>
          <p className="text-xs text-muted-foreground mt-1.5">Password recovery</p>
        </div>

        <div className="bg-card rounded-2xl shadow-sm border border-border p-8">
          {!sent ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-sm text-muted-foreground leading-relaxed mb-2">
                Enter the email address you registered with and we&apos;ll send you a link to reset your password.
              </p>

              <fieldset disabled={loading} className="space-y-4 disabled:opacity-90">
                <div>
                  <label htmlFor="forgot-email" className="block text-sm font-medium text-secondary-foreground mb-1.5">
                    Email
                  </label>
                  <input
                    id="forgot-email"
                    type="email"
                    required
                    autoFocus
                    autoComplete="email"
                    inputMode="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
                    placeholder="you@example.com"
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
                  pendingLabel="Sending…"
                  className="w-full justify-center py-2.5 mt-2"
                >
                  Send reset link
                </ActionButton>
              </fieldset>
            </form>
          ) : (
            /* Success state */
            <div className="text-center">
              <div className="flex justify-center mb-5">
                <div className="w-14 h-14 rounded-full bg-primary/8 flex items-center justify-center">
                  <Mail size={28} className="text-primary" strokeWidth={1.5} />
                </div>
              </div>
              <h2 className="text-lg font-semibold text-foreground mb-2">Check your email</h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                If <span className="font-medium text-secondary-foreground">{email}</span> is registered,
                you&apos;ll receive a password reset link shortly.
              </p>
              <p className="text-xs text-muted-foreground mt-3">
                Don&apos;t see it? Check your spam folder.
              </p>
            </div>
          )}
        </div>

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
