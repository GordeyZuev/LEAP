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

export function Sidebar() {
  const pathname = usePathname();
  // Hydrate after mount to avoid SSR/client mismatch: the server can't read
  // localStorage and would always render the expanded state.
  const [collapsed, setCollapsed] = useState(false);
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    /* eslint-disable react-hooks/set-state-in-effect */
    if (window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true") {
      setCollapsed(true);
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  function toggleCollapsed() {
    setCollapsed((c) => {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(!c));
      return !c;
    });
  }

  const labelClass = cn(
    "overflow-hidden whitespace-nowrap transition-all duration-200",
    collapsed ? "max-w-0 opacity-0 ml-0" : "max-w-[12rem] opacity-100 ml-3"
  );

  const linkClass = (active: boolean) =>
    cn(
      "flex items-center rounded-xl text-sm font-medium transition-colors px-3 py-2.5",
      collapsed && "justify-center",
      active
        ? "bg-white text-[#224C87]"
        : "text-white/80 hover:bg-white/10 hover:text-white"
    );

  return (
    <aside
      className={cn(
        "flex flex-col shrink-0 h-full bg-[#224C87] text-white overflow-hidden transition-[width] duration-200",
        collapsed ? "w-16" : "w-60"
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
          className={cn(
            "flex items-center gap-2 rounded-xl px-3 py-1.5 hover:bg-white/10 transition-colors",
            collapsed && "justify-center"
          )}
        >
          <Logo size={22} variant="inverse" />
          <span
            className={cn(
              "text-lg font-semibold tracking-wider text-white leading-none whitespace-nowrap overflow-hidden transition-all duration-200",
              collapsed ? "max-w-0 opacity-0 -ml-2" : "max-w-[5rem] opacity-100"
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
              title={collapsed ? label : undefined}
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
          href="/settings"
          title={collapsed ? "Settings" : undefined}
          className={linkClass(pathname === "/settings")}
        >
          <Settings size={18} strokeWidth={1.75} className="shrink-0" />
          <span className={labelClass}>Settings</span>
        </Link>
        <button
          onClick={() => setLogoutConfirmOpen(true)}
          title={collapsed ? "Log out" : undefined}
          className={cn(
            "flex items-center rounded-xl text-sm font-medium text-white/80 hover:bg-white/10 hover:text-white transition-colors w-full px-3 py-2.5",
            collapsed && "justify-center"
          )}
        >
          <LogOut size={18} strokeWidth={1.75} className="shrink-0" />
          <span className={labelClass}>Log out</span>
        </button>

        {/* Divider sets the collapse toggle apart from nav-style actions. */}
        <div className="mx-3 my-2 h-px bg-white/10" />

        <button
          onClick={toggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          className={cn(
            "flex items-center rounded-xl text-xs font-medium text-white/60 hover:bg-white/10 hover:text-white transition-colors w-full px-3 py-2",
            collapsed && "justify-center"
          )}
        >
          {collapsed ? (
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
  );
}
