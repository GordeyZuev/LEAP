import { hasSessionCookie } from "@/lib/auth";
import { useMe } from "@/lib/react-query";

export type SessionStatus = "checking" | "authenticated" | "anonymous";

// Session status for public entry routes (/login, landing). Waits for /users/me
// when a cookie is present so a dead session does not bounce through /recordings.
export function useSession(): SessionStatus {
  const hasCookie = hasSessionCookie();
  const { isError, isPending, data } = useMe({ enabled: hasCookie });

  if (!hasCookie) return "anonymous";
  if (isError) return "anonymous";
  if (isPending && data === undefined) return "checking";
  return "authenticated";
}
