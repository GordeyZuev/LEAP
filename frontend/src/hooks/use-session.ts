import { hasSessionCookie } from "@/lib/auth";
import { useMe } from "@/lib/react-query";
import { useHydrated } from "@/hooks/use-hydrated";

export type SessionStatus = "checking" | "authenticated" | "anonymous";

// Session status for public entry routes (/login, landing). Waits for /users/me
// when a cookie is present so a dead session does not bounce through /recordings.
export function useSession(): SessionStatus {
  const hydrated = useHydrated();
  const hasCookie = hydrated && hasSessionCookie();
  const { isError, isPending, data } = useMe({ enabled: hasCookie });

  if (!hydrated) return "checking";
  if (!hasCookie) return "anonymous";
  if (isError) return "anonymous";
  if (isPending && data === undefined) return "checking";
  return "authenticated";
}
