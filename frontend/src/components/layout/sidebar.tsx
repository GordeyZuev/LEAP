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
} from "lucide-react";
import { cn } from "@/lib/utils";

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

  return (
    <aside className="flex flex-col w-60 shrink-0 h-full bg-[#224C87] text-white">
      {/* Logo */}
      <div className="px-6 py-6">
        <span className="text-xl font-bold tracking-tight">LEAP</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors",
                active
                  ? "bg-white text-[#224C87]"
                  : "text-white/80 hover:bg-white/10 hover:text-white"
              )}
            >
              <Icon size={18} strokeWidth={1.75} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="px-3 pb-4 space-y-1">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors",
            pathname === "/settings"
              ? "bg-white text-[#224C87]"
              : "text-white/80 hover:bg-white/10 hover:text-white"
          )}
        >
          <Settings size={18} strokeWidth={1.75} />
          Settings
        </Link>
        <button
          onClick={logout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-white/80 hover:bg-white/10 hover:text-white transition-colors w-full"
        >
          <LogOut size={18} strokeWidth={1.75} />
          Log out
        </button>
      </div>
    </aside>
  );
}
