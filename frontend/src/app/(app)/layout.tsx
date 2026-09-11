import { cookies } from "next/headers";
import { AuthGuard } from "@/components/layout/auth-guard";
import { AppShell } from "@/components/layout/app-shell";
import { DisplayConfigDefaultsPrefetch } from "@/components/platforms/display-config-defaults-prefetch";
import { CSRF_COOKIE_NAME } from "@/lib/auth";
import { fetchMeServer } from "@/lib/fetch-me-server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const hasSession = (await cookies()).has(CSRF_COOKIE_NAME);
  const me = hasSession ? await fetchMeServer() : null;
  const isAdmin = me?.role === "admin";

  return (
    <AuthGuard hasSession={hasSession}>
      <DisplayConfigDefaultsPrefetch />
      <AppShell isAdmin={isAdmin}>{children}</AppShell>
    </AuthGuard>
  );
}
