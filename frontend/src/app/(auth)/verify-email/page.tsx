"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { apiClient } from "@/api/client";
import { Logo } from "@/components/layout/logo";
import { ActionButton } from "@/components/ui/action-button";

type State = "verifying" | "success" | "error";

export default function VerifyEmailPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [state, setState] = useState<State>(() => (token ? "verifying" : "error"));
  const [errorMsg, setErrorMsg] = useState(() =>
    token ? "" : "No verification token found. Please use the link from your email.",
  );
  const calledRef = useRef(false);

  useEffect(() => {
    if (!token || calledRef.current) return;
    calledRef.current = true;

    apiClient
      .post("/auth/verify-email", { token })
      .then(() => {
        setState("success");
        // Auto-redirect to login after 3 s so user can read the success message.
        setTimeout(() => router.push("/login"), 3000);
      })
      .catch(() => {
        setErrorMsg(
          "This verification link is invalid or has expired. Please request a new one.",
        );
        setState("error");
      });
  }, [token, router]);

  return (
    <div className="min-h-full flex items-center justify-center bg-[#FAFAFA] px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex flex-col items-center mb-10">
          <Logo size={48} />
          <p className="text-sm font-semibold tracking-[0.2em] text-[#224C87] mt-5">LEAP</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-[#D9D9D9] p-8 text-center">

          {/* Verifying */}
          {state === "verifying" && (
            <>
              <div className="flex justify-center mb-5">
                <Loader2 size={40} className="text-[#224C87] animate-spin" strokeWidth={1.5} />
              </div>
              <h1 className="text-xl font-semibold text-gray-900 mb-2">Verifying your email…</h1>
              <p className="text-sm text-gray-500">Just a moment, please.</p>
            </>
          )}

          {/* Success */}
          {state === "success" && (
            <>
              <div className="flex justify-center mb-5">
                <div className="w-16 h-16 rounded-full bg-green-50 flex items-center justify-center">
                  <CheckCircle2 size={36} className="text-green-500" strokeWidth={1.5} />
                </div>
              </div>
              <h1 className="text-xl font-semibold text-gray-900 mb-2">Email verified!</h1>
              <p className="text-sm text-gray-500 mb-7 leading-relaxed">
                Your account is now active. Redirecting you to the login page…
              </p>
              <ActionButton
                onClick={() => router.push("/login")}
                className="w-full justify-center py-2.5"
              >
                Go to login
              </ActionButton>
            </>
          )}

          {/* Error */}
          {state === "error" && (
            <>
              <div className="flex justify-center mb-5">
                <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center">
                  <XCircle size={36} className="text-red-400" strokeWidth={1.5} />
                </div>
              </div>
              <h1 className="text-xl font-semibold text-gray-900 mb-2">Link invalid</h1>
              <p className="text-sm text-gray-500 mb-7 leading-relaxed">{errorMsg}</p>
              <Link href="/login">
                <ActionButton className="w-full justify-center py-2.5">
                  Back to login
                </ActionButton>
              </Link>
            </>
          )}

        </div>

        {/* Resend link — only shown on error */}
        {state === "error" && (
          <p className="text-center text-sm text-gray-500 mt-4">
            Need a new link?{" "}
            <Link href="/login" className="text-[#224C87] font-medium hover:underline">
              Sign in to resend
            </Link>
          </p>
        )}

      </div>
    </div>
  );
}
