"use client";

import Image from "next/image";
import Link from "next/link";

export function LandingNavbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white/90 backdrop-blur-sm border-b border-[#D9D9D9]">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Image src="/logo_symb.svg" alt="LEAP" width={24} height={29} priority />
          <span className="text-lg font-semibold tracking-wider text-[#224C87] leading-none">LEAP</span>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/login"
            className="px-4 py-2 text-sm font-medium border border-[#D9D9D9] text-gray-600 rounded-xl hover:bg-gray-50 transition-all duration-200"
          >
            Войти
          </Link>
          <Link
            href="/register"
            className="px-4 py-2 text-sm font-medium bg-[#224C87] text-white rounded-xl hover:bg-[#1a3d6e] transition-all duration-200"
          >
            Зарегистрироваться
          </Link>
        </div>
      </div>
    </nav>
  );
}
