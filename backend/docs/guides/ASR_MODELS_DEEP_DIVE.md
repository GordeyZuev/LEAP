# Глубокий обзор ASR-моделей и статей

Подробное описание русскоязычных моделей, API-сервисов, оптимизированных Whisper-пайплайнов на основе статей, документации и репозиториев.

---

## TL;DR

**Содержание:** §0 Fireworks | §1 API (OpenAI, AssemblyAI, Deepgram, Gladia, ElevenLabs, Azure, Google) | §2 RU ASR (GigaAM, T-one, Vosk, podlodka, Borealis) | §3 Whisper-пайплайны (Faster-Whisper, WhisperX, Pisets) | §4–5 Сводные таблицы, RTF, scope промпта | §6 Ссылки.

**Выводы:**
- **API:** Fireworks — самый быстрый и дешёвый Whisper ($0.0009/мин), whole-request prompt. Для ZoomUploader — оптимальный выбор.
- **Self-hosted RU:** GigaAM-v3 — SOTA по WER; Pisets — лекции/интервью, робастность; podlodka — подкасты; Borealis — пунктуация через LLM.
- **RTF:** API batch — у Fireworks в блоге: turbo **~0.00083–0.002** (3–7 с на 1 ч, dedicated vs serverless / beam), large **~0.00125–0.003** (4.5–11 с на 1 ч); OpenAI 0.03. Streaming (Deepgram, Gladia) — TTFT в мс, не batch RTF. Self-hosted — критично железо; док.: Faster-Whisper (RTX 3070 Ti), Pisets (README), Vosk (CPU).
- **Scope промпта:** Whole request (Fireworks, AssemblyAI, Deepgram) — терминология по всей длине. Initial only (WhisperX) — термины «затухают» в длинном аудио.

**Главная таблица:** [§5.4](#54-единая-плоская-таблица-все-параметры) — все модели в одной таблице (цена, RTF, промптинг, scope, WER).

---

## 0. Fireworks Whisper и оптимизации

**Источники:** [Fireworks Blog](https://fireworks.ai/blog/audio-transcription-launch), [Pricing](https://fireworks.ai/pricing), [Distil-Whisper](https://arxiv.org/abs/2311.00430)

### Whisper-v3-turbo

#### Оптимизация

- **Decoder pruning:** 32 слоя → 4 слоя (как у tiny), идея из Distil-Whisper
- **Метод:** fine-tuning 2 эпохи на тех же мультиязычных данных, что и large-v3 (без translation)
- **Параметры:** ~809M (encoder сохранён, decoder уменьшен)
- **Контекст:** 30 секунд на forward pass

#### Скорость (Fireworks)


| Deployment              | 1 час аудио | RTF (время/длительность) | Throughput         |
| ----------------------- | ----------- | ------------------------- | ------------------ |
| Dedicated turbo beam=1  | 3 сек       | **0.00083**               | 3500 audio min/min |
| Dedicated turbo beam=5  | 6 сек       | 0.00167                  | 700                |
| Serverless turbo beam=5 | 7 сек       | **0.00194**               | Variable           |
| Serverless large beam=5 | 11 сек      | **0.00306**               | Variable           |
| OpenAI Whisper v2       | 105 сек     | **0.029**                 | Variable           |


**20×+ быстрее OpenAI**, 10× дешевле ($0.0009 vs $0.006/мин). RTF = время_обработки / длительность_аудио.

#### Качество

- Сопоставимо с large-v2 по языкам
- Большая деградация на Thai, Cantonese

### Whisper-v3-large (Fireworks)

- Полный encoder-decoder (32 слоя)
- Dedicated: 4.5 сек (beam=1) — 9 сек (beam=5) на 1 час
- Serverless: $0.0015/мин, Batch −40%, Diarization +40%

### Fireworks-специфичные оптимизации

- **Serving stack:** PyTorch-оптимизации, 900× realtime на dedicated
- **VAD:** Silero VAD (до 8000× realtime) — вырезание тишины до ASR
- **Preprocessing:** фильтры (dynamic, soft_dynamic, bass_dynamic) для нестудийного аудио
- **Transcoding:** 7200× realtime (1 час AAC → 0.5 сек)
- **Alignment:** Gentle на GPU, mms_fa, tdnn_ffn — word/sentence timestamps
- **Translate API:** транскрипция + перевод в десятки языков

### Промптинг (Whisper-style)

- **Параметр:** `prompt` (string)
- **Куда подаётся:** в **decoder** как начальный контекст (до 224 токенов у Whisper)
- **Эффект:** стиль, орфография, кастомные слова. Пример: «Um, here's, uh» → модель включит filler words
- **Документация:** [Fireworks API](https://docs.fireworks.ai/api-reference/audio-transcriptions)

---

## 1. API-сервисы (краткий обзор)

### OpenAI Whisper API (whisper-1)

- **Языки:** 99
- **Промптинг:** `prompt` (string) — decoder context, стиль/орфография. Должен соответствовать языку аудио. [Документация](https://platform.openai.com/docs/api-reference/audio/createTranscription)
- **Цена:** $0.006/мин

### OpenAI GPT-4o / GPT-4o Mini Transcribe

- **Языки:** мультиязычный
- **Промптинг:** `prompt` — текст или список ключевых слов (зависит от модели). Не поддерживается в `gpt-4o-transcribe-diarize`
- **Цена:** $0.003/мин (mini), $0.006/мин (full)

### AssemblyAI Universal-3 Pro

- **Языки:** 6 — EN, ES, PT, FR, DE, IT (Universal-2: 99)
- **Промптинг:** два параметра:
  - `prompt` — plain language инструкции (пунктуация, filler words, домен, стиль). Применяется **во время** транскрипции
  - `keyterms_prompt` — массив до 1000 слов/фраз (макс 6 слов на фразу). Буст при распознавании
  - Можно комбинировать, но осторожно с длиной. Streaming: `keyterms` до 100
- **Цена:** $0.21/час, Keyterms +$0.05/час, Streaming keyterms +$0.04/час
- **Документация:** [Prompting](https://www.assemblyai.com/docs/streaming/universal-3-pro/prompting), [Keyterms](https://www.assemblyai.com/docs/pre-recorded-audio/keyterms-prompting)

### Deepgram Nova-3

- **Языки:** 36+ (multilingual, monolingual режимы)
- **Промптинг:** `keyterm` — до 100 терминов в одном запросе. Улучшает Keyword Recall Rate до 90%. Буст при scoring. Nova-2 и старше — `keywords` (другой параметр)
- **Цена:** $0.0077/мин (PAYG), Keyterm +$0.0013/мин
- **Cloudflare Workers AI:** Nova-3 доступен через Workers — HTTP $0.0052/мин, WebSocket $0.0092/мин. 10+ языков, включая RU. Дешевле прямого PAYG.
- **Документация:** [Keyterm Prompting](https://developers.deepgram.com/docs/keyterm), [Cloudflare Nova-3](https://developers.cloudflare.com/workers-ai/models/nova-3/)

### Gladia (v2 / Solaria)

- **Источники:** [Gladia Pricing](https://www.gladia.io/pricing), [Docs](https://docs.gladia.io/)
- **Модели:** Async STT, Real-time (Solaria-1, <300 ms latency)
- **Языки:** 100+
- **Промптинг:** Custom vocabulary (beta) — доменная терминология
- **Цена:** Async $0.61/ч (Starter) = ~$0.01/мин; Growth от $0.20/ч = ~$0.0033/мин. Real-time $0.75/ч (Starter), Growth от $0.25/ч. 10 ч бесплатно/мес.
- **Особенности:** Diarization, word-level timestamps, 25 async / 30 real-time concurrent requests (Starter)

### ElevenLabs Scribe v1 / v2

- **Источники:** [ElevenLabs Pricing](https://elevenlabs.io/pricing/api), [STT Docs](https://elevenlabs.io/docs/overview/capabilities/speech-to-text)
- **Языки:** 90+
- **Промптинг:** Keyterm prompting (+$0.06/ч на Business), Entity detection (+$0.09/ч)
- **Цена:** $0.22–0.40/ч по тарифам (Starter $0.40, Business $0.22) = ~$0.0037–0.0067/мин
- **Особенности:** Word-level timestamps, speaker diarization, SRT/VTT, до 2 ч файл

### Azure Speech

- **Промптинг:** Custom Speech — кастомные модели; Phrase List / grammar — аналог keyterms

### Google Speech-to-Text

- **Промптинг:** `speechContexts` / `phraseSets` — phrase hints с `boost` (0–20). SpeechAdaptation, классы ($ADDRESSNUM и др.)
- **Документация:** [Model adaptation](https://cloud.google.com/speech-to-text/v2/docs/adaptation-model)

---

## 2. Русскоязычные ASR-модели

### 2.1. GigaAM-v3 (Sber / Salute Developers)

**Источники:** [developers.sber.ru](https://developers.sber.ru/kak-v-sbere/culture/gigaAM-v3), [Habr](https://habr.com/ru/companies/sberdevices/articles/973160/), [GitHub](https://github.com/salute-developers/GigaAM)

#### Архитектура

- **Основа:** Conformer-based foundational model, ~220M параметров
- **SSL-претренинг:** HuBERT-CTC — ASR-энкодер как «учитель»; признаки для кластеризации берутся с **последнего слоя** (в отличие от классического HuBERT, где — с промежуточных)
- **Декодеры:** CTC (Connectionist Temporal Classification) и RNN-T (Recurrent Neural Network Transducer)
- **E2E-варианты:** BPE-токенизатор (256 для CTC, 1024 для RNN-T), пунктуация и нормализация в одном проходе

#### Обучение


| Этап                   | Объём                                                                                                                                     |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Неразмеченные данные   | ~700 000 часов (v3) vs ~50 000 (v1/v2)                                                                                                    |
| Размеченные ASR-данные | ~4 000 часов                                                                                                                              |
| Новые домены           | Сложные тексты (950 ч), спонтанная речь (450 ч), телефония (350 ч), зашумлённая речь (110 ч), синтез (100 ч), речь с особенностями (50 ч) |


#### Ключевые техники

- **HuBERT-CTC:** дистилляция от обученного ASR-энкодера; ~10% WER лучше классического HuBERT
- **Данные:** VAD-фильтрация неразмеченных данных; GigaChat Audio для пунктуации и нормализации (in-context learning с 10 примерами)
- **LLM-as-a-judge:** Gemini 2.5 Pro для попарного сравнения транскрипций

#### WER (примерно)


| Датасет             | v3 CTC | v3 RNNT | Whisper | T-one |
| ------------------- | ------ | ------- | ------- | ----- |
| Golos Farfield      | 4.5%   | 3.9%    | 16.4%   | 12.2% |
| Golos Crowd         | 2.8%   | 2.4%    | 19.0%   | 5.7%  |
| Russian LibriSpeech | 4.7%   | 4.4%    | 9.4%    | 6.2%  |
| Callcenter          | 10.3%  | 9.5%    | 23.1%   | 13.5% |
| Disordered Speech   | 20.6%  | 19.2%   | 58.6%   | 51.0% |


**Языки:** только русский (мультиязычная модель в разработке).

**Промптинг:** нет.

**Лицензия:** MIT. Hugging Face, ONNX-экспорт.

---

### 2.2. T-one (T-Bank / VoiceKit)

**Источники:** [Habr](https://habr.com/ru/companies/tbank/articles/929850/), [GitHub](https://github.com/voicekit-team/T-one)

#### Архитектура

- **Тип:** CTC streaming acoustic model на Conformer
- **Размер:** ~71.6M параметров
- **Чанки:** 300 ms; левый контекст ~900 ms (30 фреймов)
- **Вход:** mel-спектрограммы, hop_length = 10 ms

#### Модификации Conformer

- **SwiGLU** вместо стандартного FFN (−3% WERR)
- **SiLU** в Convolution Subsampling (−2% WERR)
- **RMSNorm** вместо LayerNorm (−2% WERR)
- **RoPE** вместо Relative Positional Embedding (−1% WERR, +15% скорость обучения)
- **U-Net-like:** уменьшение временной размерности на 8-м слое в 2×, восстановление на 15-м
- **Переиспользование attention scores:** объединение MHSA-слоев в группы, общий score внутри группы
- **Стейты только на последних 2 слоях** — для ускорения стриминга

#### Обучение

- **Данные:** ~80 000 часов русскоязычного аудио
  - Телефония: 57.9k ч
  - Far-field: 2.2k ч
  - Mix: ~20k ч (часть open source)
- **Pseudo-labeling:** ~64% данных через ансамбль (прод, Whisper, conformer, encoder-decoder) + ROVER

#### Декодер

- **Greedy** или **KenLM beam search** (5-граммная LM)
- **LogprobSplitter:** конец фразы по P(blank) + P(space) > порога

#### Latency

- **Emission latency:** ~330 ms
- **Tail latency:** ~1–1.2 s (emission + silence_duration_threshold 600 ms + overhead)

#### WER (телефония, с LM)


| Домен            | T-one + LM | GigaAM-RNNT | GigaAM-CTC+LM | Vosk   | Whisper large-v3 |
| ---------------- | ---------- | ----------- | ------------- | ------ | ---------------- |
| Колл-центр       | 8.63%      | 10.22%      | 9.29%         | 11.28% | 19.39%           |
| Прочая телефония | 6.20%      | 7.88%       | 7.07%         | 8.69%  | 17.29%           |
| CommonVoice19    | 5.32%      | 2.68%       | 2.76%         | 6.22%  | 5.78%            |


На телефонии T-one лучше GigaAM и Whisper; на CommonVoice — хуже GigaAM.

**Языки:** только русский (телефония).

**Промптинг:** нет; каскад (AM + LM), LM можно менять под домен.

**Лицензия:** Apache 2.0. Triton Inference Server, Docker, примеры дообучения.

---

### 2.3. Vosk (AlphaCephei)

**Источники:** [alphacephei.com](https://alphacephei.com/vosk/), [GitHub](https://github.com/alphacep/vosk-api)

#### Архитектура

- **Основа:** Kaldi
- **Идея:** Lookahead composition — граф декодирования собирается «на лету» из небольших компонентов (лексикон ~20 MB, LM ~20 MB), без единого большого графа (~300 MB и больше)
- **LM:** можно менять на лету без перекомпиляции

#### Особенности

- **Large Signal Database:** база аудио-отпечатков и LSH; поиск похожих чанков при декодировании
- **Масштаб обучения:** до 100k+ часов
- **Обучение:** добавление примеров и дообучение без полного перезапуска

#### Модели

- Маленькие модели (~50 MB), быстрые на CPU
- Поддержка: русский, английский, испанский, китайский и др.
- RTF ~0.2–0.5 на CPU в типичных сценариях

**Языки:** русский, английский, испанский, китайский и др. (многоязычные модели).

**Промптинг:** нет (Kaldi-грамматика, LM).

**Развёртывание:** pip, Docker, WebSocket/gRPC/MQTT/WebRTC, Android/iOS.

---

### 2.4. whisper-podlodka-turbo (bond005)

**Источники:** [HuggingFace](https://huggingface.co/bond005/whisper-podlodka-turbo), [FriendliAI](https://friendli.ai/model/bond005/whisper-podlodka-turbo)

#### База и обучение

- **База:** `openai/whisper-large-v3-turbo`
- **Автор:** Ivan Bondarenko
- **Лицензия:** Apache 2.0
- **Данные:** Common Voice, Podlodka Speech, Russian Librispeech, Sberdevices Golos, Taiga Speech, AudioSet (non-speech)

#### WER (примерно)


| Датасет                    | WER    |
| -------------------------- | ------ |
| Podlodka Speech            | 8.17%  |
| Common Voice RU            | 5.22%  |
| Russian Librispeech        | 9.76%  |
| Sova RuDevices             | 15.35% |
| Sberdevices Golos farfield | 11.61% |
| Sberdevices Golos crowd    | 11.85% |


#### Borealis benchmark (из HuggingFace)


| Модель                 | Средний WER | RuLS   | CV 22.0 | Books  | Speak | Sova   |
| ---------------------- | ----------- | ------ | ------- | ------ | ----- | ------ |
| Borealis               | 6.33%       | 6.39%  | 2.67%   | 5.28%  | 1.95% | 15.37% |
| GigaAM-ASR-V2-RNNT     | 5.85%       | 5.24%  | 2.85%   | 8.06%  | 3.08% | 10.01% |
| **podlodka-turbo**     | **9.38%**   | 11.91% | 6.36%   | 8.96%  | 3.14% | 16.55% |
| whisper-large-v3       | 10.74%      | 11.62% | 7.51%   | 12.19% | 2.74% | 19.65% |
| whisper-large-v3-turbo | 11.30%      | 11.88% | 8.17%   | 13.29% | 2.80% | 20.37% |
| VOSK-model-ru-0.42     | 11.30%      | 12.06% | 11.87%  | 10.80% | 2.61% | 19.15% |


**Языки:** русский, английский.

**Промптинг:** как у Whisper — `prompt` (decoder context). Fine-tune на данных, без отдельного API для промпта.

podlodka-turbo лучше vanilla Whisper на русском, но хуже GigaAM и Borealis.

**Широкий бенчмарк (alphacephei):** [11 доменов](https://alphacephei.com/nsh/2025/04/18/russian-models.html) — podlodka-turbo **13.78%** среднее. Лучше Whisper Large V3 (16.21) и Turbo (16.84); на Golos Farfield 10.9 vs 17.6 у Whisper. GigaAM2 CTC+LM — 8.42% (лидер).

---

### 2.5. Borealis (Vikhrmodels)

**Источники:** [HuggingFace](https://huggingface.co/Vikhrmodels/Borealis)

#### Архитектура

- **Тип:** Audio LLM для ASR на русском
- **Идея:** Voxtral (Whisper encoder + LLM)
- **Обучение:** ~7 000 часов русского аудио
- **Авторы:** Илья Кулешов, Александр Николич (Vikhr Team)

#### Особенности

- Встроенная пунктуация
- Гибкий текстовый промпт (LLM-style)
- Поддержка русского и английского

#### WER (HuggingFace)


| Модель             | Средний WER | RuLS      | CV 22.0   | Books  | Speak     | Sova       |
| ------------------ | ----------- | --------- | --------- | ------ | --------- | ---------- |
| Borealis           | **6.33%**   | 6.39%     | **2.67%** | 5.28%  | **1.95%** | 15.37%     |
| GigaAM-ASR-V2-RNNT | 5.85%       | **5.24%** | 2.85%     | 8.06%  | 3.08%     | **10.01%** |
| whisper-large-v3   | 10.74%      | 11.62%    | 7.51%     | 12.19% | 2.74%     | 19.65%     |


**WER на широком бенчмарке (alphacephei):**

Независимый тест [alphacephei.com](https://alphacephei.com/nsh/2025/04/18/russian-models.html) — 11 доменов (аудиокниги, Golos, Sova, телевещание, медицина, звонки и др.). Borealis: **среднее 15.99%** — сильнее на CommonVoice (2.9), Ru Librispeech (5.9); слабее на телефонии (звонки заказы 29.5%, поддержка 28.9%), телевещании (22.7%). GigaAM2 CTC+LM — 8.42% (лидер).

**Языки:** русский, английский.

**Промптинг:** LLM-style — свободный текст-инструкция в LLM. Audio → encoder → LLM. Единый forward pass.

**Лицензия:** Apache 2.0. Transformers, inference на GPU.

---

## 3. Оптимизированные Whisper-пайплайны

### 3.1. Faster-Whisper (SYSTRAN)

**Источники:** [GitHub](https://github.com/SYSTRAN/faster-whisper), [Issue #9](https://github.com/guillaumekln/faster-whisper/issues/9)

#### Идея

- Реализация Whisper на **CTranslate2**
- Цель: ускорение инференса при сохранении качества

#### Бенчмарки (13 мин аудио)

**Железо:** NVIDIA RTX 3070 Ti 8GB, CUDA 12.4 ([README](https://github.com/SYSTRAN/faster-whisper)).

| Конфигурация                           | Время | VRAM/RAM | RTF ≈  |
| -------------------------------------- | ----- | -------- | ------ |
| openai/whisper large-v2, fp16          | 2m23s | 4708 MB  | 0.184  |
| faster-whisper large-v2, fp16          | 1m03s | 4525 MB  | 0.081  |
| faster-whisper large-v2, batch=8, fp16 | 17s   | 6090 MB  | **0.022** |
| faster-whisper large-v2, int8          | 59s   | 2926 MB  | 0.076  |
| faster-whisper large-v2, int8, batch=8 | 16s   | 4500 MB  | 0.021  |


**Ускорение:** до ~4× vs OpenAI Whisper без batch; с batch=8 — до ~8×.

#### Особенности

- **int8 quantization** на CPU и GPU
- **Batched inference**
- **PyAV** для декодирования аудио (без системного FFmpeg)
- **Mixed int8-float32** (линейные слои в int8, остальное в float32)

**Языки:** 99 (как Whisper).

**Промптинг:** как у Whisper — `prompt` параметр (decoder context).

---

### 3.2. WhisperX (Bain et al., Interspeech 2023)

**Источники:** [arXiv:2303.00747](https://arxiv.org/html/2303.00747v2), [GitHub](https://github.com/m-bain/whisperX)

#### Авторы

Max Bain, Jaesung Huh, Tengda Han, Andrew Zisserman

#### Проблемы Whisper

- Неточные таймстемпы
- Нет word-level таймстемпов
- Буферизованное декодирование не позволяет батчить

#### Архитектура

1. **VAD** (pyannote): сегментация по речи
2. **VAD Cut & Merge:**
  - **Min-cut:** ограничение длины сегментов (max ≈ 30 s) по точке минимума VAD
  - **Merge:** объединение коротких соседних сегментов до τ ≈ 30 s
3. **Whisper:** параллельная транскрипция сегментов (без conditioning на предыдущий текст)
4. **Forced phoneme alignment:** wav2vec2-фонемная модель + DTW → word-level таймстемпы

#### Результаты


| Модель       | TED-LIUM WER | Spd.      | AMI Prec./Rec.  | SWB Prec./Rec.  |
| ------------ | ------------ | --------- | --------------- | --------------- |
| wav2vec2.0   | 19.8         | 10.3×     | 81.8 / 45.5     | 92.9 / 54.3     |
| Whisper      | 10.5         | 1.0×      | 78.9 / 52.1     | 85.4 / 62.8     |
| **WhisperX** | **9.7**      | **11.8×** | **84.1 / 60.3** | **93.2 / 65.4** |


- **IER и 5-Dup:** меньше галлюцинаций и повторений
- **Скорость:** до ~12× за счёт batch + VAD

#### Конфигурация по умолчанию

- VAD: pyannote, onset 0.767, offset 0.377
- Whisper: large-v2, greedy
- Phoneme: wav2vec2 BASE_960H

**Языки:** 99+ (как Whisper) + alignment по языкам phoneme-модели.

**Промптинг:** как у Whisper — decoder prompt.

---

### 3.3. Pisets (NAACL 2025 Industry)

**Источники:** [ACL Anthology](https://aclanthology.org/2025.naacl-industry.74/), [arXiv:2601.18415](https://arxiv.org/abs/2601.18415), [GitHub](https://github.com/bond005/pisets), [pisets.com](https://pisets.com/)

#### Авторы

Ivan Bondarenko, Daniil Grebenkin, Oleg Sedukhin, Mikhail Klementev, Roman Derunets, Lyudmila Budneva (НГУ, Siberian Neuronets)

#### Цель

Робастная система для **лекций и интервью** (русский и английский).

#### Архитектура (3 компонента)

1. **Wav2Vec2:** основной ASR
2. **AST (Audio Spectrogram Transformer):** фильтрация ложноположительных сегментов (не речь)
3. **Whisper:** финальное распознавание

#### Особенности

- Curriculum learning
- Uncertainty modeling
- Устойчивость к длинному аудио и разным условиям
- Аудитория: учёные, журналисты

#### Результаты

- Оценка точности: 95–98% на русском
- Преимущество над WhisperX и базовым Whisper на длинном аудио
- Выход: пунктуация и таймкоды

**Языки:** русский, английский.

**Промптинг:** нет — пайплайн без внешнего промпта.

**Лицензия:** Apache 2.0. Коммерческая версия с UI и интеграциями.

---

## 4. Сводная таблица (краткая)


| Модель         | Тип                     | Домен            | Ключевая фича                | Публикация                 |
| -------------- | ----------------------- | ---------------- | ---------------------------- | -------------------------- |
| GigaAM-v3      | Conformer CTC/RNNT      | Универсальный RU | HuBERT-CTC, E2E пунктуация   | developers.sber, Habr 2025 |
| T-one          | CTC streaming Conformer | Телефония RU     | 300 ms chunks, 71M params    | Habr 2025                  |
| Vosk           | Kaldi                   | Универсальный    | Lookahead composition, CPU   | alphacephei.com            |
| podlodka-turbo | Whisper fine-tune       | Подкасты RU      | fine-tune large-v3-turbo     | HuggingFace                |
| Borealis       | Audio LLM               | RU + EN          | Whisper + Qwen4B, пунктуация | HuggingFace                |
| Faster-Whisper | CTranslate2             | Универсальный    | 4–8× ускорение               | GitHub SYSTRAN             |
| WhisperX       | Pipeline                | Long-form        | VAD + phoneme alignment      | Interspeech 2023           |
| Pisets         | Pipeline                | Лекции, интервью | Wav2Vec2 + AST + Whisper     | NAACL 2025                 |


---

## 5. Полная сравнительная таблица

Все параметры в одной таблице для выбора решения.

### 5.1. API-сервисы


| Модель                            | Цена $/мин          | RTF ≈     | Развёртывание    | Языки  | Промптинг                  | Чем хороша                        | Обучение/оптимизация                |
| --------------------------------- | ------------------- | --------- | ---------------- | ------ | -------------------------- | --------------------------------- | ----------------------------------- |
| **Fireworks Whisper-v3-turbo**    | 0.0009              | **0.00083–0.002** (док., см. §0) | API serverless/dedicated   | 99     | `prompt` (decoder)         | 1 ч за 3–7 с (типично), самая быстрая       | Decoder pruning 32→4, fine-tune     |
| **Fireworks Whisper-v3-large**    | 0.0015              | **0.00125–0.003** (док., см. §0)  | API serverless/dedicated   | 99     | `prompt` (decoder)         | 1 ч за 4.5–11 с                  | Полный Whisper, serving-оптимизации |
| **OpenAI Whisper**                | 0.006               | **0.03** (105 с/1 ч)   | API              | 99     | `prompt` (decoder)         | Эталон, 20× медленнее Fireworks   | Базовый Whisper large-v3            |
| **OpenAI GPT-4o Mini Transcribe** | 0.003               | 0.02–0.05 (оценка)     | API              | Мульти | `prompt` (текст/keywords)  | Дешёвый                           | Multimodal LLM                      |
| **AssemblyAI Universal-3 Pro**    | 0.0035              | 0.02–0.05 (оценка)     | API batch/stream | 6      | `prompt` + `keyterms_prompt` | U2: TTFT 300–600 ms             | Custom ASR                          |
| **Deepgram Nova-3**               | 0.0077              | TTFT 0.2–0.3 с (stream) | API stream       | 36+    | `keyterm` (до 100)         | Streaming, не batch RTF           | C++/CUDA                            |
| **Gladia** (Async / Real-time)    | 0.006–0.0125        | 0.02–0.05 (оценка)      | API              | 100+   | Custom vocab (beta)        | Real-time <300 ms                 | Solaria ASR                         |
| **ElevenLabs Scribe v1**          | 0.0037–0.007        | 0.03–0.1 (оценка)       | API batch        | 90+    | Keyterms, entities         | Batch — RTF не док.               | Custom STT                         |
| **Azure Batch STT**               | 0.006               | 0.1–0.3   | API batch        | 100+   | Phrase List, Custom        | Enterprise, batch                 | Custom models                       |
| **Google STT v2**                 | 0.016 / 0.003 batch | 0.05–0.15 | API              | 125+   | PhraseSet, boost 0–20      | Tiered, Chirp                     | Phrase hints                        |


### 5.2. Self-hosted модели

> **RTF:** зависит от железа. Документированные бенчмарки — [§5.5](#55-rtf-правдивость-и-железо). Рекомендация: замерять на своём GPU/CPU.

| Модель                   | Цена | RTF ≈        | Железо (док.)      | Развёртывание | Языки  | Промптинг              | Чем хороша                    | Обучение/оптимизация          |
| ------------------------ | ---- | ------------ | ------------------ | ------------- | ------ | ---------------------- | ----------------------------- | ----------------------------- |
| **Faster-Whisper turbo** | GPU  | 0.02–0.1     | RTX 3070 Ti (large-v2) | Self-host     | 99     | `prompt` (decoder)     | 4–8× vs Whisper, int8         | CTranslate2, quantization     |
| **WhisperX**             | —    | 0.1–0.3      | GPU <8GB (paper)   | Self-host     | 99+    | `prompt` (decoder)     | Word timestamps, 12× batch    | VAD Cut&Merge, phoneme align  |
| **Pisets**               | —    | 0.15–0.25 GPU; 1.0–1.5 CPU | GPU/CPU (README) | Self-host     | RU, EN | —                      | Лекции, интервью, робастность | Wav2Vec2+AST+Whisper pipeline |
| **GigaAM-v3**            | —    | 0.05–0.15    | Encoder CUDA (eval)   | Self-host     | RU     | —                      | SOTA RU, E2E пунктуация       | HuBERT-CTC, 700k ч, GigaChat  |
| **T-one**                | —    | <0.01 stream | —                 | Self-host     | RU     | —                      | Телефония, streaming 300 ms   | 80k ч, CTC Conformer          |
| **Vosk**                 | —    | 0.2–0.5 CPU  | CPU               | Self-host     | Мульти | —                      | CPU, 50 MB, offline           | Kaldi, lookahead composition  |
| **podlodka-turbo**       | —    | 0.03–0.1     | —                 | Self-host     | RU, EN | `prompt` (decoder)     | RU лучше vanilla Whisper      | Fine-tune large-v3-turbo      |
| **Borealis**             | —    | 0.05–0.2     | —                 | Self-host     | RU, EN | LLM instruction        | Пунктуация, гибкий промпт     | Whisper+Qwen4B, 7k ч          |


### 5.3. Легенда: типы промптинга

- **`prompt` (decoder):** Whisper-style — начальный контекст декодера (~224 токена). Стиль, орфография, термины. Fireworks, OpenAI Whisper, Faster-Whisper, WhisperX, podlodka-turbo.
- **`keyterm` / `keyterms_prompt`:** список слов — буст при scoring. Deepgram (до 100), AssemblyAI (до 1000, 6 слов/фраза).
- **`prompt` (plain language):** инструкции на естественном языке. AssemblyAI Universal-3 — применяется во время транскрипции.
- **PhraseSet / Phrase Hints:** Google, Azure — аналог keyterms, с boost.
- **LLM instruction:** Borealis, GPT-4o Transcribe — свободный текст в multimodal LLM.
- **RTF:** см. [§5.5](#55-rtf-правдивость-и-железо) — для self-hosted критично железо; для API — оценка по latency.

**Scope промпта (применимость по длине аудио):**

- **Full conditioning:** промпт для первого чанка, далее каждый чанк получает предыдущий транскрипт как контекст (~224 токена). Терминология/стиль сохраняются по всей длине. *Faster-Whisper, podlodka-turbo.*
- **Initial only:** промпт только для первого чанка/батча; остальные чанки без внешнего промпта. Типично для параллельного батчинга (VAD-cut → batch transcribe). Терминология может «затухать». *WhisperX*, пайплайны с параллельным Whisper (Pisets — Whisper-этап без conditioning), возможно OpenAI API при батчевой реализации.
- **Whole request:** промпт/keyterms применяются к целому аудио (модель обрабатывает его за один проход или с глобальным контекстом). *AssemblyAI, Deepgram, Azure, Google, Borealis, GPT-4o, Fireworks.*
- **Unknown (API):** внутренняя реализация не документирована. *OpenAI Whisper.*

**Насколько хуже initial only:**

- Для длинного аудио (1 ч ≈ 120 чанков): термины из промпта могут «затухать» в середине и конце — модель не видит их в контексте чанков 2+.
- Для короткого (1–2 чанка): разница минимальна.
- Trade-off: full conditioning иногда усиливает галлюцинации (повтор предыдущего текста); WhisperX специально отключил его ради чистоты.
- Рекомендация: Fireworks (whole request) подходит для терминологии по всей длине; при initial-only (WhisperX и др.) — термины могут «затухать» в длинных роликах.

### 5.4. Единая плоская таблица (все параметры)

Для экспорта, фильтрации, выбора. Строки — все решения; колонки — все атрибуты.


| Модель                        | Тип  | Цена $/мин | RTF   | Развёртывание | Языки  | Промптинг                | Scope промпта      | Сильные стороны          | Как обучалась/улучшалась        | Архитектура        | RU WER ≈   |
| ----------------------------- | ---- | ---------- | ----- | ------------- | ------ | ------------------------- | ------------------ | ------------------------ | ------------------------------- | ------------------ | ---------- |
| Fireworks Whisper-v3-turbo    | API  | 0.0009     | **0.00083–0.002** | Serverless/dedicated    | 99     | `prompt` (decoder)        | Whole request      | 1 ч за 3–7 с (док.)      | Decoder 32→4, [blog](https://fireworks.ai/blog/audio-transcription-launch) | Enc-Dec 4 слоя     | ~10%       |
| Fireworks Whisper-v3-large    | API  | 0.0015     | **0.00125–0.003**  | Serverless/dedicated    | 99     | `prompt` (decoder)        | Whole request      | 1 ч за 4.5–11 с (док.)  | Serving stack, VAD             | Enc-Dec 32 слоя    | ~10%       |
| OpenAI Whisper                | API  | 0.006      | **0.03**        | API           | 99     | `prompt` (decoder)        | Unknown            | 105 с/1 ч (Fireworks)    | 680k ч weak supervise           | Enc-Dec            | ~10%       |
| OpenAI GPT-4o Mini Transcribe | API  | 0.003      | 0.02–0.05       | API           | Мульти | `prompt`                  | Whole request      | Дешево                   | Multimodal LLM                  | LLM                | —          |
| AssemblyAI Universal-3 Pro    | API  | 0.0035     | 0.02–0.05       | API           | 6      | `prompt` + `keyterms_prompt` | Whole request   | Plain language, keyterms | Custom ASR                    | Custom             | —          |
| Deepgram Nova-3               | API  | 0.0077     | TTFT 0.2–0.3 с  | API stream    | 36+    | `keyterm` (до 100)        | Whole request      | Streaming, не batch     | C++/CUDA                        | Nova               | Отлично EN |
| Deepgram Nova-3 (Cloudflare)  | API  | 0.0052     | TTFT ~0.3 с     | Workers AI    | 10+ RU | `keyterm`                 | Whole request      | Дешевле PAYG             | Cloudflare Workers              | Nova               | RU+        |
| Gladia (Async / Real-time)    | API  | 0.006–0.0125 | 0.02–0.05     | API           | 100+   | Custom vocab (beta)       | Whole request      | Real-time <300 ms        | Solaria ASR                     | Custom             | Хорошо     |
| ElevenLabs Scribe v1          | API  | 0.0037–0.007 | 0.03–0.1      | API batch     | 90+    | Keyterms, entities        | Whole request      | Timestamps, batch — нет док. | Custom STT                    | Custom             | —          |
| Azure Batch STT               | API  | 0.006      | 0.1–0.3 | Batch       | 100+   | Phrase List, Custom       | Whole request      | Enterprise               | Custom models                   | Enterprise         | Хорошо     |
| Google STT v2                 | API  | 0.016      | 0.05–0.15 | API       | 125+   | PhraseSet                 | Whole request      | Tiered, Chirp            | Phrase hints                    | Chirp              | Хорошо     |
| Faster-Whisper turbo          | Self | GPU        | 0.02–0.1 | Self        | 99     | `prompt` (decoder)        | Full conditioning  | 4–8× ускорение, 0.022 large-v2 (README)    | CTranslate2, int8  | CTranslate2        | ~10%       |
| WhisperX                      | Self | —          | 0.1–0.3 | Self        | 99     | `prompt` (decoder)        | Initial only       | Word timestamps          | VAD Cut&Merge                   | Whisper+align      | ~10%       |
| Pisets                        | Self | —          | 0.15–0.25       | Self          | RU, EN | —                         | —                 | Лекции, интервью         | Wav2Vec2+AST+Whisper            | Pipeline           | 2–5%       |
| GigaAM-v3                     | Self | —          | 0.05–0.15 | Self    | RU     | —                         | —                 | SOTA RU                  | HuBERT-CTC, 700k ч              | Conformer          | 3–10%      |
| T-one                         | Self | —          | <0.01 | Self          | RU     | —                         | —                 | Телефония                | 80k ч, CTC Conformer            | CTC stream         | 6–9%       |
| Vosk                          | Self | —          | 0.2–0.5 | Self        | Мульти | —                         | —                 | CPU, offline             | Kaldi, lookahead                | Kaldi              | ~11%       |
| podlodka-turbo                | Self | —          | 0.03–0.1 | Self      | RU, EN | `prompt` (decoder)        | Full conditioning  | RU подкасты              | Fine-tune large-v3-turbo        | Whisper            | ~9% (HF); 14% (alphacephei) |
| Borealis                      | Self | —          | 0.05–0.2 | Self      | RU, EN | LLM instruction           | Whole request      | Пунктуация               | Whisper+Qwen4B, 7k ч            | Audio-LLM          | ~6% (HF); 16% (alphacephei) |


**Примечания:** RU WER — ориентировочно по бенчмаркам.

### 5.5. RTF: правдивость и железо

**Насколько правдивы RTF в таблицах:**

| Тип           | Правдивость | Комментарий                                                                                                                                 |
| -------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **API batch**  | Fireworks — док. | RTF из [Fireworks blog](https://fireworks.ai/blog/audio-transcription-launch): turbo 7 с/1 ч = 0.002, large 11 с/1 ч = 0.003; OpenAI 105 с/1 ч = 0.03. Deepgram, Gladia — streaming TTFT (мс), не batch RTF. |
| **API streaming** | TTFT, не RTF | Deepgram Nova-3: TTFT 200–300 ms. Gladia real-time: <300 ms. Batch throughput не публикуется. |
| **Self-hosted**| Зависит от железа | Без указания GPU/CPU значения бессмысленны. RTF на T4 и на A100 отличаются в разы. Ниже — что **документировано** и что **нет**. |

**API batch RTF (документировано):**

| Модель | Условия | RTF | Источник |
|--------|---------|-----|----------|
| Fireworks turbo serverless | 1 ч FLAC mono 16k | **0.002** (7 с/1 ч) | [Fireworks blog](https://fireworks.ai/blog/audio-transcription-launch) |
| Fireworks turbo dedicated beam=1 | 1 ч, 1 FAU | **0.00083** (3 с/1 ч) | Fireworks blog |
| Fireworks large serverless | 1 ч, beam=5 | **0.003** (11 с/1 ч) | Fireworks blog |
| Fireworks large dedicated beam=1 | 1 ч, 1 FAU | **0.00125** (4.5 с/1 ч) | Fireworks blog |
| OpenAI Whisper | 1 ч (сравнение Fireworks) | **0.03** (105 с/1 ч) | Fireworks blog |

**Документированные бенчмарки self-hosted (источник + железо):**

| Модель           | Железо                    | Условия                  | RTF   | Источник |
| ---------------- | ------------------------- | ------------------------ | ----- | -------- |
| Faster-Whisper large-v2 | **NVIDIA RTX 3070 Ti 8GB** | 13 мин аудио, fp16, beam=5 | 0.081 | [README](https://github.com/SYSTRAN/faster-whisper) |
| Faster-Whisper large-v2 | **NVIDIA RTX 3070 Ti 8GB** | 13 мин, fp16, batch=8     | **0.022** | [README](https://github.com/SYSTRAN/faster-whisper) |
| Faster-Whisper large-v2 | **NVIDIA RTX 3070 Ti 8GB** | 13 мин, int8, batch=8     | 0.021 | [README](https://github.com/SYSTRAN/faster-whisper) |
| Faster-Whisper small   | **Intel i7-12700K, 8 threads** | CPU, int8, batch=8     | ~0.14 (13 мин за 51s) | [README](https://github.com/SYSTRAN/faster-whisper) |
| WhisperX large-v2     | GPU, <8GB VRAM            | 70× realtime, batch      | ~0.014 | [Paper](https://arxiv.org/html/2303.00747v2), [README](https://github.com/m-bain/whisperX) — GPU не указан |
| Vosk                 | **CPU** (Ryzen 5 5600G и др.) | 3 мин аудио              | 0.3–0.5 (realtime use) | OpenBenchmarking, [Issue #1007](https://github.com/alphacep/vosk-api/issues/1007) |
| GigaAM (encoder only) | **CUDA** (GPU не указан)      | Encoder: 10 ms / 10 s (bs=1); 324 ms / 128×30 s (bs=128) | Encoder RTF ≈ 0.001 (single); полный pipeline не замерян | [evaluation.md](https://github.com/salute-developers/GigaAM/blob/main/evaluation.md) |
| Pisets                | **GPU** (тип не указан)      | xRT ≈ 0.15–0.25 (зависит от GPU)                        | 0.15–0.25 | [README](https://github.com/bond005/pisets) |
| Pisets                | **CPU**                      | xRT ≈ 1.0–1.5                                           | 1.0–1.5  | [README](https://github.com/bond005/pisets) |

**Не документировано (оценка или экстраполяция):**

| Модель         | Текущий RTF в таблице | Проблема |
| -------------- | --------------------- | -------- |
| GigaAM-v3 (full) | 0.05–0.15           | Encoder замерян; decoder (CTC/RNNT) + железа нет — полный RTF оценка |
| podlodka-turbo | 0.03–0.1              | Нет бенчмарков; ≈ faster-whisper turbo (экстраполяция) |
| Borealis       | 0.05–0.2              | Whisper + Qwen4B; железо не документировано |
| T-one          | <0.01 (stream)        | RTF для streaming 300 ms чанков — другой метрик |

**Рекомендация для self-hosted:**

1. **Замерять на своём железе** — RTF = `время_обработки / длительность_аудио`. Один тест (напр. 10 мин MP3) даст честный результат.
2. **Ориентиры по GPU:** A100/L4 — быстрее T4; RTX 3070 Ti — средний уровень; на CPU Whisper-подобные часто RTF 0.5–2.0.
3. **Не экстраполировать** — «0.05 на RTX 3070» ≠ «0.05 на вашем ноутбуке».

---

## 6. Ссылки и источники (что взято из каждого)

| Источник | URL | Что взято |
|----------|-----|-----------|
| **Fireworks Blog** | [fireworks.ai/blog/audio-transcription-launch](https://fireworks.ai/blog/audio-transcription-launch) | Таблица latency (turbo 3–7 с/1 ч, large 4.5–11 с, OpenAI 105 с); throughput; 900× realtime; decoder pruning; VAD 8000×, transcoding 7200× |
| **Fireworks Pricing** | [fireworks.ai/pricing](https://fireworks.ai/pricing) | $0.0009 turbo, $0.0015 large |
| **Fireworks API** | [docs.fireworks.ai/api-reference/audio-transcriptions](https://docs.fireworks.ai/api-reference/audio-transcriptions) | prompt, decoder context |
| **Distil-Whisper** | [arxiv.org/abs/2311.00430](https://arxiv.org/abs/2311.00430) | Decoder pruning 32→4 |
| **OpenAI Whisper API** | [platform.openai.com/docs/api-reference/audio](https://platform.openai.com/docs/api-reference/audio/createTranscription) | prompt 224 токенов |
| **OpenAI pricing** | [openai.com/api/pricing](https://openai.com/api/pricing/) | $0.006/мин, $0.003 mini |
| **AssemblyAI** | [assemblyai.com/docs](https://www.assemblyai.com/docs/streaming/universal-3-pro/prompting) | prompt + keyterms, 6 языков |
| **Deepgram Keyterm** | [developers.deepgram.com/docs/keyterm](https://developers.deepgram.com/docs/keyterm) | keyterm до 100, KRR 90% |
| **Deepgram Cloudflare** | [developers.cloudflare.com/workers-ai/models/nova-3](https://developers.cloudflare.com/workers-ai/models/nova-3/) | $0.0052 HTTP, 10+ яз. |
| **Deepgram benchmarks** | [transcriber.talkflowai.com](https://transcriber.talkflowai.com/blog/deepgram-nova-3-review-benchmarks-pricing) | TTFT 200–300 ms |
| **Gladia Pricing** | [gladia.io/pricing](https://www.gladia.io/pricing) | $0.61/ч async, $0.75 real-time; 10 ч free |
| **Gladia Docs** | [docs.gladia.io](https://docs.gladia.io/) | Custom vocab (beta), <300 ms |
| **ElevenLabs** | [elevenlabs.io/pricing/api](https://elevenlabs.io/pricing/api) | Scribe $0.22–0.40/ч, keyterm +$0.06 |
| **ElevenLabs STT** | [elevenlabs.io/docs/.../speech-to-text](https://elevenlabs.io/docs/overview/capabilities/speech-to-text) | 90+ яз., timestamps, 2 ч |
| **GigaAM Sber** | [developers.sber.ru/.../gigaAM-v3](https://developers.sber.ru/kak-v-sbere/culture/gigaAM-v3) | HuBERT-CTC, 700k ч, WER таблица |
| **GigaAM GitHub** | [github.com/salute-developers/GigaAM](https://github.com/salute-developers/GigaAM) | MIT, ONNX |
| **GigaAM evaluation** | [evaluation.md](https://github.com/salute-developers/GigaAM/blob/main/evaluation.md) | Encoder RTF benchmark |
| **T-one Habr** | [habr.com/.../929850](https://habr.com/ru/companies/tbank/articles/929850/) | WER колл-центр, 300 ms, 71.6M |
| **T-one GitHub** | [github.com/voicekit-team/T-one](https://github.com/voicekit-team/T-one) | SwiGLU, RoPE, 80k ч |
| **T-one HF** | [huggingface.co/t-tech/T-one](https://huggingface.co/t-tech/T-one) | alphacephei модель |
| **Vosk** | [alphacephei.com/vosk](https://alphacephei.com/vosk/) | Kaldi, lookahead, 50 MB |
| **Vosk Issue #1007** | [github.com/alphacep/vosk-api/issues/1007](https://github.com/alphacep/vosk-api/issues/1007) | RTF 0.3–0.5 CPU |
| **podlodka-turbo** | [huggingface.co/bond005/whisper-podlodka-turbo](https://huggingface.co/bond005/whisper-podlodka-turbo) | WER 6 датасетов, Borealis benchmark |
| **Borealis** | [huggingface.co/Vikhrmodels/Borealis](https://huggingface.co/Vikhrmodels/Borealis) | Whisper+Qwen4B, 7k ч, WER 6.33% |
| **alphacephei** | [alphacephei.com/nsh/2025/04/18/russian-models](https://alphacephei.com/nsh/2025/04/18/russian-models.html) | 11 доменов: GigaAM 8.42%, podlodka 13.78%, Borealis 15.99% |
| **Faster-Whisper** | [github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | RTF 0.022 RTX 3070 Ti |
| **WhisperX paper** | [arxiv.org/html/2303.00747v2](https://arxiv.org/html/2303.00747v2) | Initial only, 11.8×, VAD Cut&Merge |
| **WhisperX GitHub** | [github.com/m-bain/whisperX](https://github.com/m-bain/whisperX) | 70× realtime |
| **Pisets paper** | [arxiv.org/abs/2601.18415](https://arxiv.org/abs/2601.18415) | Wav2Vec2+AST+Whisper, 95–98% |
| **Pisets GitHub** | [github.com/bond005/pisets](https://github.com/bond005/pisets) | xRT 0.15–0.25 GPU, 1.0–1.5 CPU |
| **Pisets ACL** | [aclanthology.org/2025.naacl-industry.74](https://aclanthology.org/2025.naacl-industry.74/) | NAACL 2025 |
| **Pisets.com** | [pisets.com](https://pisets.com/) | Коммерческая версия |
| **GigaAM Habr** | [habr.com/.../973160](https://habr.com/ru/companies/sberdevices/articles/973160/) | Доп. контекст GigaAM v3 |
| **FriendliAI** | [friendli.ai/.../whisper-podlodka-turbo](https://friendli.ai/model/bond005/whisper-podlodka-turbo) | podlodka альтернативный хостинг |
| **Faster-Whisper Issue #9** | [github.com/guillaumekln/faster-whisper/issues/9](https://github.com/guillaumekln/faster-whisper/issues/9) | История/контекст (fork) |
| **Google adaptation** | [cloud.google.com/.../adaptation-model](https://cloud.google.com/speech-to-text/v2/docs/adaptation-model) | PhraseSet, SpeechAdaptation |
| **Deepgram pricing** | [deepgram.com/pricing](https://deepgram.com/pricing) | $0.0077, Keyterm +$0.0013 |
| **deepgram.com/learn** | [deepgram.com/learn/speech-to-text-benchmarks](https://deepgram.com/learn/speech-to-text-benchmarks) | Официальные бенчмарки |


