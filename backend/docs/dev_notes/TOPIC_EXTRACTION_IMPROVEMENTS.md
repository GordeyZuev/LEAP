# План улучшений: Topic Extraction и Transcription

## 1. Анализ текущей реализации

### topic_extractor.py (DeepSeek)

**Странности и потенциальные проблемы:**

| Проблема | Описание | Решение |
|----------|----------|---------|
| Дублирование system prompt | Одинаковый текст в `client.chat.completions.create` и `_fireworks_request` | Вынести в константу или загрузчик |
| Несогласованность в except | `extract_topics` в except возвращает dict без `long_pauses`; вызывающий код в processing.py делает `topics_result.get("long_pauses", [])` — OK, fallback сработает | Оставить как есть (безопасно) или добавить `long_pauses: []` для консистентности |
| Перерыв 5 vs 8 минут | В промпте short: "Перерывы: все >=5 минут добавлены", но `MIN_PAUSE_MINUTES = 8` | Привести к единому значению (8 мин) |
| _process_main_topics | При `len(words) > 7` обрезаем до 7 слов, но MAIN_TOPIC_MAX_WORDS = 4 и промпт просит 2–4 слова | Привести к max 4–5 слов |
| Таймстампы MM:SS | `_parse_timestamp_to_seconds` при `seconds_str is None` трактует как MM:SS (minutes*60+sec). Для "02:15" на 2ч видео это даст 135 сек вместо 8100 | LLM обычно выдает HH:MM:SS. Добавить логирование при странных значениях или валидацию |
| Длинный inline промпт | Промпты ~60 строк в коде, сложно редактировать | Вынести в файлы |

### fireworks_module/service.py (Transcription)

| Проблема | Описание | Решение |
|----------|----------|---------|
| Минимальный prompt | `compose_fireworks_prompt` — только topic + "Consider specifics" | Расширить: topic + vocabulary (список терминов) |
| Нет vocabulary | Нет механизма передать "особые слова" для транскрайбера | Добавить параметр `vocabulary: list[str] \| None` |

### Отсутствующая функциональность

| Что | Где используется | Статус |
|-----|------------------|--------|
| `{summary}` | `description_template`, `metadata_config` | ✅ **РЕАЛИЗОВАНО** — `prepare_recording_context` читает `summary` из extracted.json |

---

## 2. Вынести промпт в отдельный файл — **СДЕЛАНО 2025-02-15** (deepseek_module/prompts.py)

**Подход:**
- Директория: `deepseek_module/prompts/` (или `config/prompts/` на уровне проекта)
- Файлы:
  - `system_prompt.txt` — системный промпт
  - `topic_extraction_short.txt` — промпт для granularity short
  - `topic_extraction_medium.txt` — для medium (новый)
  - `topic_extraction_long.txt` — для long

**Плейсхолдеры в шаблонах:**
- `{context_line}` — строка с контекстом курса
- `{pauses_instruction}` — блок про перерывы
- `{min_topics}`, `{max_topics}` — диапазон топиков
- `{min_spacing_minutes}` — минимальный шаг между темами
- `{recording_topic}` — для условной части "не дублируй слова из курса"
- `{transcript}` — транскрипция

**Реализация:**
- Класс `PromptLoader` или функция `load_prompt(name, **kwargs)` — загружает .txt и подставляет переменные
- Строгая типизация: `def load_prompt(name: str, /, **kwargs: str) -> str`
- Путь к файлам: `Path(__file__).parent / "prompts"` (относительно модуля)

---

## 3. Три уровня топиков: short / medium / long

**Текущее:** `granularity: Literal["short", "long"]`

**Новое:** `granularity: Literal["short", "medium", "long"]`

**Параметры по уровням:**

| Уровень | Длительность темы | Кол-во топиков (50 мин) | Кол-во (180 мин) | Min spacing |
|---------|-------------------|--------------------------|------------------|-------------|
| **short** | 10–45 мин | 3–8 | 5–12 | ~12 мин |
| **medium** | 5–15 мин | 8–15 | 15–22 | ~6 мин |
| **long** | 3–12 мин | 12–20 | 18–26 | ~4 мин |

**Изменения:**
1. `_calculate_topic_range(duration_minutes, granularity)` — добавить ветку `medium`
2. `_analyze_full_transcript` — три варианта промпта (или один шаблон с параметрами)
3. Схемы: `TranscriptionProcessingConfig`, `TranscriptionConfig`, `UserConfig` — `Literal["short", "medium", "long"]`
4. API: `extract_topics_task`, `BulkExtractTopicsRequest` — обновить валидацию

---

## 4. Отдельное саммари (summary) — **ОБНОВЛЕНО 2025-02-15**

**Цель:** Генерировать краткое содержание лекции (2–5 предложений) для `{summary}` в шаблонах.

**Реализация — DONE:**
1. Секция САММАРИ в промптах (SHORT, MEDIUM, LONG)
2. Парсинг в `_parse_structured_response`
3. Сохранение в `extracted.json` (версионировано)
4. **Хранилище:** summary только в extracted.json (master.json = только транскрипция)
5. `prepare_recording_context` — читает summary из extracted.json

---

## 5. Особые слова для транскрайбера (vocabulary) — **ОБНОВЛЕНО 2025-02-15**

**Цель:** Помочь Whisper лучше распознавать специфические термины (ML, Python, имена, аббревиатуры).

**Реализация — DONE:**
- `compose_fireworks_prompt(base_prompt, recording_topic, vocabulary)` — поддерживает vocabulary
- **Отдельное поле в шаблоне:** `transcription_vocabulary: list[str] | None` в `TemplateProcessingConfig`
- При резолве конфига: `transcription_vocabulary` мержится в `transcription.vocabulary`
- Схемы: TranscriptionProcessingConfig, TranscriptionConfig, TranscriptionConfigData — vocabulary
- API/tasks: передают vocabulary в compose_fireworks_prompt

**Формат для Whisper:** "Topic: X. Key terms to recognize: A, B, C."

---

## 6. Валидации и набор слов

**Набор слов (vocabulary)** — только для **транскрайбера** (Whisper/Fireworks). Помогает распознавать специфические термины (ML, имена, аббревиатуры). Не передаётся в DeepSeek/topic extraction.

**Реализация:**
- `transcription.vocabulary` / `transcription_vocabulary` в шаблоне
- `compose_fireworks_prompt()` в fireworks_module/service.py — передаёт vocabulary в промпт Whisper

---

## 7. Структура файлов (предлагаемая)

```
deepseek_module/
├── prompts/
│   ├── system.txt
│   ├── topic_extraction_short.txt
│   ├── topic_extraction_medium.txt
│   └── topic_extraction_long.txt
├── topic_extractor.py
└── config.py

config/
├── topic_hints.json   # опционально: пресеты по домену
└── ...

fireworks_module/
└── service.py  # compose_fireworks_prompt с vocabulary
```

---

## 8. Порядок внедрения (приоритеты)

1. **Промпты в файлы** — ✅ СДЕЛАНО (deepseek_module/prompts.py)
2. **summary** — добавление в промпт, парсинг, сохранение, TemplateRenderer
3. **Три уровня топиков** — medium, обновление схем
4. **vocabulary для транскрайбера** — compose_fireworks_prompt, config
5. **topic_hints** — подсказки в промпт topic extraction
6. **Исправления странностей** — system prompt, 5 vs 8 мин, _process_main_topics — **СДЕЛАНО 2025-02-15**

---

## 9. Оставшиеся потенциальные косяки (не критичные)

| Проблема | Статус |
|----------|--------|
| Таймстампы MM:SS | ✅ Heuristic: при total_duration>1h и h>=1 трактуем HH:MM |
| total_duration | ✅ max(seg.end, seg.start) по всем сегментам |
| `{summary}` | ✅ Добавлен в промпт, парсинг, extracted.json, prepare_recording_context |
| fireworks vocabulary | ✅ compose_fireworks_prompt + vocabulary в config |
| granularity validation | ✅ Нормализация: unknown → "long" |

---

## 10. Новая реализация (2025-02-15): vocabulary в шаблоне + summary в extracted.json

**transcription_vocabulary — отдельное поле шаблона:**
- `TemplateProcessingConfig.transcription_vocabulary: list[str] | None`
- При резолве конфига мержится в `transcription.vocabulary`
- Позволяет задавать особые слова на уровне шаблона (ML-курс → gradient descent, transformer, …)

**summary в extracted.json:**
- Summary пишется только в extracted.json (единый запрос DeepSeek)
- master.json — только транскрипция (words, segments)
- `prepare_recording_context` читает summary только из extracted.json

---

## 11. Вопросы для уточнения

1. **summary:** Хранить в Recording или только в extracted.json? Использовать ли при fallback (main_topics → themes) что-то вроде "Лекция по {main_topic}"?
2. **vocabulary:** Источник — только ручной ввод в template или ещё пресеты по домену (ml, python)?
3. **topic_hints vs vocabulary:** Это один и тот же набор слов (и для транскрайбера, и для topic extraction) или два разных (transcription_vocabulary, topic_hints)?
4. **Валидация топиков:** Нужна ли постобработка (проверка, что в топиках есть ожидаемые термины) или достаточно подсказок в промпт?
5. **Пресеты по домену:** Нужен ли `domain: "ml" | "python" | "general"` в template, который автоматически подставляет hints/vocabulary?
