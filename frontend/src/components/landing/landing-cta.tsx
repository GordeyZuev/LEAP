import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { AgeRatingBadge } from "@/components/ui/age-rating-badge";

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
          className="pressable inline-flex items-center gap-2 px-6 py-2.5 bg-card text-primary text-sm font-semibold rounded-xl hover:bg-muted"
        >
          Зарегистрироваться
          <ArrowRight size={15} />
        </Link>
        <p className="mt-10 flex items-center justify-center gap-2 text-blue-200 text-xs">
          <span>© 2026 LEAP – Lecture Enhancement & Automation Platform</span>
          <AgeRatingBadge className="border-blue-200/80 text-blue-100" label="Возрастное ограничение: 12+" />
        </p>
      </div>
    </footer>
  );
}
