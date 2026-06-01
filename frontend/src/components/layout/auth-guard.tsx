"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useSession } from "@/hooks/use-session";

// Gates the (app) section on an authenticated session. Renders a placeholder
// until session status is known so protected pages never paint before redirect.
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const status = useSession();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return <div className="flex h-full items-center justify-center bg-[#FAFAFA]" aria-hidden="true" />;
  }
  return <>{children}</>;
}
