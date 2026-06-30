const steps = [
  {
    n: "01",
    title: "Загрузите запись",
    description: "Подключите Zoom, загрузите файл, вставьте ссылку или выберите из Яндекс.Диска.",
  },
  {
    n: "02",
    title: "Получите готовое видео",
    description: "Запись обрезается, речь распознаётся, субтитры генерируются – без вашего участия.",
  },
  {
    n: "03",
    title: "Опубликуйте на площадки",
    description: "YouTube, ВКонтакте, Яндекс.Диск – одной кнопкой или по расписанию, с описанием и тегами.",
  },
  {
    n: "04",
    title: "Настройте автоматизацию",
    description: "Создайте шаблон один раз – каждая новая запись из любого источника будет обрабатываться и публиковаться сама.",
  },
];

export function LandingHowItWorks() {
  return (
    <section className="py-16 px-6">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold text-foreground text-center mb-2">Как это работает</h2>
        <p className="text-sm text-muted-foreground text-center mb-10">От записи до публикации – несколько минут</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step) => (
            <div key={step.n} className="relative">
              <div className="text-4xl font-black text-primary/15 mb-3 leading-none">{step.n}</div>
              <h3 className="text-base font-semibold text-foreground mb-2">{step.title}</h3>
              <p className="text-sm text-secondary-foreground leading-relaxed">{step.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
