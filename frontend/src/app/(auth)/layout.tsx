"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useSession } from "@/hooks/use-session";

// Redirects an already-authenticated user away from /login and /register so
// they can't accidentally re-login and rotate their tokens.
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const status = useSession();

  useEffect(() => {
    if (status === "authenticated") router.replace("/recordings");
  }, [status, router]);

  if (status === "checking" || status === "authenticated") {
    return <div className="min-h-full bg-background" aria-hidden="true" />;
  }
  return <>{children}</>;
}
