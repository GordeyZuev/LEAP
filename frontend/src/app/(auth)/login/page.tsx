"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import axios from "axios";
import { apiClient } from "@/api/client";
import { extractApiError } from "@/lib/utils";
import { PasswordInput } from "@/components/ui/password-input";
import { Logo } from "@/components/layout/logo";
import { ActionButton } from "@/components/ui/action-button";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError("");
    setLoading(true);
    try {
      // Server sets httpOnly session cookies + CSRF cookie on the response.
      // We don't read or store any tokens client-side.
      await apiClient.post("/auth/login", { email, password });
      router.push("/recordings");
    } catch (err: unknown) {
      // 403 "Email not verified" → send the user to the check-your-inbox screen
      // so they can resend the verification link from there.
      if (axios.isAxiosError(err) && err.response?.status === 403) {
        const detail: string = err.response.data?.detail ?? "";
        if (detail.toLowerCase().includes("not verified")) {
          router.push(`/verify-email-sent?email=${encodeURIComponent(email)}`);
          return;
        }
      }
      setError(extractApiError(err, "Invalid email or password"));
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
          <p className="text-xs text-muted-foreground mt-1.5">Sign in to your account</p>
        </div>

        <div className="bg-card rounded-2xl shadow-sm border border-border p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <fieldset disabled={loading} className="space-y-4 disabled:opacity-90">
              <div>
                <label htmlFor="login-email" className="block text-sm font-medium text-secondary-foreground mb-1.5">
                  Email
                </label>
                <input
                  id="login-email"
                  type="email"
                  required
                  autoComplete="email"
                  inputMode="email"
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label htmlFor="login-password" className="block text-sm font-medium text-secondary-foreground mb-1.5">
                  Password
                </label>
                <PasswordInput
                  id="login-password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
                  placeholder="••••••••"
                />
              </div>

              <div className="flex justify-end -mt-1">
                <Link href="/forgot-password" className="text-xs text-muted-foreground hover:text-primary transition-colors">
                  Forgot password?
                </Link>
              </div>

              {error && (
                <p role="alert" aria-live="polite" className="text-sm text-red-500 bg-red-50 dark:bg-red-500/10 px-3 py-2 rounded-xl">
                  {error}
                </p>
              )}

              <ActionButton
                type="submit"
                isPending={loading}
                pendingLabel="Signing in…"
                className="w-full justify-center py-2.5 mt-2"
              >
                Sign in
              </ActionButton>
            </fieldset>
          </form>
        </div>

        <p className="text-center text-sm text-muted-foreground mt-4">
          No account?{" "}
          <Link href="/register" className="text-primary font-medium hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
