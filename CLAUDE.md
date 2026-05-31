# LEAP — Agent context

## Project overview

**LEAP** (Lecture Enhancement & Automation Platform) is a **multi-tenant** backend for educational video processing: ingestion (Zoom OAuth, yt-dlp, Yandex Disk, uploads), FFmpeg trimming, ASR (Fireworks/Whisper), topic extraction (DeepSeek), subtitles, and multi-platform upload (YouTube, VK, Yandex, etc.).

**Pipeline:** download → trim (FFmpeg) → transcribe → topics → subtitles → upload. Orchestrated via **Celery** chains and queues: `downloads`, `processing_cpu`, `async_operations`, `uploads`, `maintenance`.

### Repository layout


| Area               | Path                      | Notes                                               |
| ------------------ | ------------------------- | --------------------------------------------------- |
| Application        | `backend/`                | FastAPI, Celery, Alembic, Python ≥ 3.14, `uv`       |
| Package version    | `backend/pyproject.toml`  | `[project].version` is canonical                    |
| Docker / infra     | repo root                 | `docker-compose.yml`, root `Makefile` (Docker-only) |
| Backend tasks      | `backend/Makefile`        | API, Celery queues, DB, lint, tests                 |
| Authoritative docs | `backend/docs/`           | See `INDEX.md`                                      |
| Drafts / internal  | `backend/docs/dev_notes/` | May be outdated; prefer `guides/` + ADR             |


### Backend code layout


| Concern              | Location                                           |
| -------------------- | -------------------------------------------------- |
| FastAPI app, routers | `backend/api/`                                     |
| SQLAlchemy models    | `backend/database/`                                |
| Celery tasks         | `backend/api/tasks/`                               |
| Business logic       | services / repositories alongside existing modules |


### Tooling entrypoint

- Install/sync deps from `backend/`: `uv sync`
- Run API: `make api` from `backend/`
- Default DB name in local/docker: `zoom_manager`

---

## Engineering principles

- **KISS** — prefer the simplest design that solves the problem.
- **DRY** — no duplicated logic without reason; extract when repetition hurts maintenance.
- **YAGNI** — do not build features or abstractions until they are needed.
- **Readability** — optimize for the next reader; avoid speculative "future-proofing."

These apply to **code, APIs, and docs**.

---

## Agent behavior

- **Minimal diffs:** change only what the task requires; no drive-by refactors.
- **Match existing code:** naming, imports (ruff isort first-party list), patterns in neighboring modules.
- **Do not add** unsolicited markdown files; documentation updates follow the rules below.
- Prefer `uv run python` / `make` targets from `backend/` over ad-hoc global Python.

---

## Multi-tenancy and security

- Every API and repository change must **preserve tenant/user isolation** — scope queries with `user_id` / ownership filters like existing code.
- Enforce access with `ResourceAccessValidator`, `TaskAccessService` — do not add bare IDs without checks.
- **OAuth tokens** are stored **encrypted** in the DB; use existing crypto/storage helpers; do not log or persist plaintext tokens.
- Do not log secrets, tokens, or raw credentials. Follow `backend/docs/guides/CREDENTIAL_SECURITY.md` when touching auth or storage.

---

## Storage (S3-first)

Since v0.10.0 all persistent media (`source.mp4`, processed `video.mp4`, `audio.mp3`,
`master.json`, `extracted.json`, subtitle/segment caches, thumbnails) live in the
storage backend — Yandex Object Storage in production, MinIO for local dev.
The local filesystem is used **only** for ephemeral temp files used by FFmpeg /
Fireworks ASR / platform SDKs.

- **DB fields** `local_video_path`, `processed_video_path`, `processed_audio_path`,
  `transcription_dir` hold **storage keys** (not absolute paths).
- **All I/O** goes through `file_storage.get_storage_backend()`. Don't `Path.open()`
  recording artifacts directly — use `storage.save/load/save_file/download_to_file`.
- **Async**: `TranscriptionManager`, `SubtitleGenerator`, `ThumbnailManager` are async.
  Synchronous callers (e.g. Jinja `prepare_recording_context`) must accept
  pre-loaded data via parameters; do not call the manager from sync code.
- **Pipeline pattern** for FFmpeg/ASR: download key → temp → process → upload temp → S3,
  cleanup temp in `finally`. Beat task `maintenance.cleanup_temp_files` sweeps
  orphans hourly.
- **Frontend video** uses presigned URLs from `GET /api/v1/recordings/{id}/media`
  (`{ url, expires_in }`). Don't proxy video bytes through the API.
- **CORS** on the bucket must allow GET from the production frontend origin so
  presigned URLs play in `<video>`.

---

## Local debugging signals

- API / app: `backend/logs/app.log`
- Async Celery worker: `backend/logs/celery-async.log`
- When investigating stuck recordings: relate log lines to **recording id**, **task name**, and **queue**.

---

## Workflow — versions, CHANGELOG, and releases

### Canonical version

- `backend/pyproject.toml` → `[project].version` is the single source of truth (no `v` prefix, e.g. `0.9.6.6`).
- Root `README.md` uses `v` + same semver (e.g. `v0.9.6.6`). Keep them in sync on every release.
- Full sync checklist: `/leap-version-bump`.

### CHANGELOG (`backend/docs/CHANGELOG.md`)

Add entries for user-visible behavior, API contract changes, DB migrations, deployment prerequisites, and breaking changes.

**Structure:**

1. Release block: `## vX.Y.Z (YYYY-MM-DD)` + short summary
2. Dated sections: `## YYYY-MM-DD: Short English title` + bullets with **bold lead-in**
3. `### Файлы` subsection: repo-relative paths touched
4. Deploy / ordering notes when migrations and code must roll out together

**Language:** match surrounding CHANGELOG entries (existing file mixes Russian + technical English).

**Do not put:** purely internal refactors, secrets.

### Documentation cross-updates

When you change behavior, update at least one of:


| Change type                | Update                                                         |
| -------------------------- | -------------------------------------------------------------- |
| REST API surface           | `backend/docs/TECHNICAL.md`, OpenAPI via code                  |
| Auth / OAuth / creds       | `backend/docs/guides/OAUTH.md`, `CREDENTIAL_SECURITY.md`       |
| Celery / workers / queues  | `backend/docs/guides/CELERY_*.md`, `AUTOMATION_CELERY_BEAT.md` |
| Templates / Jinja metadata | `backend/docs/guides/JINJA_METADATA_TEMPLATES.md`              |
| Deployment / env vars      | `backend/docs/guides/DEPLOYMENT.md`, `.env.example`            |


Keep `backend/docs/INDEX.md` accurate if you add new top-level guides.

### Commits and PRs

- Commit messages: **imperative mood**, concise subject; body explains *why* when non-obvious.
- PR description: what changed, how to verify, migration/deploy notes if any.

---

## Python — style, linting, type checking

*(Apply when editing `backend/**/*.py`)*

- **Python:** `>= 3.14` per `backend/pyproject.toml`. **Package manager:** `uv` from `backend/`.
- **Ruff config:** `backend/ruff.toml` — line length 120, double quotes, `target-version = "py311"`.
- **Imports:** isort-compatible; lazy imports only for import cycles or optional heavy deps.
- **Pydantic v2** patterns: `model_validate`, `model_dump`, `Field`.
- **Logging:** use project logging (loguru / middleware patterns); avoid `print` in library/API code.
- `tests/**/*.py` has relaxed Ruff rules; `alembic/versions/*.py` has per-file ignores.

### Commands (from `backend/`)

```bash
make lint           # ruff check .
make lint-fix       # ruff check . --fix && ruff format .
make format         # ruff format .
make typecheck      # uv run python -m ty check
make quality        # lint + typecheck + pytest quality markers
```

### Docstrings and comments

- Write docstrings and comments in **English**.
- Document non-obvious behavior, invariants, side effects (DB, Celery enqueue, external HTTP).
- Comments only when they add real value (non-obvious *why*, hazards, external constraints). Skip comments that restate the code.

---

## Testing

*(Apply when editing `backend/tests/**/*.py`)*

- Config: `backend/pytest.ini` — `testpaths = tests`, `asyncio_mode = auto`, strict markers.
- Tests live under `backend/tests/` mirroring production package structure.

### Markers

`unit`, `integration`, `e2e`, `quality`, `security`, `slow`, `performance`. Register new markers in `pytest.ini`.

### Commands (from `backend/`)


| Target                | Purpose                             |
| --------------------- | ----------------------------------- |
| `make test`           | Full suite                          |
| `make tests-mock`     | Fast: ruff + unit tests             |
| `make tests-quality`  | `pytest tests/quality/ -m quality`  |
| `make tests-security` | `pytest tests/quality/ -m security` |


### Writing tests

- Async: `asyncio_mode = auto` — plain `async def`.
- Fixtures: colocate in `conftest.py`; prefer explicit fixtures.
- DB integration: use project patterns (transactions, test DB URL).
- Celery: prefer unit tests with mocks; mark heavy worker tests `slow`.
- Before merge: at minimum `make tests-mock` + `make lint` + `make typecheck`.

---

## Alembic migrations

*(Apply when editing `backend/alembic/**/*.py`)*

- **DB URL:** `alembic/env.py` uses `DatabaseConfig.from_env()`. Run all commands from `backend/`.
- **Revision ID:** zero-padded **3-digit** string (`"001"` … `"020"`, next `"021"`). Same in `Revision ID:` docstring line.
- **Filename:** `backend/alembic/versions/{revision}_{snake_case_slug}.py`
- **Linear history:** one `down_revision` per revision; no branches unless unavoidable.
- If Alembic emits a non-numeric revision, rename the file and set `revision`/`down_revision` to the next numeric id.

### Commands


| Step              | Command             |
| ----------------- | ------------------- |
| Apply all pending | `make migrate`      |
| Current revision  | `make db-version`   |
| History           | `make db-history`   |
| Roll back one     | `make migrate-down` |


### After `upgrade head`

1. `alembic current` must print the expected revision.
2. `alembic history` must show a single unbroken chain (no multiple heads).
3. For non-trivial migrations: run `tests/unit/alembic/`.

### Before merge

- New file under `alembic/versions/` with numeric `revision` and matching filename.
- Verify `downgrade -1` against a throwaway DB if it's meant to be reversible.
- CHANGELOG must mention revision id(s) + deploy order.

---

## Documentation

*(Apply when editing `backend/docs/**/*.md` or `**/README.md`)*

### Source of truth hierarchy

1. `backend/docs/INDEX.md` — navigation hub; update when adding major docs.
2. `backend/docs/guides/` — how-tos: deployment, OAuth, Celery, integrations, templates, quotas.
3. `backend/docs/TECHNICAL.md` — REST API and technical reference.
4. `backend/docs/ADR_OVERVIEW.md`, `ADR_FEATURES.md` — architecture decisions.
5. `backend/docs/DATABASE_DESIGN.md`, `ARCHITECTURE_SCHEMAS.md` — schema and diagrams.
6. `backend/docs/CHANGELOG.md` — release history.
7. `backend/docs/archive/` — historical / legacy material (do not treat as current runbooks).
8. `backend/docs/dev_notes/` — drafts, TODOs; **never** prefer over `guides/` when they conflict.

### Writing style

- **Audience:** backend operators and contributors. English is primary for new technical prose; existing Russian guides may stay Russian — be consistent within one file.
- **Headings:** hierarchical `##` / `###`; avoid skipping levels.
- **Code blocks:** fenced with language tags (`bash`, `python`, `json`, `sql`).
- **Paths:** repo-relative from repo root or state anchor directory explicitly.
- **Env vars:** document **names and semantics** only; never commit example secrets.

### Do not

- Add stray top-level `.md` files without a clear home in INDEX or `guides/`.
- Duplicate the same procedure in three places — link to one canonical guide.

---

## Version bump — file checklist

*(Apply when editing `README.md`, `backend/pyproject.toml`, `backend/docs/CHANGELOG.md`)*

On every release, update all of:

1. `backend/pyproject.toml` → `[project].version` (no `v`)
2. `backend/api/__init__.py` → `__version__`
3. `backend/config/settings.py` → `AppSettings.version` default
4. `backend/.version` → single line `X.Y.Z`
5. Root `README.md` → version line(s) and `Новое в vX.Y.Z` highlights block
6. `backend/docs/CHANGELOG.md` → new release block

**Grep the previous semver** across the repo to find stale stamps. Do **not** bump document-internal edition numbers (ADR/guide own `Версия:` headers) unless that file tracks the product release.

---

## Available slash commands

- `/leap-version-bump` — ships a product update: business summary, doc audit, version bump everywhere, verification.
- `/leap-release` — short pre-merge release gate: CHANGELOG, migrations, docs, lint, typecheck, tests.
- `/leap-docs-hygiene` — reorganizes docs: canonical locations, INDEX updates, archive vs dev_notes.
- `/leap-debug-pipeline` — debugs stuck or failed recording pipelines: Celery queues, log correlation.
а
