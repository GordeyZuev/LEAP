# Run & Resume Strategy - INFO

**Документ для обсуждения архитектуры Smart Resume и унификации retry механизма**

**Дата создания:** 2026-02-01  
**Статус:** Draft for Discussion

---

## 📋 Контекст

В процессе реализации error handling возникли вопросы:
1. Как реализовать "Smart Resume" для `/run` endpoint
2. Нужен ли отдельный `/retry-upload` или достаточно `/run`
3. Как избежать дублирования логики retry

---

## 🎯 Цели

### **Smart Resume**
Возможность продолжить обработку с места остановки (failure/interruption):
- Recording failed at download → resume продолжит с download
- Recording failed at transcribe → resume продолжит с transcribe
- Partial upload (1 success, 1 failed) → resume доделает failed upload

### **Unified Retry**
Единый механизм retry через `/run` вместо множества специализированных endpoints:
- ❌ `/download` + `/transcribe` + `/upload/{platform}` + `/retry-upload`
- ✅ `/run` с флагом `resume=true` который умеет всё

---

## 🔍 Текущее Состояние

### **Существующие Endpoints:**

```python
POST /recordings/{id}/download        # Download only
POST /recordings/{id}/transcribe      # Transcribe only
POST /recordings/{id}/upload/{platform}  # Upload to specific platform
POST /recordings/{id}/retry-upload    # Retry failed uploads
POST /recordings/{id}/run             # Full pipeline orchestrator
```

### **Проблемы:**

1. **Дублирование логики** - каждый endpoint проверяет статусы по-своему
2. **Неочевидно для UI** - непонятно какой endpoint использовать для retry
3. **retry-upload vs run** - зачем отдельный endpoint если `/run` может доделать?
4. **Нет resume** - `/run` всегда начинает заново или пытается продолжить?

---

## 💡 Архитектурные Варианты

### **Вариант A: Smart Resume в /run (Recommended)**

**Концепция:**
```python
POST /recordings/{id}/run?resume=true
```

**Поведение:**
```python
def run_recording(recording_id: int, resume: bool = False):
    recording = get_recording(recording_id)
    
    if resume:
        # Smart Resume: продолжить с места остановки
        return _resume_from_current_state(recording)
    else:
        # Full Re-run: начать с начала (download)
        return _run_full_pipeline(recording)

def _resume_from_current_state(recording):
    """Resume from current status/stage."""
    
    # 1. Download не завершён
    if recording.status in [INITIALIZED, DOWNLOADING]:
        if recording.failed and recording.failed_at_stage == "download":
            return download_task.delay(recording_id)
        return download_task.delay(recording_id)
    
    # 2. Processing stages не завершены
    if recording.status in [DOWNLOADED, PROCESSING]:
        # Check which stages need to run
        pending_stages = get_pending_stages(recording)
        return run_processing_pipeline(recording, stages=pending_stages)
    
    # 3. Upload не завершён или partial
    if recording.status in [PROCESSED, UPLOADING, UPLOADED]:
        failed_outputs = get_failed_outputs(recording)
        not_uploaded = get_not_uploaded_outputs(recording)
        
        targets = failed_outputs + not_uploaded
        if targets:
            return upload_targets(recording, targets)
        
        # Already complete
        return {"status": "complete", "message": "Nothing to resume"}
    
    # 4. Already READY
    if recording.status == READY:
        return {"status": "complete", "message": "Recording already complete"}
```

**Преимущества:**
- ✅ **Один endpoint для всего** - понятно и просто
- ✅ **Умный retry** - автоматически определяет что доделать
- ✅ **Экономия ресурсов** - не перезапускает то что уже сделано
- ✅ **Идеален для UI** - одна кнопка "Continue/Resume"

**Недостатки:**
- ⚠️ Чуть сложнее логика внутри
- ⚠️ Нужна хорошая документация поведения

---

### **Вариант B: Отдельные endpoints для каждого stage (Current)**

**Сохранить текущую структуру:**
```python
POST /recordings/{id}/download        # Retry download
POST /recordings/{id}/transcribe      # Retry transcribe
POST /recordings/{id}/upload/{platform}  # Retry single upload
POST /recordings/{id}/retry-upload    # Retry all failed uploads
POST /recordings/{id}/run             # Full pipeline
```

**Преимущества:**
- ✅ Гранулярный контроль для advanced users
- ✅ Проще логика в каждом endpoint

**Недостатки:**
- ❌ **Дублирование кода** - проверки статусов в каждом endpoint
- ❌ **Запутанно для UI** - какой endpoint использовать?
- ❌ **Не масштабируемо** - при добавлении stage нужен новый endpoint
- ❌ **Нарушает DRY** - retry логика размазана по endpoints

---

### **Вариант C: Гибридный (Compromise)**

**Комбинация:**
```python
# Основной - Smart Resume
POST /recordings/{id}/run?resume=true   # Main retry mechanism

# Оставить для advanced cases
POST /recordings/{id}/upload/{platform}  # Force upload to specific platform
```

**Логика:**
- 95% случаев → `/run?resume=true` (UI использует это)
- 5% advanced → `/upload/{platform}` (API для особых случаев)
- Убрать: `/retry-upload`, `/download`, `/transcribe` (дублируют `/run`)

**Преимущества:**
- ✅ Простота для обычных пользователей
- ✅ Гибкость для advanced scenarios
- ✅ Меньше дублирования кода

---

## 🏗️ Предлагаемая Реализация

### **1. Добавить resume parameter в /run**

```python
@router.post("/{recording_id}/run")
async def run_recording(
    recording_id: int,
    resume: bool = Query(False, description="Resume from current state instead of re-run"),
    manual_override: dict | None = None,
    ctx: ServiceContext = Depends(get_service_context),
):
    """
    Run recording processing pipeline.
    
    Args:
        resume: If True, continue from current state (smart resume).
                If False, start from beginning (full re-run).
    
    Examples:
        - Recording failed at download → resume will retry download
        - Recording failed at transcribe → resume will continue from transcribe
        - Partial upload (1/2 platforms) → resume will upload to failed platform
        - Recording complete → resume returns "nothing to do"
    """
    recording_repo = RecordingRepository(ctx.session)
    recording = await recording_repo.get_by_id(recording_id, ctx.user_id)
    
    if not recording:
        raise HTTPException(404, "Recording not found")
    
    if resume:
        # Smart Resume
        result = await _smart_resume(recording, ctx)
    else:
        # Full pipeline
        result = await _run_full_pipeline(recording, manual_override, ctx)
    
    return result
```

### **2. Реализовать _smart_resume()**

```python
async def _smart_resume(recording: RecordingModel, ctx: ServiceContext):
    """
    Smart Resume: determine current state and continue from there.
    
    State Machine:
    1. INITIALIZED/SKIPPED → start download
    2. DOWNLOADING (failed) → retry download
    3. DOWNLOADED → start processing (trim/transcribe)
    4. PROCESSING (failed at stage) → retry failed stage
    5. PROCESSED → start uploads
    6. UPLOADING/UPLOADED (partial) → retry failed uploads
    7. READY → nothing to do
    """
    from api.tasks.processing import download_recording_task, run_recording_task
    from api.tasks.upload import upload_recording_to_platform
    
    # 1. Download phase
    if recording.status in [ProcessingStatus.INITIALIZED, ProcessingStatus.SKIPPED]:
        task = download_recording_task.delay(recording.id, ctx.user_id, force=False)
        return {"task_id": task.id, "phase": "download", "resumed": False}
    
    if recording.status == ProcessingStatus.DOWNLOADING:
        # Failed download - retry
        if recording.failed and recording.failed_at_stage == "download":
            task = download_recording_task.delay(recording.id, ctx.user_id, force=True)
            return {"task_id": task.id, "phase": "download", "resumed": True, "retry": True}
        # Still downloading - return existing task
        return {"message": "Download already in progress", "phase": "download"}
    
    # 2. Processing phase
    if recording.status in [ProcessingStatus.DOWNLOADED, ProcessingStatus.PROCESSING]:
        # Check if any stages failed or pending
        has_failed = any(s.status == ProcessingStageStatus.FAILED for s in recording.processing_stages)
        has_pending = any(s.status == ProcessingStageStatus.PENDING for s in recording.processing_stages)
        
        if has_failed or has_pending or recording.status == ProcessingStatus.DOWNLOADED:
            # Resume processing from current point
            task = run_recording_task.delay(recording.id, ctx.user_id)
            return {"task_id": task.id, "phase": "processing", "resumed": True}
        
        return {"message": "Processing already in progress", "phase": "processing"}
    
    # 3. Upload phase
    if recording.status in [ProcessingStatus.PROCESSED, ProcessingStatus.UPLOADING, ProcessingStatus.UPLOADED]:
        # Find failed or not-uploaded outputs
        failed_outputs = [o for o in recording.outputs if o.status == TargetStatus.FAILED]
        pending_outputs = [o for o in recording.outputs if o.status == TargetStatus.NOT_UPLOADED]
        
        targets_to_upload = failed_outputs + pending_outputs
        
        if targets_to_upload:
            # Resume uploads
            tasks = []
            for output in targets_to_upload:
                platform = output.target_type.value.lower()
                task = upload_recording_to_platform.delay(
                    recording.id, 
                    ctx.user_id, 
                    platform,
                    preset_id=output.preset_id
                )
                tasks.append({"platform": platform, "task_id": task.id})
            
            return {
                "phase": "upload",
                "resumed": True,
                "tasks": tasks,
                "message": f"Resuming {len(tasks)} failed/pending uploads"
            }
        
        # Check if already complete
        if recording.status == ProcessingStatus.READY:
            return {"message": "Recording already complete", "phase": "complete", "resumed": False}
        
        # In progress
        return {"message": "Upload already in progress", "phase": "upload"}
    
    # 4. Already complete
    if recording.status == ProcessingStatus.READY:
        return {"message": "Recording already complete. Use resume=false to re-run.", "phase": "complete"}
    
    # Unknown state
    return {"message": f"Cannot resume from status {recording.status.value}", "error": True}
```

### **3. Удалить/Deprecate дублирующие endpoints**

```python
# УДАЛИТЬ (заменены на /run?resume=true):
# POST /recordings/{id}/retry-upload  → use /run?resume=true
# POST /recordings/{id}/download       → use /run?resume=true
# POST /recordings/{id}/transcribe     → use /run?resume=true

# ОСТАВИТЬ для advanced use-cases:
# POST /recordings/{id}/upload/{platform}  - force upload to specific platform
# POST /recordings/{id}/run                - orchestrator (resume parameter added)
```

---

## 📊 Comparison Matrix

| Feature | Current (Multiple Endpoints) | Variant A (Smart Resume) | Variant C (Hybrid) |
|---------|------------------------------|--------------------------|-------------------|
| **Код дублирование** | ❌ Высокое | ✅ Минимальное | ✅ Низкое |
| **UI Complexity** | ❌ 5+ кнопок | ✅ 1 кнопка | ✅ 1-2 кнопки |
| **API понятность** | ⚠️ Средняя | ✅ Высокая | ✅ Высокая |
| **Гранулярность** | ✅ Полная | ⚠️ Автоматическая | ✅ Опциональная |
| **Масштабируемость** | ❌ Плохая | ✅ Отличная | ✅ Хорошая |
| **DRY принцип** | ❌ Нарушен | ✅ Соблюдён | ✅ Соблюдён |

---

## 🎯 Рекомендация

### **Реализовать Вариант C (Hybrid):**

1. **Добавить `resume` parameter в `/run`**
   - Default: `resume=false` (backward compatible)
   - `resume=true` → Smart Resume behavior

2. **Оставить `/upload/{platform}`**
   - Для force upload на конкретную платформу
   - Для advanced API usage

3. **Удалить endpoints:**
   - ❌ `/retry-upload` → заменён на `/run?resume=true`
   - ❌ `/download` → заменён на `/run?resume=true`
   - ❌ `/transcribe` → заменён на `/run?resume=true`

4. **UI Guidelines:**
   - **"Continue"** button → `POST /run?resume=true`
   - **"Restart"** button → `POST /run?resume=false`
   - **"Upload to {platform}"** → `POST /upload/{platform}` (advanced)

---

## 🔄 Migration Strategy

### **Phase 1 - Add resume (non-breaking):**
```python
# Add resume parameter, default=false (existing behavior)
POST /run?resume=false  # Current behavior (re-run)
POST /run?resume=true   # New behavior (smart resume)
```

### **Phase 2 - Deprecate old endpoints:**
```python
# Mark as deprecated in OpenAPI spec
@deprecated(message="Use /run?resume=true instead")
POST /retry-upload
POST /download
POST /transcribe
```

### **Phase 3 - Update UI:**
```typescript
// Old:
if (recording.failed) {
  if (recording.failed_at_stage === 'download') {
    api.post(`/recordings/${id}/download`);
  } else if (recording.failed_at_stage === 'upload') {
    api.post(`/recordings/${id}/retry-upload`);
  }
}

// New:
if (recording.failed || recording.status !== 'READY') {
  api.post(`/recordings/${id}/run?resume=true`);
}
```

### **Phase 4 - Remove deprecated (v2.0):**
```python
# Complete removal in next major version
```

---

## 📝 Examples

### **Example 1: Download Failed**
```bash
# Recording: status=INITIALIZED, failed=true, failed_at_stage="download"

POST /recordings/123/run?resume=true
→ Starts download task
→ Returns: {"task_id": "abc", "phase": "download", "resumed": true}
```

### **Example 2: Transcribe Failed**
```bash
# Recording: status=DOWNLOADED, failed=true, failed_at_stage="transcribe"

POST /recordings/123/run?resume=true
→ Starts processing pipeline from transcribe
→ Returns: {"task_id": "def", "phase": "processing", "resumed": true}
```

### **Example 3: Partial Upload**
```bash
# Recording: status=UPLOADED, outputs=[
#   {platform: "youtube", status: "UPLOADED"},
#   {platform: "vk", status: "FAILED"}
# ]

POST /recordings/123/run?resume=true
→ Retries only VK upload
→ Returns: {
    "phase": "upload",
    "resumed": true,
    "tasks": [{"platform": "vk", "task_id": "ghi"}]
  }
```

### **Example 4: Already Complete**
```bash
# Recording: status=READY

POST /recordings/123/run?resume=true
→ Returns: {"message": "Recording already complete", "phase": "complete"}

POST /recordings/123/run?resume=false
→ Starts full re-run from download
→ Returns: {"task_id": "jkl", "phase": "download", "resumed": false}
```

---

## 🧪 Testing Scenarios

1. ✅ **Resume after download failure** → retries download
2. ✅ **Resume after trim failure** → continues from trim
3. ✅ **Resume after transcribe failure (allow_errors=false)** → retries transcribe
4. ✅ **Resume after transcribe failure (allow_errors=true)** → skips to upload
5. ✅ **Resume with partial upload** → retries only failed platforms
6. ✅ **Resume when complete** → returns "nothing to do"
7. ✅ **Full re-run** → starts from download regardless of status
8. ✅ **Resume during active processing** → returns "in progress"

---

## 📚 Related Documentation

- [ERROR_HANDLING_IMPLEMENTATION.md](ERROR_HANDLING_IMPLEMENTATION.md) - Error handling infrastructure
- [statuses_determinated_INFO.md](statuses_determinated_INFO.md) - Status validation
- [TECHNICAL.md](TECHNICAL.md) - Processing pipeline
- [API_GUIDE.md](API_GUIDE.md) - API reference

---

## ✅ Action Items

- [ ] Implement `resume` parameter in `/run` endpoint
- [ ] Implement `_smart_resume()` helper function
- [ ] Add tests for all resume scenarios
- [ ] Mark old endpoints as deprecated in OpenAPI
- [ ] Update UI to use `/run?resume=true`
- [ ] Document new behavior in API_GUIDE.md
- [ ] Remove deprecated endpoints in v2.0

---

**Автор:** AI Assistant  
**Для обсуждения с:** @gazuev  
**Приоритет:** High  
**Ожидаемое время:** 1-2 дня реализации
