import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";

export function LandingHero() {
  return (
    <section className="pt-32 pb-20 px-6 text-center">
      <div className="max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 bg-[#224C87]/10 text-[#224C87] text-sm font-medium px-3 py-1.5 rounded-full mb-6">
          <Sparkles size={13} strokeWidth={2} />
          Платформа для образовательного видео
        </div>
        <h1 className="text-5xl font-bold text-gray-900 leading-tight mb-5 tracking-tight">
          Записали занятие?
          <br />
          <span className="text-[#224C87]">Остальное сделаем мы.</span>
        </h1>
        <p className="text-lg text-gray-600 leading-relaxed mb-10 max-w-2xl mx-auto">
          Загрузите видео из любого источника, получите готовую запись с субтитрами
          и опубликуйте на нескольких площадках – без ручной работы.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/register"
            className="inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-[#224C87] text-white text-sm font-medium rounded-xl hover:bg-[#1a3d6e] transition-all duration-200 active:scale-[0.97]"
          >
            Начать работу
            <ArrowRight size={15} />
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center px-6 py-2.5 text-sm font-medium border border-[#D9D9D9] text-gray-600 rounded-xl hover:bg-gray-50 transition-all duration-200 active:scale-[0.97]"
          >
            Войти в аккаунт
          </Link>
        </div>
      </div>
    </section>
  );
}
