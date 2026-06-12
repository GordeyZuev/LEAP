import { AuthGuard } from "@/components/layout/auth-guard";
import { Sidebar } from "@/components/layout/sidebar";
import { DisplayConfigDefaultsPrefetch } from "@/components/platforms/display-config-defaults-prefetch";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <DisplayConfigDefaultsPrefetch />
      <div className="flex h-full">
        <Sidebar />
        <main className="flex-1 overflow-auto bg-[#FAFAFA]">{children}</main>
      </div>
    </AuthGuard>
  );
}
