"use client";

import Image from "next/image";
import Link from "next/link";

export function LandingNavbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-card/90 backdrop-blur-sm border-b border-border">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Image src="/logo_symb.svg" alt="LEAP" width={24} height={29} priority />
          <span className="text-lg font-semibold tracking-wider text-primary leading-none">LEAP</span>
        </div>
        {/* No nav links to hide, so narrow screens only need smaller controls
            and a shorter sign-up label — a hamburger would have nothing in it. */}
        <div className="flex shrink-0 items-center gap-2">
          <Link
            href="/login"
            className="px-3 py-1.5 text-xs sm:px-4 sm:py-2 sm:text-sm font-medium border border-border text-secondary-foreground rounded-xl hover:bg-muted transition-all duration-200"
          >
            Войти
          </Link>
          <Link
            href="/register"
            className="px-3 py-1.5 text-xs sm:px-4 sm:py-2 sm:text-sm font-medium bg-primary text-white rounded-xl hover:bg-primary-hover transition-all duration-200"
          >
            <span className="sm:hidden">Начать</span>
            <span className="hidden sm:inline">Зарегистрироваться</span>
          </Link>
        </div>
      </div>
    </nav>
  );
}
