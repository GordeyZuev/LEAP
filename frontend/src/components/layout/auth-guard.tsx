"use client";

import { useEffect } from "react";

import { useRouter } from "next/navigation";

import { hasSessionCookie } from "@/lib/auth";
import { useMe } from "@/lib/react-query";

// Gates the (app) section. The server passes whether the csrf cookie was on the
// request so the first paint matches SSR (document.cookie is empty on the server).
export function AuthGuard({
  children,
  hasSession,
}: {
  children: React.ReactNode;
  hasSession: boolean;
}) {
  const router = useRouter();
  const { isError } = useMe({ enabled: hasSession });

  useEffect(() => {
    if (!hasSessionCookie() || isError) router.replace("/login");
  }, [hasSession, isError, router]);

  if (!hasSession || isError) return null;

  return <>{children}</>;
}
