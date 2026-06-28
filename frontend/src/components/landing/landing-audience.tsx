import { Building2, GraduationCap, Radio } from "lucide-react";

const cards = [
  {
    icon: Building2,
    title: "Факультеты, школы и онлайн-курсы",
    description:
      "Записываете каждую пару или урок? Настройте один раз – и все новые записи будут обрабатываться и публиковаться автоматически. Отдельное пространство для каждого преподавателя, общее управление для администратора.",
    highlights: ["Все уроки и пары", "Общее управление", "Готовые интеграции"],
  },
  {
    icon: GraduationCap,
    title: "Преподаватели и репетиторы",
    description:
      "Записали занятие – загрузите, и платформа сама обрежет, добавит субтитры и опубликует на нужных площадках. Никакого монтажа вручную.",
    highlights: ["Zoom и Яндекс.Диск", "Субтитры на русском", "YouTube и ВКонтакте"],
  },
  {
    icon: Radio,
    title: "Авторы вебинаров и лекций",
    description:
      "Проводите вебинары и курсы? LEAP автоматически подхватывает записи и публикует их на всех площадках – вы только ведёте эфир.",
    highlights: ["Вебинары и лекции", "Автопубликация", "Несколько платформ"],
  },
];

export function LandingAudience() {
  return (
    <section className="py-16 px-6 bg-white">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold text-gray-900 text-center mb-2">Для кого</h2>
        <p className="text-sm text-gray-500 text-center mb-10">
          Для всех, кто регулярно записывает и публикует учебный контент
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <div key={card.title} className="p-6 rounded-xl border border-[#D9D9D9] bg-[#FAFAFA] flex flex-col">
                <div className="w-10 h-10 rounded-xl bg-[#224C87]/10 flex items-center justify-center mb-4 shrink-0">
                  <Icon size={20} className="text-[#224C87]" strokeWidth={1.75} />
                </div>
                <h3 className="text-base font-semibold text-gray-900 mb-2">{card.title}</h3>
                <p className="text-sm text-gray-600 leading-relaxed mb-4 flex-1">{card.description}</p>
                <ul className="flex flex-wrap gap-2">
                  {card.highlights.map((tag) => (
                    <li
                      key={tag}
                      className="text-xs font-medium px-2.5 py-1 rounded-full bg-[#224C87]/10 text-[#224C87]"
                    >
                      {tag}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
