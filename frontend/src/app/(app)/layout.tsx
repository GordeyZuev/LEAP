import { AuthGuard } from "@/components/layout/auth-guard";
import { AppShell } from "@/components/layout/app-shell";
import { DisplayConfigDefaultsPrefetch } from "@/components/platforms/display-config-defaults-prefetch";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <DisplayConfigDefaultsPrefetch />
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
