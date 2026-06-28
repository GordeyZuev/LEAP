import Link from "next/link";
import { ArrowRight } from "lucide-react";

export function LandingCta() {
  return (
    <footer className="py-16 px-6 bg-[#224C87]">
      <div className="max-w-2xl mx-auto text-center">
        <h2 className="text-2xl font-bold text-white mb-3">Готовы попробовать?</h2>
        <p className="text-blue-200 mb-8 text-sm">
          Зарегистрируйтесь и опубликуйте первое видео уже сегодня.
        </p>
        <Link
          href="/register"
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-white text-[#224C87] text-sm font-semibold rounded-xl hover:bg-gray-50 transition-all duration-200 active:scale-[0.97]"
        >
          Зарегистрироваться
          <ArrowRight size={15} />
        </Link>
        <p className="mt-10 text-blue-200/50 text-xs">© 2026 LEAP – Lecture Enhancement & Automation Platform</p>
      </div>
    </footer>
  );
}
