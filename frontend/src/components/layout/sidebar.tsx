"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Video,
  FileText,
  Settings2,
  Database,
  Key,
  Zap,
  BookOpen,
  Settings,
  LogOut,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { Logo } from "@/components/layout/logo";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { apiClient } from "@/api/client";

const SIDEBAR_COLLAPSED_KEY = "sidebar-collapsed";

const navItems = [
  { href: "/recordings", label: "Recordings", icon: Video },
  { href: "/templates", label: "Templates", icon: FileText },
  { href: "/presets", label: "Presets", icon: Settings2 },
  { href: "/sources", label: "Sources", icon: Database },
  { href: "/credentials", label: "Credentials", icon: Key },
  { href: "/automation", label: "Automation", icon: Zap },
];

async function performLogout() {
  // POST /auth/logout clears the httpOnly session cookies on the server. Even
  // if the call fails (network error, expired session), we still navigate to
  // /login so the user isn't stuck.
  try {
    await apiClient.post("/auth/logout");
  } catch {
    // Ignored — proceed to /login regardless.
  }
  window.location.href = "/login";
}

interface SidebarProps {
  /** Mobile drawer open state. Ignored on lg+ where the sidebar is static. */
  mobileOpen?: boolean;
  /** Called to close the mobile drawer (nav click, backdrop, route change, ESC). */
  onMobileClose?: () => void;
}

export function Sidebar({ mobileOpen = false, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  // Hydrate after mount to avoid SSR/client mismatch: the server can't read
  // localStorage and would always render the expanded state.
  const [collapsed, setCollapsed] = useState(false);
  const [isDesktop, setIsDesktop] = useState(true);
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    /* eslint-disable react-hooks/set-state-in-effect */
    if (window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true") {
      setCollapsed(true);
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  // Track viewport so the drawer (mobile) is always expanded while the
  // persistent sidebar (lg+) respects the user's collapse preference.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(min-width: 1024px)");
    const apply = () => setIsDesktop(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  // Close the mobile drawer on route change so navigating doesn't leave it open.
  useEffect(() => {
    onMobileClose?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  // Close the mobile drawer on Escape.
  useEffect(() => {
    if (!mobileOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onMobileClose?.();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen, onMobileClose]);

  // On mobile the drawer is always expanded (the collapse affordance is desktop-only).
  const effectiveCollapsed = isDesktop && collapsed;

  function toggleCollapsed() {
    setCollapsed((c) => {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(!c));
      return !c;
    });
  }

  const labelClass = cn(
    "overflow-hidden whitespace-nowrap transition-all duration-200",
    effectiveCollapsed ? "max-w-0 opacity-0 ml-0" : "max-w-[12rem] opacity-100 ml-3"
  );

  const linkClass = (active: boolean) =>
    cn(
      "flex items-center rounded-xl text-sm font-medium transition-colors px-3 py-2.5",
      effectiveCollapsed && "justify-center",
      active
        ? "bg-sidebar-active text-primary dark:text-white shadow-sm"
        : "text-white/80 hover:bg-white/10 hover:text-white"
    );

  return (
    <>
      {/* Backdrop — mobile drawer only. */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden animate-overlay-in"
          aria-hidden="true"
          onClick={onMobileClose}
        />
      )}
      <aside
        className={cn(
          "flex flex-col h-full bg-sidebar text-white overflow-hidden",
          // Desktop: static column whose width tracks the collapse state.
          "lg:static lg:z-auto lg:shrink-0 lg:translate-x-0 transition-[width,transform] duration-200",
          effectiveCollapsed ? "lg:w-16" : "lg:w-60",
          // Mobile: fixed off-canvas drawer that slides in when open.
          "fixed inset-y-0 left-0 z-50 w-64",
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
      {/* Logo — always navigates to /recordings, wordmark animates with sidebar width.
          Padding mirrors nav (px-2 on wrapper + px-3 on link) so the symbol stays on
          the same x-axis as nav icons in both states. */}
      <div className="px-2 py-5">
        <Link
          href="/recordings"
          title="Recordings"
          aria-label="LEAP — recordings"
          onClick={onMobileClose}
          className={cn(
            "flex items-center gap-2 rounded-xl px-3 py-1.5 hover:bg-white/10 transition-colors",
            effectiveCollapsed && "justify-center"
          )}
        >
          <Logo size={22} variant="inverse" />
          <span
            className={cn(
              "text-lg font-semibold tracking-wider text-white leading-none whitespace-nowrap overflow-hidden transition-all duration-200",
              effectiveCollapsed ? "max-w-0 opacity-0 -ml-2" : "max-w-[5rem] opacity-100"
            )}
          >
            LEAP
          </span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              title={effectiveCollapsed ? label : undefined}
              onClick={onMobileClose}
              className={linkClass(active)}
            >
              <Icon size={18} strokeWidth={1.75} className="shrink-0" />
              <span className={labelClass}>{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="px-2 pb-4 space-y-1">
        <Link
          href="/docs"
          title={effectiveCollapsed ? "Documentation" : undefined}
          onClick={onMobileClose}
          className={linkClass(pathname === "/docs" || pathname.startsWith("/docs/"))}
        >
          <BookOpen size={18} strokeWidth={1.75} className="shrink-0" />
          <span className={labelClass}>Documentation</span>
        </Link>
        <Link
          href="/settings"
          title={effectiveCollapsed ? "Settings" : undefined}
          onClick={onMobileClose}
          className={linkClass(pathname === "/settings")}
        >
          <Settings size={18} strokeWidth={1.75} className="shrink-0" />
          <span className={labelClass}>Settings</span>
        </Link>
        <button
          onClick={() => setLogoutConfirmOpen(true)}
          title={effectiveCollapsed ? "Log out" : undefined}
          className={cn(
            "flex items-center rounded-xl text-sm font-medium text-white/80 hover:bg-white/10 hover:text-white transition-colors w-full px-3 py-2.5",
            effectiveCollapsed && "justify-center"
          )}
        >
          <LogOut size={18} strokeWidth={1.75} className="shrink-0" />
          <span className={labelClass}>Log out</span>
        </button>

        {/* Divider sets the collapse toggle apart from nav-style actions. */}
        <div className="mx-3 my-2 h-px bg-white/10 hidden lg:block" />

        {/* Collapse toggle is a desktop affordance — hidden in the mobile drawer. */}
        <button
          onClick={toggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          className={cn(
            "hidden lg:flex items-center rounded-xl text-xs font-medium text-white/60 hover:bg-white/10 hover:text-white transition-colors w-full px-3 py-2",
            effectiveCollapsed && "justify-center"
          )}
        >
          {effectiveCollapsed ? (
            <ChevronsRight size={16} strokeWidth={2} className="shrink-0" />
          ) : (
            <ChevronsLeft size={16} strokeWidth={2} className="shrink-0" />
          )}
          <span className={labelClass}>Collapse sidebar</span>
        </button>
      </div>

      <ConfirmDialog
        open={logoutConfirmOpen}
        title="Log out?"
        description="You'll be signed out and returned to the login page. Any unsaved changes in open forms will be lost."
        confirmLabel="Log out"
        cancelLabel="Cancel"
        danger
        onConfirm={() => {
          setLogoutConfirmOpen(false);
          void performLogout();
        }}
        onCancel={() => setLogoutConfirmOpen(false)}
      />
      </aside>
    </>
  );
}
