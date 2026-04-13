# Сравнение ASR-систем: модели и сервисы распознавания речи

> Таблица проверена по официальным источникам (март 2025). Цены в USD за минуту аудио, если не указано иное.
>
> **Покрытие:** Whisper-based (Fireworks, OpenAI), коммерческие ASR (AssemblyAI, Deepgram incl. Cloudflare, Gladia, ElevenLabs), enterprise (Azure, Google), self-hosted RU. Gladia и ElevenLabs добавлены для полноты сравнения с типичными таблицами стоимости API.
>
> **Подробный разбор моделей и статей:** [ASR_MODELS_DEEP_DIVE.md](../guides/ASR_MODELS_DEEP_DIVE.md) — Fireworks, API, self-hosted, языки, промптинг, scope, RTF, полная таблица.

---

## Сводная таблица (для статьи)

Компактная таблица для выбора и сравнения. Детали — в разделах ниже.

| Модель | Тип | Цена $/мин | RTF ≈ | RU WER | Промптинг | Scope | Главное |
|--------|-----|------------|-------|--------|-----------|-------|---------|
| **Fireworks turbo** | API | 0.0009 | **0.002–0.007** | ~10% | Whisper | Whole | 1 ч за 3–7 с (Fireworks blog) |
| **Fireworks large** | API | 0.0015 | **0.003–0.01** | ~10% | Whisper | Whole | 1 ч за 4.5–11 с |
| **OpenAI Whisper** | API | 0.006 | **0.03** (105 с/1 ч) | ~10% | Whisper | ? | Эталон, 20× медленнее Fireworks |
| **AssemblyAI U3** | API | 0.0035 | 0.02–0.05 (оценка) | — | Keyterms + prompt | Whole | Plain language, 6 языков |
| **Gladia v2** | API | 0.006–0.01 | 0.02–0.05 (оценка) | Хорошо | Custom vocab (beta) | Whole | 100+ яз., Solaria, real-time <300 ms |
| **ElevenLabs Scribe v1** | API | 0.0037–0.0067 | 0.03–0.1 (оценка) | — | Keyterms, entities | Whole | 90+ яз., timestamps, 98% acc |
| **Deepgram Nova-3** | API | 0.0077 | TTFT 0.2–0.3 с (stream) | EN | Keyterms | Whole | Streaming, не batch RTF |
| **Deepgram Nova-3 (Cloudflare)** | API | 0.0052 HTTP | TTFT ~0.3 с (оценка) | RU+ | Keyterms | Whole | Workers AI, дешевле PAYG |
| **GigaAM-v3** | Self | — | 0.05–0.15 | **3–10%** | — | — | SOTA RU (alphacephei 8.4%) |
| **Pisets** | Self | — | 0.15–0.25 GPU | 2–5% | — | — | Лекции, робастность |
| **podlodka-turbo** | Self | — | 0.03–0.1 | ~9% (HF); 14% (alphacephei) | Whisper | Full | RU подкасты |
| **Borealis** | Self | — | 0.05–0.2 | ~6% (HF); 16% (alphacephei) | LLM | Whole | Пунктуация из коробки |
| **Faster-Whisper** | Self | — | **0.022** (large-v2, RTX 3070 Ti) | ~10% | Whisper | Full | Документированный RTF |
| **T-one** | Self | — | <0.01 stream | 6–9% | — | — | Телефония, 300 ms |
| **Vosk** | Self | — | 0.2–0.5 CPU | ~11% | — | — | CPU, offline |

---

## Важные поинты для статьи

- **Fireworks — оптимальный API для RU:** $0.0009/мин (10× дешевле OpenAI), whole-request prompt, RTF 0.002–0.007 (1 ч за 3–7 с, [blog](https://fireworks.ai/blog/audio-transcription-launch)). 20× быстрее OpenAI (105 с/1 ч).
- **Scope промпта критичен для длинного аудио:** whole request (Fireworks, AssemblyAI, Deepgram) — термины действуют по всей длине; initial only (WhisperX) — «затухают» после первого чанка.
- **RTF для self-hosted — без железа бесполезен:** Faster-Whisper 0.022 на RTX 3070 Ti (док.), Pisets 0.15–0.25 GPU (README). Borealis, podlodka — не документировано. Замерять на своём GPU/CPU.
- **GigaAM-v3 — SOTA RU:** alphacephei 11 доменов — 8.42% среднее (GigaAM2 CTC+LM). Лучше Borealis (16%), podlodka (14%), Whisper (16%).
- **Borealis — пунктуация через LLM:** Whisper + Qwen4B, 7k ч. Хорош на читаемой речи (HF 6.33%); слаб на телефонии (alphacephei 29%).
- **Два бенчмарка RU:** HF (6 датасетов) vs alphacephei (11 доменов). Разница для Borealis и podlodка — большая (6% vs 16%, 9% vs 14%).
- **Pisets — лекции и интервью:** Wav2Vec2 + AST + Whisper, RTF 0.15–0.25 (README). Робастность к длинному аудио.
- **T-one — для телефонии:** streaming 300 ms, CTC Conformer 71.6M. Лучше GigaAM на колл-центре (Habr).

---

## API-сервисы

> **RTF для API:** для batch (pre-recorded) RTF документирован только у Fireworks (1 ч за 3–11 с). Deepgram/Gladia — streaming TTFT (мс), не batch RTF. Остальное — оценка.

| Модель/Сервис                     | RTF (≈, GPU/сервер) | Цена ($/мин)     | Развертывание           | Промптинг                                  | Архитектура               | RU качество  | Ключ оптимизации                        |
| --------------------------------- | -------------------- | ---------------- | ----------------------- | ------------------------------------------ | ------------------------- | ------------ | --------------------------------------- |
| **Fireworks Whisper-v3-turbo**    | **0.002–0.007** (док.) | 0.0009           | API serverless          | ✅ Whisper-style (prompt до 224 токенов)    | Encoder-Decoder (4 слоя)  | Хорошо       | 1 ч за 3–7 с [blog](https://fireworks.ai/blog/audio-transcription-launch) |
| **Fireworks Whisper-v3-large**    | **0.003–0.01** (док.)  | 0.0015           | API serverless          | ✅ Whisper-style                            | Encoder-Decoder (32 слоя) | Отлично      | 1 ч за 4.5–11 с, dedicated быстрее      |
| **OpenAI Whisper API**            | **0.03** (105 с/1 ч)   | 0.006            | API                     | ⚠️ Частично (prompt до 224 токенов, стиль) | Encoder-Decoder           | Хорошо       | Fireworks: 20× медленнее                 |
| **OpenAI GPT-4o Mini Transcribe** | 0.02–0.05 (оценка)     | 0.003            | API                     | ✅ LLM-style (свободный текст)              | Multimodal LLM            | Хорошо       | ASR + reasoning в одном                 |
| **AssemblyAI Universal-3 Pro**   | 0.02–0.05 (оценка)     | 0.0035           | API batch/stream        | ⚠️ Keyterms + Prompting (plain language)   | Custom ASR                | Хорошо       | U2: TTFT 300–600 ms [benchmarks]         |
| **Deepgram Nova-3**               | TTFT **0.2–0.3 с**     | 0.0077           | API streaming           | ⚠️ Keyterm Prompting (+$0.0013/мин)        | C++/CUDA runtime          | Отлично (EN) | Streaming, не batch RTF                  |
| **Deepgram Nova-3 (Cloudflare)** | TTFT ~0.3 с (оценка)   | 0.0052 (HTTP)    | API (Workers AI)        | ⚠️ Keyterm Prompting                       | Cloudflare Workers        | RU+          | Дешевле PAYG, 10+ языков                 |
| **Deepgram Nova-3 Multilingual**  | —                    | 0.0092           | API streaming           | ⚠️ Keyterm Prompting                       | —                         | —            | Мультиязычность                         |
| **Gladia** (Async / Real-time)   | 0.02–0.05 (оценка)     | 0.006–0.0125     | API                     | ⚠️ Custom vocab (beta)                     | Solaria ASR               | Хорошо       | Real-time <300 ms, batch — нет док.      |
| **ElevenLabs Scribe v1**         | 0.03–0.1 (оценка)      | 0.0037–0.0067    | API batch               | ⚠️ Keyterms + Entity detection              | Custom STT                | —            | 90+ яз., word timestamps, batch — нет док. |
| **Azure Batch STT**               | 0.1–0.3              | 0.006            | API batch               | ❌ Нет                                      | Enterprise ASR            | Хорошо       | Масштаб batch                           |
| **Google STT v2 Tier 1**          | 0.05–0.15            | 0.016            | API                     | ❌ Нет                                      | Google ASR                | Хорошо       | Tiered pricing (0–500k мин/мес)         |
| **Google STT v2 Dynamic Batch**   | —                    | 0.003            | API batch               | ❌ Нет                                      | Google ASR                | Хорошо       | Плоская ставка batch                    |
| **Google Chirp 3**                | 0.05–0.1             | 0.016 (tier 1)   | API (Speech-to-Text v2) | ❌ Нет                                      | Distilled ASR             | Хорошо       | Chirp 3 в v2 API                        |
| **Any2Text Premium**              | ?                    | ~0.007 (overage) | Web/API?                | ?                                          | Wrapper                   | RU?          | Зависит от провайдера                   |


## Self-hosted модели

> **RTF:** сильно зависит от GPU/CPU. На CPU Whisper легко RTF 0.5–2.0. Замерять на своём железе.

| Модель/Сервис            | RTF (≈)          | Цена ($/мин)    | Развертывание     | Промптинг        | Архитектура                  | RU качество  | Ключ оптимизации                |
| ------------------------ | ---------------- | --------------- | ----------------- | ---------------- | ---------------------------- | ------------ | ------------------------------- |
| **Faster-Whisper turbo** | 0.02–0.1 (GPU)   | Бесплатно + GPU | Self-host         | ⚠️ Как у модели  | CTranslate2                  | Хорошо       | 4–8x ускорение, fp16/int8 quant |
| **WhisperX**             | 0.1–0.3 (GPU)    | Бесплатно       | Self-host         | ⚠️ Как Whisper   | Whisper + VAE align          | Хорошо       | Timestamping, диаризация        |
| **Pisets**               | 0.15–0.25 (GPU); 1.0–1.5 (CPU) | Бесплатно       | Self-host         | ❌ Нет            | Wav2Vec2 + AST + Whisper     | RU лекции    | xRT из [README](https://github.com/bond005/pisets) |
| **GigaAM-v3 (Sber)**     | 0.05–0.15        | Бесплатно       | Self-host         | ❌ Нет            | Conformer CTC                | SOTA RU      | RU pretraining, компактная      |
| **T-one (T-Bank)**       | <0.01 (stream)   | Бесплатно       | Self-host stream  | ❌ Нет            | CTC streaming (70M params)   | RU telephony | 300мс чанки, call-center        |
| **Vosk**                 | 0.2–0.5 (CPU)    | Бесплатно       | Self-host offline | ❌ Нет            | Kaldi-based                  | Средне RU    | 50MB модели, CPU-friendly       |
| **podlodka-turbo**       | 0.03–0.1 (GPU)    | Бесплатно       | Self-host         | ⚠️ Whisper-style | Distilled Whisper            | RU подкасты  | RU fine-tune turbo              |
| **Borealis**             | 0.05–0.2         | Бесплатно       | Self-host         | ✅ LLM-style      | Audio-LLM (Whisper + Qwen4B) | Отлично RU   | Гибкий промпт, пунктуация       |


---

## Глоссарий и уточнения

### 1. Типы промптинга (все — во время декодирования, не постизменение)

| Тип | Как работает | Когда применяется |
|-----|--------------|-------------------|
| **Whisper-style** | Prompt подаётся как **начальный контекст декодеру** (первые 224 токена). Модель «продолжает» текст в том же стиле/орфографии. Не выполняет инструкции, а подражает примеру. | Во время авторегрессивного декодирования |
| **Keyterm prompting** | Список слов/фраз, которые **бустятся в вероятностях** при распознавании (bias в словаре или language model). Специализированные термины, имена, бренды. | Во время декодирования (boost в scoring) |
| **LLM-style** | Свободный текст-инструкция, который модель **понимает и выполняет** («ожидай технические термины», «форматируй списком»). | Во время forward pass, модель обучена следовать инструкциям |

**Итого:** ни один из вариантов не является постизменением — все влияют на процесс генерации токенов.

**Scope промпта (Whisper-style):** `initial_prompt` может применяться только к первому чанку (WhisperX) или ко всему аудио (Fireworks — whole request) или ко всем чанкам через conditioning на предыдущий транскрипт (Faster-Whisper). Для длинного аудио initial-only → терминология может «затухать». Подробнее: [ASR_MODELS_DEEP_DIVE.md §5.3](../guides/ASR_MODELS_DEEP_DIVE.md).

---

### 2. RTF (Real-Time Factor)

**Определение:** `RTF = время_обработки / длительность_аудио`

- **RTF = 0.01** → 1 мин аудио за ~0.6 сек (≈100× быстрее реального времени)
- **RTF = 0.1** → 1 мин аудио за ~6 сек (≈10× быстрее)
- **RTF = 1.0** → realtime (1 мин аудио = 1 мин обработки)
- **RTF > 1** → медленнее realtime

**Чем меньше RTF — тем быстрее.**

---

### 3. Осторожность с RTF

**API batch (pre-recorded):** RTF документирован у Fireworks (turbo 7 с/1 ч = 0.002, large 11 с/1 ч = 0.003; dedicated быстрее). OpenAI: 105 с/1 ч = 0.03 (из сравнения Fireworks). Остальные провайдеры — оценка или streaming TTFT, не batch RTF.

**Self-hosted:** RTF **критично зависит от железа**. Без указания GPU/CPU числа бессмысленны.

| Условия | Типичный RTF Whisper large-v3 | Источник |
|---------|------------------------------|----------|
| **Fireworks turbo serverless** | **0.002** (7 с/1 ч) | [Fireworks blog](https://fireworks.ai/blog/audio-transcription-launch) |
| **Fireworks large serverless** | **0.003** (11 с/1 ч) | [Fireworks blog](https://fireworks.ai/blog/audio-transcription-launch) |
| **OpenAI Whisper API** | **0.03** (105 с/1 ч) | Сравнение Fireworks |
| Groq LPU | ~0.006 (≈164× realtime) | Заявки провайдера |
| **NVIDIA RTX 3070 Ti 8GB**, faster-whisper large-v2 batch=8 | **0.022** | [faster-whisper README](https://github.com/SYSTRAN/faster-whisper) |
| **NVIDIA RTX 3070 Ti 8GB**, faster-whisper large-v2, без batch | 0.081 | [faster-whisper README](https://github.com/SYSTRAN/faster-whisper) |
| GPU (A100/L4/T4), faster-whisper fp16 | 0.02–0.05 | Оценка |
| GPU средний, без батчинга | 0.05–0.1 | Оценка |
| CPU | 0.5–2.0 (часто медленнее realtime) | Типично |

**Рекомендация:** для self-hosted — **замерять на своём железе**: `RTF = время_обработки / длительность_аудио`. Подробнее: [ASR_MODELS_DEEP_DIVE.md §5.5](../guides/ASR_MODELS_DEEP_DIVE.md).

---

## Легенда таблицы

- **Промптинг**: ✅ полный (LLM-style), ⚠️ ограниченный (Whisper/keyterms), ❌ нет.
- **Whisper-style**: prompt до 224 токенов, влияет на стиль/орфографию.
- **LLM-style**: свободный текст, инструкции.
- **Keyterm**: список слов для буста при распознавании.

---

## Источники (март 2025)

> **Примечание:** Источники без URL (Groq, OpenBenchmarking, Any2Text) — цитаты из других источников или оценки; прямую ссылку не удалось проверить.

| Источник | URL | Что взято |
|----------|-----|-----------|
| **Fireworks blog** | [fireworks.ai/blog/audio-transcription-launch](https://fireworks.ai/blog/audio-transcription-launch) | RTF: turbo 3–7 с/1 ч, large 4.5–11 с/1 ч, OpenAI 105 с/1 ч; decoder pruning 32→4; throughput таблица; VAD, alignment, transcoding |
| **Fireworks pricing** | [fireworks.ai/pricing](https://fireworks.ai/pricing) | Цены: turbo $0.0009/мин, large $0.0015/мин |
| **OpenAI pricing** | [openai.com/api/pricing](https://openai.com/api/pricing/) | Цены: Whisper $0.006/мин, GPT-4o Mini Transcribe $0.003/мин |
| **OpenAI Whisper API** | [platform.openai.com/docs/api-reference/audio](https://platform.openai.com/docs/api-reference/audio/createTranscription) | Промптинг: prompt до 224 токенов, decoder context |
| **Deepgram pricing** | [deepgram.com/pricing](https://deepgram.com/pricing) | Цены: Nova-3 $0.0077/мин, Multilingual $0.0092, Keyterm +$0.0013 |
| **Deepgram Keyterm** | [developers.deepgram.com/docs/keyterm](https://developers.deepgram.com/docs/keyterm) | Keyterm prompting, до 100 терминов |
| **Deepgram benchmarks** | [deepgram.com/learn/speech-to-text-benchmarks](https://deepgram.com/learn/speech-to-text-benchmarks), [transcriber.talkflowai.com](https://transcriber.talkflowai.com/blog/deepgram-nova-3-review-benchmarks-pricing) | TTFT 200–300 ms для Nova-3; сравнение с AssemblyAI U2 300–600 ms, OpenAI 500 ms+ |
| **Cloudflare Workers Nova-3** | [developers.cloudflare.com/workers-ai/models/nova-3](https://developers.cloudflare.com/workers-ai/models/nova-3/) | HTTP $0.0052/мин, WebSocket $0.0092/мин, 10+ языков включая RU |
| **Gladia pricing** | [gladia.io/pricing](https://www.gladia.io/pricing) | Async $0.61/ч (Starter), Real-time $0.75/ч; Growth от $0.20/ч; 10 ч free/мес; 100+ яз.; custom vocab (beta); diarization |
| **ElevenLabs pricing** | [elevenlabs.io/pricing/api](https://elevenlabs.io/pricing/api) | Scribe v1/v2: $0.22–0.40/ч по тарифам; keyterm +$0.06/ч, entity +$0.09/ч; 90+ яз. |
| **ElevenLabs STT docs** | [elevenlabs.io/docs/overview/capabilities/speech-to-text](https://elevenlabs.io/docs/overview/capabilities/speech-to-text) | Word timestamps, diarization, SRT/VTT, 2 ч макс |
| **AssemblyAI pricing** | [assemblyai.com/pricing](https://www.assemblyai.com/pricing/) | Universal-3 Pro $0.21/ч = $0.0035/мин, Keyterms +$0.05/ч |
| **AssemblyAI prompting** | [assemblyai.com/docs/streaming/universal-3-pro/prompting](https://www.assemblyai.com/docs/streaming/universal-3-pro/prompting) | Plain language prompt, keyterms до 1000 (6 слов/фраза) |
| **Google Cloud STT** | [cloud.google.com/speech-to-text/pricing](https://cloud.google.com/speech-to-text/pricing) | Tier 1 $0.016/мин, Dynamic Batch $0.003; tiered pricing |
| **Azure Speech** | [azure.microsoft.com/.../speech-services](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/) | Batch STT $0.006/мин; Phrase List, Custom Speech |
| **Faster-Whisper README** | [github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | RTF 0.022 (RTX 3070 Ti, batch=8), 0.081 без batch; 13 мин аудио |
| **GigaAM GitHub** | [github.com/salute-developers/GigaAM](https://github.com/salute-developers/GigaAM) | Архитектура, encoder benchmark (evaluation.md) |
| **GigaAM Sber** | [developers.sber.ru/.../gigaAM-v3](https://developers.sber.ru/kak-v-sbere/culture/gigaAM-v3) | HuBERT-CTC, 700k ч, WER таблица (Golos, RuLS, Callcenter) |
| **T-one Habr** | [habr.com/.../929850](https://habr.com/ru/companies/tbank/articles/929850) | WER телефония (T-one vs GigaAM vs Whisper), 300 ms latency, 71M params |
| **T-one GitHub** | [github.com/voicekit-team/T-one](https://github.com/voicekit-team/T-one) | Архитектура, CTC Conformer |
| **Pisets README** | [github.com/bond005/pisets](https://github.com/bond005/pisets) | RTF 0.15–0.25 GPU, 1.0–1.5 CPU; Wav2Vec2+AST+Whisper |
| **Pisets paper** | [arxiv.org/abs/2601.18415](https://arxiv.org/abs/2601.18415) | NAACL 2025 Industry, лекции/интервью |
| **Vosk** | [alphacephei.com/vosk](https://alphacephei.com/vosk/) | Kaldi, lookahead composition, 50 MB, CPU |
| **Vosk Issue #1007** | [github.com/alphacep/vosk-api/issues/1007](https://github.com/alphacep/vosk-api/issues/1007) | RTF 0.3–0.5 CPU (Ryzen 5 5600G) |
| **podlodka-turbo HF** | [huggingface.co/bond005/whisper-podlodka-turbo](https://huggingface.co/bond005/whisper-podlodka-turbo) | WER по датасетам; fine-tune large-v3-turbo |
| **Borealis HF** | [huggingface.co/Vikhrmodels/Borealis](https://huggingface.co/Vikhrmodels/Borealis) | Audio LLM Whisper+Qwen4B, 7k ч, LLM-style промпт; WER 6.33% (HF benchmark) |
| **alphacephei benchmark** | [alphacephei.com/nsh/2025/04/18/russian-models](https://alphacephei.com/nsh/2025/04/18/russian-models.html) | 11 доменов: GigaAM 8.42%, podlodka 13.78%, Borealis 15.99%, Whisper 16%; телефония Borealis 29% |
| **WhisperX paper** | [arxiv.org/html/2303.00747v2](https://arxiv.org/html/2303.00747v2) | Initial only scope, VAD Cut&Merge, 11.8× speed |
| **Distil-Whisper** | [arxiv.org/abs/2311.00430](https://arxiv.org/abs/2311.00430) | Идея decoder pruning для turbo |
| **GigaAM Habr** | [habr.com/.../973160](https://habr.com/ru/companies/sberdevices/articles/973160/) | Доп. контекст GigaAM v3 |
| **FriendliAI podlodka** | [friendli.ai/model/.../whisper-podlodka-turbo](https://friendli.ai/model/bond005/whisper-podlodka-turbo) | Альтернативный хостинг podlodka |
| **Pisets.com** | [pisets.com](https://pisets.com/) | Коммерческая версия Pisets |
| **Google adaptation** | [cloud.google.com/.../adaptation-model](https://cloud.google.com/speech-to-text/v2/docs/adaptation-model) | PhraseSet, boost |
| **OpenBenchmarking** | — | Vosk RTF 0.3–0.5 (цит. через Vosk Issue #1007) |
| **Groq** | — | RTF ~0.006 — заявки провайдера, URL не найден |
| **Any2Text** | — | Wrapper, ~$0.007 — оценка по агрегаторам, источник не подтверждён |


