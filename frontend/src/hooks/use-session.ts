import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { hasSessionCookie } from "@/lib/auth";

export type SessionStatus = "checking" | "authenticated" | "anonymous";

// Verifies the session by hitting /users/me. The fast path skips the round-trip
// when the CSRF cookie isn't even present (no session possible).
export function useSession(): SessionStatus {
  const [status, setStatus] = useState<SessionStatus>("checking");

  useEffect(() => {
    let cancelled = false;
    async function verify() {
      if (!hasSessionCookie()) {
        if (!cancelled) setStatus("anonymous");
        return;
      }
      try {
        await apiClient.get("/users/me");
        if (!cancelled) setStatus("authenticated");
      } catch {
        if (!cancelled) setStatus("anonymous");
      }
    }
    void verify();
    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}
