# Метрики: полная сводка экспериментов

## 1. Trimming (удаление тишины)

### Метод
- **Инструмент:** FFmpeg `silencedetect`
- **Порог:** -40 dB (дефолт; в статье: -32 dB)
- **Мин. длительность тишины:** 2.0 сек
- **Padding:** 5 сек до/после первого/последнего звука

### Метрики (n=64 записи)

| Метрика | Значение |
|---------|----------|
| Записей с `final_duration` | 64 |
| Среднее обрезание (сек) | 1459 |
| Среднее обрезание (мин) | 24.3 |
| Доля обрезки (%) | 15.53 |
| Суммарно исходное (ч) | 137.1 |
| Суммарно финальное (ч) | 111.2 |
| Удалено (ч) | 25.9 |
| По ffprobe (файлы), % | 13.41 |

---

## 2. Формат аудио

### Метод
- **Вход:** source.mp4 (Zoom AAC)
- **Выход:** MP3 16 kHz, mono, 64 kbps
- **Инструмент:** FFmpeg libmp3lame

### Метрики (n=64)

| Базис сравнения | Метрика | Значение |
|-----------------|---------|----------|
| Vs WAV 48k stereo | Сокращение размера (%) | 95.8 |
| Vs Zoom AAC (~57 kbps) | Сокращение (%) | -11.6 |
| Vs Zoom AAC | Наш битрейт выше (kbps) | 64 vs 57 |
| С учётом trimming | Общее сокращение (%) | 4.4 |
| Суммарный исходный аудио (MB) | 3259.5 |
| Суммарный наш аудио (MB) | 3117.3 |

---

## 3. Fireworks Whisper V3 Turbo — Comprehensive тесты

### Метод
- **Аудио:** ~34 мин (2032 сек), русский, устная речь
- **Дизайн:** 2×2×2×2 (vad × preprocessing × temperature × prompt)
- **Всего комбинаций:** 16
- **Критерий качества:** наличие фразы «доброе утро» в первых 100 символах (`correct_transcription`)

### Таблица метрик по тестам

| ID | vad | prep | temp | prompt | words | segs | unique_t | hall_0% | hall_1% | avg_prob | correct | req_dur(s) |
|----|-----|------|------|--------|-------|------|----------|---------|---------|----------|---------|------------|
| 1 | silero | dynamic | 0 | no | 3928 | 74 | 10 | 17.7 | 82.3 | 0.909 | ❌ | 37.1 |
| 2 | silero | dynamic | 0 | yes | 3699 | 74 | 8 | 15.3 | 84.7 | 0.859 | ❌ | 9.7 |
| 3 | silero | dynamic | 0.01 | no | 3930 | 74 | 10 | 17.7 | 82.3 | 0.910 | ❌ | 5.7 |
| 4 | silero | dynamic | 0.01 | yes | 3703 | 74 | 8 | 15.3 | 84.7 | 0.859 | ❌ | 48.3 |
| 5 | silero | soft_dyn | 0 | no | 4016 | 76 | 10 | 16.4 | 83.6 | 0.914 | ❌ | 19.0 |
| 6 | silero | soft_dyn | 0 | yes | 3727 | 76 | 8 | 16.6 | 83.4 | 0.859 | ❌ | 9.6 |
| 7 | silero | soft_dyn | 0.01 | no | 4005 | 76 | 10 | 16.4 | 83.6 | 0.914 | ❌ | 5.8 |
| 8 | silero | soft_dyn | 0.01 | yes | 3725 | 76 | 8 | 16.6 | 83.4 | 0.859 | ❌ | 11.0 |
| 9 | pyannet | dynamic | 0 | no | 3900 | 88 | 4 | 11.1 | 88.9 | 0.906 | ❌ | 13.1 |
| 10 | pyannet | dynamic | 0 | yes | 3745 | 88 | 4 | 12.6 | 87.4 | 0.855 | ❌ | 6.6 |
| 11 | pyannet | dynamic | 0.01 | no | 3900 | 88 | 4 | 11.2 | 88.8 | 0.905 | ❌ | 8.1 |
| 12 | pyannet | dynamic | 0.01 | yes | 3746 | 88 | 4 | 12.5 | 87.5 | 0.855 | ✅ | 7.0 |
| 13 | pyannet | soft_dyn | 0 | no | 3948 | 87 | 15 | 12.5 | 87.5 | 0.911 | ✅ | 6.4 |
| 14 | pyannet | soft_dyn | 0 | yes | 3708 | 87 | 15 | 13.0 | 87.0 | 0.857 | ✅ | 8.7 |
| 15 | pyannet | soft_dyn | 0.01 | no | 3942 | 87 | 15 | 12.6 | 87.4 | 0.912 | ✅ | 6.3 |
| 16 | pyannet | soft_dyn | 0.01 | yes | 3697 | 87 | 15 | 12.8 | 87.2 | 0.856 | ✅ | 8.7 |

*pyannet = whisperx-pyannet, soft_dyn = soft_dynamic*

### Агрегированные метрики

| Группа | correct (n/16) | phrase_match_rate (%) | avg req_dur (s) | avg unique_t |
|--------|----------------|----------------------|-----------------|-------------|
| silero (все) | 0/8 | 0 | 18.1 | 8.8 |
| whisperx-pyannet (все) | 5/8 | 62.5 | 8.4 | 8.4 |
| dynamic | 1/8 | 12.5 | 16.6 | 6.0 |
| soft_dynamic | 4/8 | 50.0 | 10.2 | 11.3 |
| без prompt | 2/8 | 25.0 | 11.0 | 10.0 |
| с prompt | 3/8 | 37.5 | 15.0 | 6.8 |
| **pyannet + soft_dynamic** | **4/4** | **100** | **7.6** | **15** |

### Фразовые ошибки (первые ~15 слов)

| Гипотеза (text_start) | Ошибки | Интерпретация |
|-----------------------|--------|---------------|
| «Прое утро» | substitution | доброе→прое |
| «Я на лягу» | substitution | вегу→лягу |
| «Яна Яговна» | insertion | разбиение «Я на вегу» |
| «Преутро» | merger | доброе+утро |
| «Я на эго/егану/эгон» | substitution | вегу→эго/егану/эгон |
| «Доброе утро» | 0 | корректно |

---

## 4. Качество и прокси для WER

### Ограничения
- **Reference transcripts:** нет полного эталона для аудио
- **WER:** не вычислялся; требуется ручная разметка или reference
- **Proxy:** `correct_transcription` — бинарная проверка фразы «доброе утро»

### Метрики-прокси

| Метрика | Определение | Значение |
|---------|-------------|----------|
| phrase_match_rate | Доля тестов с «доброе утро» в первых 100 символах | 31.25% (5/16) |
| silero_phrase_acc | phrase_match для vad=silero | 0% |
| pyannet_phrase_acc | phrase_match для vad=whisperx-pyannet | 62.5% |
| soft_dyn_phrase_acc | phrase_match для preprocessing=soft_dynamic | 50% |
| best_config_phrase_acc | pyannet + soft_dynamic | 100% (4/4) |

### Рекомендация для WER
Для оценки WER нужны:
1. Reference transcripts (ручная разметка выборки)
2. Инструмент (например, jiwer)
3. Формула: WER = (S + D + I) / N, где S=substitutions, D=deletions, I=insertions, N=число слов в reference

---

## 5. Alignment и word-level тайминги

### Метод
- **alignment_model:** mms_fa vs tdnn_ffn
- **Оценка:** сопоставление word-level (start, end) с реальным временем начала речи (~5 сек)

### Метрики

| alignment_model | first_word_start (s) | Сдвиг (s) | unique_timings/100 | Проблемы |
|-----------------|---------------------|-----------|---------------------|----------|
| mms_fa | 4.958 | 0 | 4–15 | группировка по сегментам |
| tdnn_ffn | ~24.7 | ~20 | выше | сдвиг ~20 сек |

### Вывод
- **mms_fa:** правильные тайминги; слова в одном сегменте имеют одинаковый start/end
- **tdnn_ffn:** отдельные тайминги на слово, но сдвиг ~20 сек — неприемлемо

---

## 6. Preprocessing (отдельные тесты)

### Метод
- Тест 4 режимов: none, dynamic, soft_dynamic, bass_dynamic
- alignment_model: mms_fa

### Метрики по режимам

| preprocessing | Время (s) | Качество текста | Рекомендация |
|---------------|-----------|------------------|--------------|
| none | 7.9 | среднее | — |
| dynamic | 6.0 | среднее | ⚡ самый быстрый |
| soft_dynamic | 17.3 | лучшее | ✅ для речи |
| bass_dynamic | 10.9 | искажения | ❌ не использовать |

---

## 7. VAD + Prompt (отдельные тесты)

### Метод
- 4 комбинации: silero/pyannet × no prompt/full prompt
- Тестовая фраза: «Доброе утро»

### Метрики

| vad | prompt | Результат | correct |
|-----|--------|-----------|---------|
| silero | no | «Прое утро» | ❌ |
| silero | yes | «Прое утро» | ❌ |
| pyannet | no | пропуск слов | ❌ |
| pyannet | yes | «Доброе утро» | ✅ |

---

## 8. Пайплайн (batch, из BATCH_TESTING)

| Метрика | Значение |
|---------|----------|
| Записей в батче | 24 |
| Суммарный контент (ч) | 42.4 |
| Wall-clock (мин) | 25.8 |
| Throughput (×realtime) | 98.5 |
| Median transcription RT factor | ~170× |
| Best RT factor | 304× |
| Avg слова/сек | ~230 |

---

## 9. Что пробовали и что дало эффект

| Что пробовали | Метод | Эффект |
|---------------|-------|--------|
| vad_model | silero vs whisperx-pyannet | pyannet: 0%→62.5% phrase_match |
| preprocessing | none, dynamic, soft, bass | soft_dynamic: лучшее качество, +11 с |
| prompt | нет vs полный | pyannet без prompt пропускает слова |
| temperature | 0 vs 0.01 | слабый эффект |
| alignment_model | mms_fa vs tdnn_ffn | tdnn_ffn: сдвиг 20 с |
| timestamp_granularities | word, segment | оба нужны; word-тайминги группируются |
| response_format | json vs verbose_json | verbose_json обязателен |

---

## 10. Оптимальная конфигурация (по результатам)

```
vad_model: whisperx-pyannet
alignment_model: mms_fa
preprocessing: soft_dynamic
temperature: 0.0
response_format: verbose_json
timestamp_granularities: ["word", "segment"]
prompt: "Это видео с устной речью. Сохраняй правильное написание..."
```

**Метрики этой конфигурации:** phrase_match 100%, avg req_dur ~7.6 s, unique_timings 15/100
