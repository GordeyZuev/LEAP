import Link from "next/link";
import { ArrowRight } from "lucide-react";

export function LandingCta() {
  return (
    <footer className="py-12 sm:py-16 px-6 bg-primary">
      <div className="max-w-2xl mx-auto text-center">
        <h2 className="text-xl sm:text-2xl font-bold text-white mb-3">Готовы попробовать?</h2>
        <p className="text-blue-200 mb-8 text-sm">
          Зарегистрируйтесь и опубликуйте первое видео уже сегодня.
        </p>
        <Link
          href="/register"
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-card text-primary text-sm font-semibold rounded-xl hover:bg-muted transition-all duration-200 active:scale-[0.97]"
        >
          Зарегистрироваться
          <ArrowRight size={15} />
        </Link>
        <p className="mt-10 text-blue-200/50 text-xs">© 2026 LEAP – Lecture Enhancement & Automation Platform</p>
      </div>
    </footer>
  );
}
