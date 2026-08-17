"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiClient } from "@/api/client";
import { PasswordInput } from "@/components/ui/password-input";
import { Logo } from "@/components/layout/logo";
import { ActionButton } from "@/components/ui/action-button";
import { extractApiError } from "@/lib/utils";
import { firstFailedRule, isPasswordValid } from "@/lib/password-rules";
import { PasswordRulesList } from "@/components/ui/password-rules-list";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);

  function set(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  const passwordValid = useMemo(() => isPasswordValid(form.password), [form.password]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    const failed = firstFailedRule(form.password);
    if (failed) {
      setError(failed.label);
      setPasswordTouched(true);
      return;
    }
    setError("");
    setLoading(true);
    try {
      await apiClient.post("/auth/register", form);
      // Verification email is sent by the server — redirect to the
      // "check your inbox" screen instead of logging in directly.
      router.push(`/verify-email-sent?email=${encodeURIComponent(form.email)}`);
    } catch (err: unknown) {
      setError(extractApiError(err, "Registration failed"));
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
          <p className="mt-1.5 max-w-xs text-center text-xs text-muted-foreground">
            Set up recordings once and LEAP handles the rest — trimming, subtitles and publishing.
            We&apos;ll email you a link to confirm your address.
          </p>
        </div>

        <div className="bg-card rounded-2xl shadow-sm border border-border p-8 animate-panel-in">
          <form onSubmit={handleSubmit} className="space-y-4">
            <fieldset disabled={loading} className="space-y-4 disabled:opacity-90">
              <div>
                <label htmlFor="register-name" className="block text-sm font-medium text-secondary-foreground mb-1.5">
                  Full name
                </label>
                <input
                  id="register-name"
                  type="text"
                  required
                  autoComplete="name"
                  autoFocus
                  value={form.full_name}
                  onChange={(e) => set("full_name", e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
                  placeholder="Your name"
                />
              </div>

              <div>
                <label htmlFor="register-email" className="block text-sm font-medium text-secondary-foreground mb-1.5">
                  Email
                </label>
                <input
                  id="register-email"
                  type="email"
                  required
                  autoComplete="email"
                  inputMode="email"
                  value={form.email}
                  onChange={(e) => set("email", e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label htmlFor="register-password" className="block text-sm font-medium text-secondary-foreground mb-1.5">
                  Password
                </label>
                <PasswordInput
                  id="register-password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  aria-describedby="password-rules"
                  value={form.password}
                  onChange={(e) => set("password", e.target.value)}
                  onBlur={() => setPasswordTouched(true)}
                  className="w-full px-4 py-2.5 rounded-xl border border-border bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors"
                  placeholder="••••••••"
                />
                <PasswordRulesList id="password-rules" password={form.password} showErrors={passwordTouched} />
              </div>

              {error && (
                <p role="alert" aria-live="polite" className="text-sm text-red-500 bg-red-50 dark:bg-red-500/10 px-3 py-2 rounded-xl">
                  {error}
                </p>
              )}

              <ActionButton
                type="submit"
                disabled={!passwordValid}
                isPending={loading}
                pendingLabel="Creating account…"
                className="w-full justify-center py-2.5 mt-2"
              >
                Create account
              </ActionButton>
            </fieldset>
          </form>
        </div>

        <p className="text-center text-sm text-muted-foreground mt-4">
          Already have an account?{" "}
          <Link href="/login" className="text-primary font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
