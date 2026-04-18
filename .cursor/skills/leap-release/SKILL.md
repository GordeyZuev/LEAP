---
name: leap-release
description: >-
  Runs a short LEAP pre-merge release gate—CHANGELOG, migrations, docs
  touchpoints, lint, typecheck, tests. Use when the version bump and README
  narrative are already handled (e.g. via leap-version-bump) or for a quick
  final checklist before merge.
---

# LEAP release checklist

For **README narrative**, **exhaustive version grep**, and **doc freshness** after a feature drop, prefer **`leap-version-bump`** first; this file stays a **short** merge checklist.

Follow **`workflow-changelog.mdc`** and **`alembic-migrations.mdc`** (project rules) for format details. Execute steps from `backend/` unless noted.

## Checklist

1. **Version**
   - [ ] Set `[project].version` in `backend/pyproject.toml` (canonical).
   - [ ] Match **`backend/api/__init__.py`** `__version__`, **`backend/config/settings.py`** version default, **`backend/.version`**, and root **`README.md`** `v…` lines to the same semver (full pass: **`leap-version-bump`**).

2. **Changelog**
   - [ ] Add `backend/docs/CHANGELOG.md` entry: release header `## vX.Y.Z (YYYY-MM-DD)` and/or dated sections per existing style.
   - [ ] Call out **DB revision ids** (e.g. `020`) and **deploy order** if code and migrations must roll out together.

3. **Migrations (if any)**
   - [ ] New file in `backend/alembic/versions/` uses **3-digit** `revision`, matching filename `{revision}_{slug}.py`.
   - [ ] After `make migrate`: `make db-version` shows the expected revision; `make db-history` shows a **linear** chain to `head` (no stray multiple heads).

4. **Docs**
   - [ ] Update `backend/docs/TECHNICAL.md` or `backend/docs/guides/*` if behavior, env vars, or operators’ steps changed (see table in `workflow-changelog.mdc`).
   - [ ] Update `backend/docs/INDEX.md` if a new top-level doc was added.

5. **Verification**
   - [ ] `make lint` and `make typecheck` from `backend/`.
   - [ ] `make test` or at least `make tests-mock` if scope allows.

6. **Commit / PR**
   - [ ] Imperative commit subject; PR body lists verify steps and migration/deploy notes.

## Do not

- Commit secrets or real credential JSON; only names in CHANGELOG/docs.
