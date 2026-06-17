"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
      setError(extractApiError(err, "Invalid email or password"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-full flex items-center justify-center bg-[#FAFAFA] px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-10">
          <Logo size={48} />
          <p className="text-sm font-semibold tracking-[0.2em] text-[#224C87] mt-5">LEAP</p>
          <p className="text-xs text-gray-400 mt-1.5">Sign in to your account</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-[#D9D9D9] p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <fieldset disabled={loading} className="space-y-4 disabled:opacity-90">
              <div>
                <label htmlFor="login-email" className="block text-sm font-medium text-gray-700 mb-1.5">
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
                  className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] bg-[#FAFAFA] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label htmlFor="login-password" className="block text-sm font-medium text-gray-700 mb-1.5">
                  Password
                </label>
                <PasswordInput
                  id="login-password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] bg-[#FAFAFA] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                  placeholder="••••••••"
                />
              </div>

              {error && (
                <p role="alert" aria-live="polite" className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">
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

        <p className="text-center text-sm text-gray-500 mt-4">
          No account?{" "}
          <Link href="/register" className="text-[#224C87] font-medium hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
