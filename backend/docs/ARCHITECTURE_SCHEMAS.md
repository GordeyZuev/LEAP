# Архитектурные схемы ZoomUploader / LEAP Platform

Уникальные Mermaid-схемы системы. Каждая диаграмма описывает отдельный аспект архитектуры.

---

## Содержание

1. [POST /run — логика по статусу](#1-post-run--логика-по-статусу)
2. [Recording FSM (State Machine)](#2-recording-fsm-state-machine)
3. [Pause Flow](#3-pause-flow)
4. [Resume Flow](#4-resume-flow)
5. [Zoom Credentials (Master Account)](#5-zoom-credentials-master-account)
6. [Configuration Hierarchy](#6-configuration-hierarchy)
7. [Template Matching](#7-template-matching)
8. [Pipeline: Input Sources → Upload](#8-pipeline-input-sources--upload)
9. [API Layers](#9-api-layers)
10. [Multi-Tenancy](#10-multi-tenancy)
11. [Celery Async Processing](#11-celery-async-processing)
12. [Quota System](#12-quota-system)
13. [Credential Encryption](#13-credential-encryption)
14. [Output Target FSM](#14-output-target-fsm)
15. [Automation Job Flow](#15-automation-job-flow)
16. [Deletion / Retention FSM](#16-deletion--retention-fsm)
17. [Task Chain (run_recording)](#17-task-chain-run_recording)
18. [Storage Structure](#18-storage-structure)
19. [SourceType → Downloader](#19-sourcetype--downloader)
20. [Entity Relationships](#20-entity-relationships)
21. [Общая схема: Credentials, Sources, Presets, Templates, Automation](#21-общая-схема-credentials-sources-presets-templates-automation)

---

## 1. POST /run — логика по статусу

**Упрощённо:** статус определяет действие. Пауза = можно снять; уже идёт = 409; терминальные = 409 или «готово».

```mermaid
flowchart LR
    subgraph Simple[" "]
        A[POST /run] --> B{Статус}
        B --> C[Старт / Продолжить / Retry / Готово / 409]
    end
```

**Подробно:**

```mermaid
flowchart TD
    A[POST /run] --> B{Текущий статус?}
    B -->|INITIALIZED / SKIPPED| C[Полный пайплайн: download → process → upload]
    B -->|DOWNLOADED| D[Пайплайн без download: process → upload]
    B -->|DOWNLOADING / PROCESSING / UPLOADING| E{on_pause?}
    E -->|true| F[Снять паузу, пайплайн продолжится]
    E -->|false| G[409: уже выполняется]
    B -->|PROCESSED / UPLOADED| H{Есть failed/pending uploads?}
    H -->|ДА| I[Перезапуск загрузок]
    H -->|НЕТ| J[Обработка завершена]
    B -->|READY| K[Уже готово]
    B -->|EXPIRED / PENDING_SOURCE| L[409: невозможно]
```

---

## 2. Recording FSM (State Machine)

```mermaid
flowchart LR
    I[INITIALIZED] --> DL[DOWNLOADING]
    DL --> DLD[DOWNLOADED]
    DLD --> P[PROCESSING]
    P --> PD[PROCESSED]
    PD --> U[UPLOADING]
    U --> UD[UPLOADED]
    U --> R[READY]
```

```mermaid
flowchart LR
    subgraph PROCESSING["PROCESSING"]
        T[TRIM] --> TR[TRANSCRIBE] --> E[EXTRACT_TOPICS] --> S[GENERATE_SUBTITLES]
    end
```

**Основной поток:** download → process → upload. При ошибке — откат к предыдущей стадии. Пауза проверяется в DOWNLOADING, PROCESSING, UPLOADING.

---

## 3. Pause Flow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant DB
    participant Task

    User->>+API: POST /recordings/{id}/pause
    API->>User: 202 Accepted
    API->>DB: Set on_pause=true

    loop between stages
        Task->>DB: Check on_pause
        DB-->>Task: on_pause=true
        Task->>Task: Stop pipeline
        Task->>DB: Update status (current stage complete)
    end
```

---

## 4. Resume Flow

**Важно:** Параметр `resume=true` не используется — единый smart `/run` сам определяет действие по статусу. Resume срабатывает, когда статус DOWNLOADING/PROCESSING/UPLOADING и `on_pause=true`.

```mermaid
sequenceDiagram
    participant User
    participant API
    participant DB
    participant Task

    User->>+API: POST /run (status=runtime, on_pause=true)
    API->>DB: Clear on_pause flag
    API->>User: success (pipeline continues)
    Note over Task: Существующая цепочка продолжит после текущей стадии
    Task->>DB: Check on_pause
    DB-->>Task: on_pause=false
    Task->>Task: Continue pipeline
```

---

## 5. Zoom Credentials (Master Account)

**Упрощённо:** один Master Credential создаёт временные креды для каждого под-аккаунта.

```mermaid
flowchart LR
    MAC[Master Credential] --> TC[Temp Creds] --> Z[Zoom API → Recordings]
```

**Подробно:**

```mermaid
flowchart LR
    subgraph User
        U[User]
    end

    subgraph InputSource
        IS[Input Source]
        AID[account_ids: master, sub1, sub2]
        IS --> AID
    end

    subgraph Creds
        MAC[Master Account Credential]
        TC[Temp Credentials]
        MAC -->|client_id + client_secret| TC
    end

    subgraph Zoom
        ZAPI[ZoomAPI instance]
        REC[GET /users/me/recordings]
        DB[(Saves to DB)]
        ZAPI --> REC
        REC --> DB
    end

    U -->|Creates| IS
    U -->|Creates| MAC
    AID -->|per account_id| TC
    TC --> ZAPI
```

---

## 6. Templates, Overrides и Resolution

### 6.0 Упрощённо

```mermaid
flowchart LR
    U[User Config] --> T[Template] --> O[Override] --> F[Final Config]
```

**Идея:** База (User) → дополняет Template (если есть) → перекрывает Override (если задан). Всё мержится, побеждает верхний уровень.

---

### 6.1 Цепочка: Sync → Match → Config → Processing

```mermaid
flowchart TB
    subgraph Sources["Источники конфига"]
        UC[User Config (user_configs)]
        T[Template: rules, processing, output, metadata]
        RO[Recording Override (processing_preferences)]
    end

    subgraph Flow["Жизненный цикл"]
        S[Recording synced] --> M{Template match?}
        M -->|да| B[recording.template_id]
        M -->|нет| U[Unmapped]
        B --> R[ConfigResolver]
        U --> R
    end

    subgraph Merge["Resolution: base → override"]
        direction TB
        R --> M1[1. User Config base]
        M1 --> M2[2. Template Config (если template_id)]
        M2 --> M3[3. Recording Override]
        M3 --> FC[Final Config]
    end

    UC --> M1
    T --> M2
    RO --> M3

    FC --> P[Processing / Upload]
```

### 6.2 Приоритет по типам конфига

| Тип | Order 1 (base) | Order 2 | Order 3 (override) |
|-----|----------------|---------|--------------------|
| **processing_config** | user_config.processing | template.processing_config | recording.processing_preferences |
| **output_config** | user_config.output | template.output_config | processing_preferences.output_config |
| **metadata_config** | user_config.metadata | template.metadata_config | processing_preferences.metadata_config |
| **upload metadata** *(per preset)* | preset.preset_metadata | template.metadata_config | processing_preferences.metadata_config |

Deep merge: каждый следующий уровень перезаписывает поля предыдущего. Вложенные объекты мержатся рекурсивно.

### 6.3 Template Matching

**Упрощённо:** запись проверяется по шаблонам, первый подходящий — побеждает.

```mermaid
flowchart LR
    R[Recording] --> T[Templates] -->|first match| W[template_id]
```

Порядок проверки для каждого шаблона (по `created_at` ASC): `source_ids` → exclude → exact/keywords/patterns.

**Подробно:**

```mermaid
flowchart TD
    A[Recording synced] --> B[For each template by created_at ASC]
    B --> C{source_ids pass?}
    C -->|no| B
    C -->|yes| D{exclude_keywords / patterns}
    D -->|match| B
    D -->|no match| E{exact OR keywords OR patterns}
    E -->|match| F[Template wins, set template_id]
    E -->|no| B
    F --> G[Auto-apply template config]
```

### 6.4 Связь Recording → Template → Presets

```mermaid
flowchart LR
    subgraph Recording
        R[Recording]
        PP[processing_preferences]
        R --> PP
        TID[template_id]
        R --> TID
    end

    subgraph Template
        TM[Template]
        PC[processing_config]
        OC[output_config]
        MC[metadata_config]
        TM --> PC
        TM --> OC
        TM --> MC
        OC -->|preset_ids| PRESETS
    end

    subgraph Presets
        P1[Preset YouTube]
        P2[Preset VK]
        P1 --> PM1[preset_metadata]
        P2 --> PM2[preset_metadata]
    end

    TID -.->|bind| TM
    PP -.->|override| PC
    PP -.->|override| OC
    PP -.->|override| MC
```

**Итог:** Template задаёт обработку и куда выгружать. Recording Override точечно переопределяет настройки для конкретной записи.

---

## 8. Pipeline: Input Sources → Upload

```mermaid
flowchart TB
    subgraph Inputs["Input Sources"]
        Z[Zoom API]
        Y[yt-dlp: YouTube, VK, Rutube]
        YA[Yandex Disk]
        L[Local File]
    end

    subgraph Sync["Sync Layer"]
        ZS[Zoom Sync]
        VS[VIDEO_URL Sync]
        YS[YaDisk Folder Sync]
    end

    subgraph DB
        R[(Recording in DB)]
    end

    subgraph Download["Download Layer"]
        ZD[ZoomDownloader]
        YD[YtDlpDownloader]
        YAD[YandexDiskDownloader]
    end

    subgraph Process["Processing"]
        T[Trim]
        TR[Transcribe]
        TS[Topics + Subtitles]
    end

    subgraph Upload["Upload Targets"]
        YT[YouTube]
        VK[VK Video]
        YDU[Yandex Disk]
    end

    Z --> ZS
    Y --> VS
    YA --> YS
    L -.->|Direct add, no sync| R
    ZS --> R
    VS --> R
    YS --> R
    R --> ZD
    R --> YD
    R --> YAD
    ZD --> T
    YD --> T
    YAD --> T
    T --> TR --> TS
    TS --> YT
    TS --> VK
    TS --> YDU
```

---

## 9. API Layers

```mermaid
flowchart TD
    subgraph Client
        C[REST API + JWT Auth]
    end

    subgraph Service
        RS[RecordingService]
        TS[TemplateService]
        AS[AutomationService]
        CR[CredentialService]
        US[UserService]
        UPS[UploadService]
    end

    subgraph Repository
        REPO[SQLAlchemy ORM (multi-tenant)]
    end

    subgraph Data
        PG[(PostgreSQL)]
    end

    C --> Service
    Service --> REPO
    REPO --> PG
```

---

## 10. Multi-Tenancy

```mermaid
flowchart TD
    subgraph UserA["User A (user_id=1)"]
        A1[recordings]
        A2[templates]
        A3[credentials]
        A4[media/user_1/]
    end

    subgraph UserB["User B (user_id=2)"]
        B1[recordings]
        B2[templates]
        B3[credentials]
        B4[media/user_2/]
    end

    subgraph DB["PostgreSQL"]
        PG[(shared DB, filter by user_id)]
    end

    UserA --> PG
    UserB --> PG
```

---

## 11. Celery Async Processing

**Упрощённо:**

```mermaid
flowchart LR
    API[API] --> T[Task] --> W[Worker] --> DB[DB]
```

**Подробно:**

```mermaid
flowchart LR
    A[API Request] --> B[Create Celery Task]
    B --> C[Return task_id]
    B --> D[Celery Worker]
    D --> E[download → process → transcribe → upload]
    E --> F[Update status in DB]
    F --> G[Client polls GET /tasks/id]

    subgraph Queues["Task Queues"]
        Q1[processing_cpu]
        Q2[downloads]
        Q3[uploads]
        Q4[async_operations]
        Q5[maintenance]
    end
```

---

## 12. Quota System

```mermaid
flowchart TD
    DQ[DEFAULT_QUOTAS (settings)] --> SP[subscription_plans]
    SP --> US[user_subscriptions (plan + overrides)]
    US --> QU[quota_usage (period YYYYMM)]
    QU --> QC[Quota checks before ops]
```

---

## 13. Credential Encryption

```mermaid
flowchart LR
    subgraph Save
        CR[credentials dict] --> ENC[encrypt_credentials] --> CIPHER[ciphertext]
    end

    subgraph Use
        CIPHER2[ciphertext] --> DEC[decrypt_credentials] --> CR2[dict] --> API[External API]
    end
```

**Key:** SECURITY_ENCRYPTION_KEY (Fernet, base64 32 bytes)

---

## 14. Output Target FSM

```mermaid
flowchart LR
    N[NOT_UPLOADED] --> U[UPLOADING]
    U --> OK[UPLOADED]
    U --> F[FAILED]
    F -.->|/run retry| U
```

Один output target (YouTube, VK и т.д.) на запись. FAILED → повтор через `/run`.

---

## 15. Automation Job Flow

**Упрощённо:**

```mermaid
flowchart LR
    J[Job] --> S[Sync sources] --> M[Match templates] --> P[Process]
```

**Подробно:**

```mermaid
flowchart TD
    A[Celery Beat trigger] --> B[Load templates]
    B --> C[Collect source_ids from matching_rules]
    C --> D{source_ids empty?}
    D -->|yes| E[Sync ALL active sources]
    D -->|no| F[Sync specified sources only]
    E --> G[Sync recordings]
    F --> G
    G --> H[Filter by automation filters]
    H --> I[Match recordings with templates]
    I --> J[Process matched recordings]
```

---

## 16. Deletion / Retention FSM

**Упрощённо:**

```mermaid
flowchart LR
    A[active] --> S[soft: файлы] --> H[hard: из БД]
```

**Подробно:**

```mermaid
flowchart LR
    A[active] -->|DELETE / expire_at| S[soft]
    S -->|soft_deleted_at (maintenance)| H[hard]
    H -->|hard_delete_at (maintenance)| X[deleted from DB]

    S -.->|/restore| A
```

**Триггеры:** `expire_at` — auto_expire_recordings_task (3:30 UTC). `soft_deleted_at` — cleanup_recordings_task (удаление файлов). `hard_delete_at` — hard_delete_recordings_task (5:00 UTC).

---

## 17. Task Chain (run_recording_task)

**Упрощённо:**

```mermaid
flowchart LR
    D[download] --> P[process] --> U[upload]
```

**Подробно:**

```mermaid
flowchart LR
    D[download] --> T[trim]
    T --> TR[transcribe]
    TR --> P{parallel}
    P --> E[extract_topics]
    P --> S[generate_subtitles]
    E --> U[launch_uploads]
    S --> U
```

Цепочка Celery: `chain(download, trim, transcribe, group(extract_topics, generate_subtitles), launch_uploads)`. Extract topics и subtitles выполняются параллельно после transcribe.

---

## 18. Storage Structure

**Упрощённо:**

```mermaid
flowchart LR
    U[user_XXXXX] --> R[recordings/id] --> F[source, video, transcriptions]
```

**Подробно:**

```mermaid
flowchart TD
    subgraph storage["storage/"]
        subgraph users["users/"]
            subgraph user["user_000001/"]
                rec["recordings/"]
                thumb["thumbnails/"]
            end
        end
        subgraph shared["shared/"]
            st["thumbnails/"]
        end
        temp["temp/"]
    end

    rec --> r74["74/"]
    r74 --> src["source.mp4"]
    r74 --> vid["video.mp4"]
    r74 --> aud["audio.mp3"]
    r74 --> trans["transcriptions/"]
    trans --> master["master.json"]
    trans --> extr["extracted.json"]
    trans --> srt["subtitles.srt"]
```

---

## 19. SourceType → Downloader

```mermaid
flowchart LR
    Z[ZOOM] --> ZD[ZoomDownloader]
    E[EXTERNAL_URL] --> YD[YtDlpDownloader]
    Y[YOUTUBE] --> YD
    YA[YANDEX_DISK] --> YAD[YandexDiskDownloader]
```

`create_downloader(source_type)` — factory в `video_download_module/factory.py`.

---

## 20. Entity Relationships

```mermaid
erDiagram
    User ||--o{ InputSource : has
    User ||--o{ RecordingTemplate : has
    User ||--o{ OutputPreset : has
    User ||--o{ UserCredential : has
    User ||--o{ Recording : owns

    Recording }o--|| InputSource : from
    Recording }o--o| RecordingTemplate : uses
    Recording ||--o{ OutputTarget : has

    InputSource }o--o| UserCredential : uses
    OutputPreset }o--|| UserCredential : uses

    RecordingTemplate ||--o{ OutputPreset : references
```

---

## 21. Общая схема: Credentials, Sources, Presets, Templates, Automation

### 21.0 Упрощённо

```mermaid
flowchart LR
    C[Credentials] --> IS[Input Sources]
    C --> P[Presets]
    IS --> R[Recordings]
    T[Templates] --> R
    T --> P
    A[Automation] --> T
    A --> IS
```

**Идея:** Credentials питают Sources (откуда) и Presets (куда). Templates матчат Recordings и задают config + presets. Automation запускает Sync из Sources и Process по Templates.

---

### 21.1 Credentials (креды)

Платформа → credential. Используются в Input Sources (sync) и Output Presets (upload).

```mermaid
flowchart TB
    subgraph Platforms["Платформы"]
        Z[Zoom]
        YT[YouTube]
        VK[VK]
        YD[Yandex Disk]
    end

    subgraph Uses["Кто использует"]
        IS[Input Source (sync, скачивание)]
        OP[Output Preset (upload, выгрузка)]
    end

    Z --> IS
    YT --> OP
    VK --> OP
    YD --> IS
    YD --> OP
```

| Платформа | Input Source | Output Preset |
|-----------|--------------|---------------|
| Zoom | ✅ | — |
| YouTube | — | ✅ |
| VK | — | ✅ |
| Yandex Disk | ✅ | ✅ |

---

### 21.2 Input Sources (источники)

Определяют, **откуда** приходят записи. Связаны с credential (кроме LOCAL, VIDEO_URL).

```mermaid
flowchart LR
    IS[Input Source] -->|credential_id| C[Credential]
    IS -->|config| CFG[account_ids, folder, user_emails...]
    IS -->|sync| R[Recordings]
```

**Типы:** ZOOM, YANDEX_DISK, VIDEO_URL, LOCAL.

---

### 21.3 Output Presets (пресеты)

Определяют, **куда** выгружать. Содержат credential + metadata (privacy, description_template и т.д.).

```mermaid
flowchart LR
    OP[Output Preset] -->|credential_id| C[Credential]
    OP -->|preset_metadata| M[privacy, playlist, templates...]
    T[Template] -->|output_config.preset_ids| OP
```

**Платформы:** youtube, vk, yandex_disk.

---

### 21.4 Templates (шаблоны)

Матрчат записи и задают конфиг: как обрабатывать и куда выгружать.

```mermaid
flowchart LR
    T[Template] -->|matching_rules| M[Match Recordings]
    T -->|processing_config| PC[trim, transcribe, topics...]
    T -->|output_config| OC[preset_ids, auto_upload]
    T -->|metadata_config| MC[title, description]
    OC --> P[Presets]
```

---

### 21.5 Automation (автоматизация)

Периодически: Sync из Sources → Match → Process по Templates.

```mermaid
flowchart TD
    A[Automation Job] -->|template_ids| T[Templates]
    T -->|source_ids из matching_rules| IS[Input Sources]
    A -->|schedule| BEAT[Celery Beat]
    BEAT --> SYNC[Sync Sources]
    SYNC --> MATCH[Match Templates]
    MATCH --> PROCESS[Process Recordings]
```

---

### 21.6 Полная схема

```mermaid
flowchart TB
    subgraph User
        U[User]
    end

    subgraph Creds
        C1[Zoom Cred]
        C2[YouTube Cred]
        C3[VK Cred]
    end

    subgraph Input
        IS1[Input Source Zoom]
        IS2[Input Source YaDisk]
    end

    subgraph Presets
        P1[YouTube Preset]
        P2[VK Preset]
    end

    subgraph Templates
        TM[Template]
    end

    subgraph Automation
        AJ[Automation Job]
    end

    U --> C1
    U --> C2
    U --> C3
    C1 --> IS1
    C2 --> P1
    C3 --> P2
    IS1 --> R[(Recordings)]
    IS2 --> R
    TM --> R
    TM --> P1
    TM --> P2
    AJ --> TM
    AJ --> IS1
```

---

## См. также

- [ADR_OVERVIEW.md](ADR_OVERVIEW.md) — Architecture Decision Records
- [TECHNICAL.md](TECHNICAL.md) — Полная техническая документация
- [TEMPLATES_PRESETS_SOURCES_GUIDE.md](guides/TEMPLATES_PRESETS_SOURCES_GUIDE.md) — Templates, Presets, Sources
- [ZOOM_CREDS_GUIDE.md](guides/ZOOM_CREDS_GUIDE.md) — Zoom credentials
- [CREDENTIAL_SECURITY.md](guides/CREDENTIAL_SECURITY.md) — Шифрование credentials
