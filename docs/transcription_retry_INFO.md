# Transcription Retry Strategy - INFO

**Документ для обсуждения архитектуры fallback механизма для транскрибации**

**Дата создания:** 2026-02-01
**Статус:** Draft for Discussion

---

## 📋 Контекст

При реализации обработки ошибок возник вопрос о fallback стратегии для транскрибации.

**Текущее поведение:**
- Fireworks Audio API с двумя моделями:
  - `whisper-v3-turbo` (быстрая, дешевая)
  - `whisper-v3` (медленнее, дороже, точнее)
- Celery retry: `processing_max_retries=2`, delay=180s
- При ошибке - все retry с той же моделью

**Требование:** Попробовать turbo несколько раз, потом prod несколько раз.

---

## 🎯 Цели

1. **Reliability:** Максимизировать вероятность успешной транскрибации
2. **Cost-efficiency:** Сначала дешевые попытки, потом дорогие
3. **Configurability:** Легко настраивать стратегию без изменения кода
4. **Scalability:** Легко добавить новые модели/провайдеры

---

## 💡 Варианты архитектуры

### **Вариант A - Config-Driven Retry Strategy**

**Идея:** Определить стратегию в конфигурации

```python
# config/settings.py или user credentials:
TRANSCRIPTION_RETRY_STRATEGY = {
    "enabled": True,
    "strategies": [
        {
            "provider": "fireworks",
            "model": "whisper-v3-turbo",
            "attempts": 3,
            "retry_delay": 60,  # seconds
            "timeout": 1800  # 30 min
        },
        {
            "provider": "fireworks",
            "model": "whisper-v3",
            "attempts": 2,
            "retry_delay": 120,
            "timeout": 3600  # 60 min
        }
    ]
}
```

**Реализация:**
```python
async def transcribe_with_fallback(audio_path: str, config: dict):
    """Try each strategy in sequence until success"""

    strategies = config.get("transcription_retry_strategy", {}).get("strategies", [])

    for strategy_idx, strategy in enumerate(strategies):
        provider = strategy["provider"]
        model = strategy["model"]
        attempts = strategy["attempts"]
        retry_delay = strategy["retry_delay"]

        logger.info(f"Trying strategy {strategy_idx + 1}/{len(strategies)}: {provider}/{model}")

        for attempt in range(attempts):
            try:
                result = await _transcribe_with_model(audio_path, provider, model)
                logger.info(f"Transcription successful: {provider}/{model} (attempt {attempt + 1})")
                return result

            except Exception as e:
                is_last_attempt = (attempt == attempts - 1)
                is_last_strategy = (strategy_idx == len(strategies) - 1)

                if is_last_attempt and is_last_strategy:
                    # All strategies exhausted
                    raise TranscriptionFailedError(f"All strategies failed. Last error: {e}")

                if is_last_attempt:
                    # Try next strategy
                    logger.warning(f"Strategy {strategy_idx + 1} failed, trying next strategy")
                    break
                else:
                    # Retry same strategy
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {retry_delay}s")
                    await asyncio.sleep(retry_delay)
```

**Плюсы:**
- ✅ Максимальная гибкость
- ✅ Легко добавить новые провайдеры
- ✅ Настраивается без кода
- ✅ Прозрачная логика

**Минусы:**
- ⚠️ Сложнее реализация
- ⚠️ Нужна валидация конфига

---

### **Вариант B - Celery-Native Retry**

**Идея:** Использовать встроенный retry механизм Celery + переключение модели

```python
@celery_app.task(
    bind=True,
    max_retries=5,  # 3 turbo + 2 prod
    default_retry_delay=180
)
def transcribe_recording_task(self, recording_id: int, user_id: str):
    attempt = self.request.retries

    # First 3 attempts: turbo
    if attempt < 3:
        model = "whisper-v3-turbo"
    # Next 2 attempts: prod
    else:
        model = "whisper-v3"

    try:
        result = await transcribe_with_model(audio_path, model)
        return result
    except Exception as e:
        logger.error(f"Transcription failed (attempt {attempt + 1}, model={model}): {e}")
        raise self.retry(exc=e)
```

**Плюсы:**
- ✅ Простая реализация
- ✅ Использует существующую инфраструктуру
- ✅ Автоматический backoff

**Минусы:**
- ⚠️ Hardcoded логика
- ⚠️ Сложно настраивать
- ⚠️ Нельзя добавить новые провайдеры без кода

---

### **Вариант C - Hybrid (Celery + Config)**

**Идея:** Использовать Celery для retry, но модель из конфига

```python
@celery_app.task(bind=True, max_retries=5)
def transcribe_recording_task(self, recording_id: int, user_id: str):
    attempt = self.request.retries

    # Get strategy from config
    strategies = get_transcription_strategies()
    current_strategy = _select_strategy_for_attempt(strategies, attempt)

    try:
        result = await transcribe_with_model(
            audio_path,
            model=current_strategy["model"],
            timeout=current_strategy["timeout"]
        )
        return result
    except Exception as e:
        raise self.retry(exc=e, countdown=current_strategy["retry_delay"])
```

**Плюсы:**
- ✅ Баланс простоты и гибкости
- ✅ Celery управляет retry
- ✅ Config определяет стратегию

**Минусы:**
- ⚠️ Все еще ограничены Celery max_retries

---

## 🎯 Рекомендации

### **Предложение 1: Config-Driven (Вариант A)**

**Обоснование:**
- Максимальная гибкость для будущего
- Можно добавить OpenAI Whisper, Deepgram, и т.д.
- Настройка без деплоя

**Структура конфига:**
```python
# В FireworksConfig или отдельный TranscriptionConfig:
class TranscriptionRetryStrategy(BaseModel):
    provider: Literal["fireworks", "openai", "deepgram"]
    model: str
    attempts: int = Field(ge=1, le=10)
    retry_delay: int = Field(ge=10, le=600)  # seconds
    timeout: int = Field(ge=300, le=7200)  # seconds

class TranscriptionConfig(BaseModel):
    retry_enabled: bool = True
    strategies: list[TranscriptionRetryStrategy]

    # Example:
    # strategies = [
    #     {"provider": "fireworks", "model": "whisper-v3-turbo", "attempts": 3, ...},
    #     {"provider": "fireworks", "model": "whisper-v3", "attempts": 2, ...}
    # ]
```

---

### **Предложение 2: Простое решение (сейчас)**

**Для MVP:** Использовать простой подход без конфига:

```python
# Hardcoded fallback:
async def transcribe_with_simple_fallback(audio_path: str):
    # Try turbo 3 times
    for attempt in range(3):
        try:
            return await transcribe_with_model(audio_path, "whisper-v3-turbo")
        except Exception as e:
            if attempt == 2:
                logger.warning("Turbo failed, trying prod")
            else:
                await asyncio.sleep(60)

    # Try prod 2 times
    for attempt in range(2):
        try:
            return await transcribe_with_model(audio_path, "whisper-v3")
        except Exception as e:
            if attempt == 1:
                raise
            await asyncio.sleep(120)
```

**Потом рефакторить** на Config-Driven когда появится требование на новые провайдеры.

---

## 📊 Сравнение

| Критерий | Config-Driven | Celery-Native | Hybrid | Simple |
|----------|---------------|---------------|--------|--------|
| Гибкость | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ |
| Простота | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Масштабируемость | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ |
| Время реализации | 4h | 1h | 2h | 30min |

---

## 🔄 Next Steps

1. **Выбрать подход** (рекомендую Simple для MVP)
2. **Реализовать базовый fallback** turbo → prod
3. **Протестировать** на реальных данных
4. **Собрать метрики**:
   - Сколько раз turbo успешен
   - Сколько раз нужен prod
   - Средняя стоимость транскрибации
5. **При необходимости** рефакторить на Config-Driven

---

## 📝 Related

- [Fireworks Audio API](https://docs.fireworks.ai/api-reference/audio-transcriptions)
- [TECHNICAL.md](TECHNICAL.md) - Processing pipeline
- `fireworks_module/service.py` - Current implementation
- `config/settings.py` - Celery retry settings

---

## 💡 Future Ideas

**Multi-provider fallback:**
```python
strategies = [
    {"provider": "fireworks", "model": "whisper-v3-turbo"},
    {"provider": "fireworks", "model": "whisper-v3"},
    {"provider": "openai", "model": "whisper-1"},  # Last resort
]
```

**Cost-based selection:**
```python
# Выбирать модель на основе длительности:
if duration < 600:  # < 10 min
    use_turbo  # быстрее и дешевле
else:
    use_prod  # для длинных видео сразу prod
```

**Quality-based retry:**
```python
# Проверять качество результата:
result = transcribe_with_turbo()
if quality_score(result) < 0.7:
    result = transcribe_with_prod()  # retry with better model
```

---

**Автор:** AI Assistant
**Для обсуждения с:** @gazuev
**Приоритет:** High
**Ожидаемое время:** 2-3 спринта (Simple → Config-Driven)
