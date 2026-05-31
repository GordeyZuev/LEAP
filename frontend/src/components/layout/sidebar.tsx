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
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";

const navItems = [
  { href: "/recordings", label: "Recordings", icon: Video },
  { href: "/templates", label: "Templates", icon: FileText },
  { href: "/presets", label: "Presets", icon: Settings2 },
  { href: "/sources", label: "Sources", icon: Database },
  { href: "/credentials", label: "Credentials", icon: Key },
  { href: "/automation", label: "Automation", icon: Zap },
];

function logout() {
  localStorage.clear();
  window.location.href = "/login";
}

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== "undefined" && localStorage.getItem("sidebar-collapsed") === "true",
  );

  function toggleCollapsed() {
    setCollapsed((c) => {
      localStorage.setItem("sidebar-collapsed", String(!c));
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
      {/* Logo + toggle */}
      <div className={cn("flex items-center px-3 py-5", !collapsed && "px-5")}>
        <span
          className={cn(
            "overflow-hidden whitespace-nowrap transition-all duration-200 text-xl font-bold tracking-tight",
            collapsed ? "max-w-0 opacity-0" : "max-w-[12rem] opacity-100 mr-auto"
          )}
        >
          LEAP
        </span>
        <button
          onClick={toggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="p-1.5 rounded-lg text-white/60 hover:text-white hover:bg-white/10 transition-colors shrink-0"
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
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
          onClick={logout}
          title={collapsed ? "Log out" : undefined}
          className={cn(
            "flex items-center rounded-xl text-sm font-medium text-white/80 hover:bg-white/10 hover:text-white transition-colors w-full px-3 py-2.5",
            collapsed && "justify-center"
          )}
        >
          <LogOut size={18} strokeWidth={1.75} className="shrink-0" />
          <span className={labelClass}>Log out</span>
        </button>
      </div>
    </aside>
  );
}
