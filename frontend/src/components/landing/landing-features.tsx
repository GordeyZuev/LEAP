import { Link2, Mic, Captions, Share2, LayoutTemplate, Zap } from "lucide-react";

const features = [
  {
    icon: Link2,
    title: "Загрузка из любого источника",
    description: "Ваши файлы, Zoom, Яндекс.Диск и ссылки на видео – всё в одном месте.",
  },
  {
    icon: Mic,
    title: "AI-транскрипция",
    description: "Современные модели распознают речь с высокой точностью на русском и английском.",
  },
  {
    icon: Captions,
    title: "Автоматические субтитры",
    description: "Субтитры генерируются и встраиваются в видео сразу после распознавания речи.",
  },
  {
    icon: Share2,
    title: "Публикация на все площадки",
    description: "Одна запись – YouTube / ВКонтакте / Яндекс.Диск и другие – одновременно.",
  },
  {
    icon: LayoutTemplate,
    title: "Шаблоны и пресеты",
    description: "Настройте параметры обработки и публикации один раз – применяйте к любой записи.",
  },
  {
    icon: Zap,
    title: "Полная автоматизация",
    description: "Загрузите один раз – каждая новая запись обрабатывается и публикуется автоматически.",
  },
];

export function LandingFeatures() {
  return (
    <section className="py-16 px-6 bg-white">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold text-gray-900 text-center mb-2">Возможности</h2>
        <p className="text-sm text-gray-500 text-center mb-10">Всё, что нужно для работы с учебным видеоконтентом</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map((f) => {
            const Icon = f.icon;
            return (
              <div key={f.title} className="p-5 rounded-xl border border-[#D9D9D9] bg-[#FAFAFA] flex gap-4">
                <div className="shrink-0 w-9 h-9 rounded-xl bg-[#224C87]/10 flex items-center justify-center mt-0.5">
                  <Icon size={18} className="text-[#224C87]" strokeWidth={1.75} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">{f.title}</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">{f.description}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
