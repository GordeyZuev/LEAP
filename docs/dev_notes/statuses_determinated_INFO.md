# Status Determination & Run Validation - INFO

**Документ для будущего обсуждения архитектуры проверок статусов при запуске операций**

**Дата создания:** 2026-02-01
**Статус:** Draft for Discussion

---

## 📋 Контекст

В процессе реализации механизма retry и обработки ошибок возник вопрос о валидации статусов при запуске операций через endpoint `/run`.

---

## 🤔 Вопросы для обсуждения

### **1. Проверка should_allow_run в endpoint /run**

**Текущее поведение:**
- Endpoint `/run` **НЕ проверяет** `should_allow_run(recording)`
- Запускает orchestrator всегда, независимо от статуса

**Вопрос:** Нужно ли добавить проверку?

```python
# Вариант A - добавить проверку:
if not should_allow_run(recording):
    raise HTTPException(400, f"Cannot run from status {recording.status}")

# Вариант B - оставить как есть (текущее поведение):
# Запускать всегда, orchestrator сам разберется
```

---

### **2. Re-run для READY/UPLOADED recordings**

**Use case:** Пользователь хочет переобработать уже готовую запись с другими настройками.

**Вопросы:**
- Разрешать ли запуск `/run` для recordings в статусе `READY`/`UPLOADED`?
- Нужно ли предупреждение в UI?
- Что делать с существующими outputs (перезаписать или создать новые)?

**Варианты:**
```python
# A) Запретить:
if recording.status == ProcessingStatus.READY:
    raise HTTPException(400, "Recording already complete. Use reset first.")

# B) Разрешить с предупреждением:
if recording.status == ProcessingStatus.READY:
    logger.warning(f"Re-running already completed recording {recording_id}")
    # Продолжить

# C) Требовать флаг force:
@router.post("/{id}/run")
async def run_recording(force: bool = False):
    if recording.status == ProcessingStatus.READY and not force:
        raise HTTPException(400, "Use force=true to re-run completed recording")
```

---

### **3. Duplicate processing protection**

**Проблема:** Пользователь может случайно нажать "Run" дважды.

**Вопрос:** Как защитить от дубликатов?

**Варианты:**
```python
# A) Проверка статуса PROCESSING:
if recording.status == ProcessingStatus.PROCESSING:
    raise HTTPException(409, "Recording is already being processed")

# B) Проверка активных задач в Celery:
active_tasks = get_active_tasks_for_recording(recording_id)
if active_tasks:
    raise HTTPException(409, f"Recording has {len(active_tasks)} active tasks")

# C) Idempotency key:
# Требовать X-Idempotency-Key header для /run
```

---

### **4. Status transitions при retry**

**Вопрос:** Нужно ли откатывать статус при retry?

**Текущее поведение:**
- Download failed → status остается `DOWNLOADING`
- После retry download → status переходит в нужный

**Предложение:** Откатывать статус при on_failure():
```python
# Download failure:
recording.status = ProcessingStatus.INITIALIZED  # откат
recording.failed = True

# Transcribe failure:
recording.status = ProcessingStatus.DOWNLOADED  # откат
recording.failed = True
```

---

### **5. should_allow_* функции - единообразие**

**Текущие проверки:**
```python
should_allow_download(recording)  # status == INITIALIZED
should_allow_run(recording)       # status in [DOWNLOADED, PROCESSED]
should_allow_transcription(recording)  # status == PROCESSED + stage check
should_allow_upload(recording, target)  # status >= DOWNLOADED + stages check
```

**Вопрос:** Унифицировать ли логику?

**Предложение:**
```python
# Добавить общий интерфейс:
def should_allow_operation(recording: RecordingModel, operation: str) -> tuple[bool, str]:
    """
    Returns: (allowed, error_message)
    """
    if operation == "download":
        return _check_download(recording)
    elif operation == "run":
        return _check_run(recording)
    # ...
```

---

## 🎯 Рекомендации (для обсуждения)

### **Приоритет 1 - Защита от дубликатов:**
```python
# В /run endpoint:
if recording.status == ProcessingStatus.PROCESSING:
    raise HTTPException(409, "Already processing")
```

### **Приоритет 2 - Re-run для READY:**
```python
# Разрешить с предупреждением:
if recording.status in [ProcessingStatus.READY, ProcessingStatus.UPLOADED]:
    logger.warning(f"Re-running completed recording {recording_id}")
```

### **Приоритет 3 - Откат статусов:**
```python
# Реализовать в on_failure() базового класса
```

---

## 📝 Related Documentation

- [API_GUIDE.md](API_GUIDE.md) - API endpoints reference
- [TECHNICAL.md](TECHNICAL.md) - Processing pipeline
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Status FSM

---

## 🔄 Next Steps

1. **Обсудить с командой** preferred behavior для каждого вопроса
2. **Выбрать подход** для protection от duplicates
3. **Определить policy** для re-run completed recordings
4. **Реализовать проверки** в endpoints
5. **Обновить документацию** с финальными решениями

---

**Автор:** AI Assistant
**Для обсуждения с:** @gazuev
**Приоритет:** Medium
**Ожидаемое время решения:** 1-2 спринта
