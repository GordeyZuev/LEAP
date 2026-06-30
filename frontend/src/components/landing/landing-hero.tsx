import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";

export function LandingHero() {
  return (
    <section className="pt-20 pb-12 sm:pt-32 sm:pb-20 px-6 text-center">
      <div className="max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 bg-primary/10 text-primary text-sm font-medium px-3 py-1.5 rounded-full mb-6">
          <Sparkles size={13} strokeWidth={2} />
          Платформа для образовательного видео
        </div>
        <h1 className="text-3xl sm:text-5xl font-bold text-foreground leading-tight mb-5 tracking-tight">
          Записали занятие?
          <br />
          <span className="text-primary">Остальное сделаем мы.</span>
        </h1>
        <p className="text-base sm:text-lg text-secondary-foreground leading-relaxed mb-8 sm:mb-10 max-w-2xl mx-auto">
          Загрузите видео из любого источника, получите готовую запись с субтитрами
          и опубликуйте на нескольких площадках – без ручной работы.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/register"
            className="inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-hover transition-all duration-200 active:scale-[0.97]"
          >
            Начать работу
            <ArrowRight size={15} />
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center px-6 py-2.5 text-sm font-medium border border-border text-secondary-foreground rounded-xl hover:bg-muted transition-all duration-200 active:scale-[0.97]"
          >
            Войти в аккаунт
          </Link>
        </div>
      </div>
    </section>
  );
}
