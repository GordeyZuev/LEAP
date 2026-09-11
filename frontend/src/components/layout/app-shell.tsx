"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import { Footer } from "@/components/layout/footer";
import { Logo } from "@/components/layout/logo";
import { ReleaseNotesGate } from "@/components/layout/release-notes-gate";

function PathKeyedMain({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="flex-1 animate-page-in">
      {children}
    </div>
  );
}

/**
 * App chrome: persistent collapsible sidebar on lg+, an off-canvas drawer on
 * mobile opened from a top bar. Owns the mobile drawer open state so the top
 * bar's hamburger and the Sidebar drawer stay in sync.
 */
export function AppShell({
  children,
  isAdmin = false,
}: {
  children: React.ReactNode;
  isAdmin?: boolean;
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex h-full">
      <ReleaseNotesGate />
      <Suspense fallback={<aside className="hidden h-full w-60 shrink-0 bg-sidebar lg:block" aria-hidden />}>
        <Sidebar
          isAdmin={isAdmin}
          mobileOpen={mobileNavOpen}
          onMobileClose={() => setMobileNavOpen(false)}
        />
      </Suspense>
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar — hidden on lg+ where the sidebar is always visible. */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4 lg:hidden">
          <button
            type="button"
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open navigation menu"
            className="pressable rounded-lg p-1.5 text-secondary-foreground hover:bg-muted hover:text-foreground"
          >
            <Menu size={22} />
          </button>
          <Link href="/recordings" aria-label="LEAP — recordings" className="flex items-center gap-2">
            <Logo size={20} />
            <span className="text-base font-semibold tracking-wider text-primary">LEAP</span>
          </Link>
        </header>
        <main className="flex-1 overflow-auto bg-background">
          <div className="flex min-h-full flex-col">
            <Suspense fallback={<div className="flex-1">{children}</div>}>
              <PathKeyedMain>{children}</PathKeyedMain>
            </Suspense>
            <Footer />
          </div>
        </main>
      </div>
    </div>
  );
}
