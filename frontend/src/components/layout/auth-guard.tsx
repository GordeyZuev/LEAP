"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.replace("/login");
    }
  }, [router]);

  // Render children — if token is missing the redirect happens above.
  // Pages will briefly mount but the API calls will 401 and the interceptor
  // will also redirect, so this is safe.
  return <>{children}</>;
}
