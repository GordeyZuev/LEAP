"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { useSession } from "@/hooks/use-session";

// Gates the (app) section on an authenticated session. Renders a loading
// placeholder until session status is known so protected pages never paint
// before redirect.
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const status = useSession();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return (
      <div className="flex h-full items-center justify-center bg-background" role="status" aria-label="Loading">
        <Loader2 className="animate-spin text-muted-foreground" size={28} />
      </div>
    );
  }
  return <>{children}</>;
}
