import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiClient } from "@/api/client";
import { PER_PAGE_LARGE } from "@/lib/constants";

export const CREDENTIALS_REAUTH_QUERY_KEY = ["credentials-reauth"] as const;

export interface CredentialReauthItem {
  id: number;
  platform: string;
  account_name: string | null;
  needs_reauth: boolean;
}

interface CredentialReauthListResponse {
  items: CredentialReauthItem[];
  total: number;
}

export function credentialsNavAriaLabel(count: number): string {
  if (count <= 0) return "Credentials";
  if (count === 1) return "Credentials, 1 credential needs reconnection";
  return `Credentials, ${count} credentials need reconnection`;
}

export function navigationMenuAriaLabel(count: number): string {
  if (count <= 0) return "Open navigation menu";
  if (count === 1) return "Open navigation menu, 1 credential needs reconnection";
  return `Open navigation menu, ${count} credentials need reconnection`;
}

/** Credentials the platform has rejected — used by the app-shell banner and sidebar badge. */
export function useCredentialsNeedingReauth() {
  // Same pattern as the collapsed sidebar: false on the server and on the
  // first client paint, then true after mount. A cached React Query result
  // must not change the Credentials markup during hydration.
  const [isClient, setIsClient] = useState(false);
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    setIsClient(true);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  const query = useQuery({
    queryKey: CREDENTIALS_REAUTH_QUERY_KEY,
    queryFn: async () => {
      const res = await apiClient.get<CredentialReauthListResponse>(
        `/credentials?needs_reauth=true&per_page=${PER_PAGE_LARGE}`,
      );
      return res.data;
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: isClient,
  });

  if (!isClient) {
    return { ...query, data: undefined };
  }
  return query;
}
