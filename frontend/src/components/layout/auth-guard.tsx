"use client";

import { useEffect } from "react";

import { useRouter } from "next/navigation";

import { hasSessionCookie } from "@/lib/auth";
import { useMe } from "@/lib/react-query";

// Gates the (app) section. With a session cookie we paint the shell immediately
// and let /users/me confirm in the background — unlike useSession on /login.
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const hasCookie = hasSessionCookie();
  const { isError } = useMe({ enabled: hasCookie });

  useEffect(() => {
    if (!hasCookie || isError) router.replace("/login");
  }, [hasCookie, isError, router]);

  if (!hasCookie || isError) return null;

  return <>{children}</>;
}
