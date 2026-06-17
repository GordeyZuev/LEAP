"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check } from "lucide-react";
import { apiClient } from "@/api/client";
import { PasswordInput } from "@/components/ui/password-input";
import { Logo } from "@/components/layout/logo";
import { ActionButton } from "@/components/ui/action-button";
import { cn, extractApiError } from "@/lib/utils";

interface PasswordRule {
  id: string;
  label: string;
  test: (pw: string) => boolean;
}

const PASSWORD_RULES: PasswordRule[] = [
  { id: "len",   label: "At least 8 characters", test: (pw) => pw.length >= 8 },
  { id: "digit", label: "Contains a digit",      test: (pw) => /\d/.test(pw) },
  { id: "upper", label: "Contains an uppercase letter", test: (pw) => /[A-Z]/.test(pw) },
];

function firstFailedRule(pw: string): PasswordRule | null {
  return PASSWORD_RULES.find((r) => !r.test(pw)) ?? null;
}

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);

  function set(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  const ruleStates = useMemo(
    () => PASSWORD_RULES.map((r) => ({ ...r, ok: r.test(form.password) })),
    [form.password],
  );
  const passwordValid = ruleStates.every((r) => r.ok);

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
      // Server sets session cookies on the login response.
      await apiClient.post("/auth/login", {
        email: form.email,
        password: form.password,
      });
      router.push("/recordings");
    } catch (err: unknown) {
      setError(extractApiError(err, "Registration failed"));
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
          <p className="text-xs text-gray-400 mt-1.5">Create your account</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-[#D9D9D9] p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <fieldset disabled={loading} className="space-y-4 disabled:opacity-90">
              <div>
                <label htmlFor="register-name" className="block text-sm font-medium text-gray-700 mb-1.5">
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
                  className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] bg-[#FAFAFA] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                  placeholder="Your name"
                />
              </div>

              <div>
                <label htmlFor="register-email" className="block text-sm font-medium text-gray-700 mb-1.5">
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
                  className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] bg-[#FAFAFA] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label htmlFor="register-password" className="block text-sm font-medium text-gray-700 mb-1.5">
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
                  className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] bg-[#FAFAFA] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                  placeholder="••••••••"
                />
                <ul id="password-rules" className="mt-2 space-y-1">
                  {ruleStates.map((r) => {
                    const showFail = (passwordTouched || form.password.length > 0) && !r.ok;
                    return (
                      <li
                        key={r.id}
                        className={cn(
                          "flex items-center gap-1.5 text-[11px] transition-colors",
                          r.ok ? "text-green-600" : showFail ? "text-red-500" : "text-gray-400",
                        )}
                      >
                        <Check
                          size={11}
                          className={cn(
                            "shrink-0 transition-opacity",
                            r.ok ? "opacity-100" : "opacity-30",
                          )}
                        />
                        {r.label}
                      </li>
                    );
                  })}
                </ul>
              </div>

              {error && (
                <p role="alert" aria-live="polite" className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">
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

        <p className="text-center text-sm text-gray-500 mt-4">
          Already have an account?{" "}
          <Link href="/login" className="text-[#224C87] font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
