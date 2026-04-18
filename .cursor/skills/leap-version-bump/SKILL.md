---
name: leap-version-bump
description: >-
  Ships a product update: derives a short business summary from changed files,
  audits docs for stale version or mismatched behavior, bumps semver in
  pyproject/README/CHANGELOG and other stamped docs, then verifies with grep
  and make checks. Use when releasing, bumping version, updating README
  “what’s new”, or syncing docs after a feature merge.
---

# LEAP version bump and product update

**Canonical version:** `backend/pyproject.toml` → `[project].version` (no `v`). **Everywhere else** user-facing may use **`v` + same semver** (e.g. `v1.2.3`).

Confirm the **target version** with the user if they did not give one (default: next logical semver from current `pyproject`).

Supporting rules: **`workflow-changelog.mdc`**, **`version-bump-and-readme.mdc`**, **`alembic-migrations.mdc`** (if DB changed).

---

## 1) Changes → business summary and doc audit

1. **Inventory** — From `git diff`, PR scope, or the user’s file list: modules, API paths, env vars (**names only**), migrations.
2. **Business summary** — 3–7 bullets **for operators/users** (outcomes, not refactors). Match the voice of the root **`README.md`** highlights section (currently the `` `Новое в v…` `` pattern).
3. **CHANGELOG draft** — Technical bullets + `` `### Файлы` `` / `` `### Files` `` subsection per **`workflow-changelog.mdc`** (match surrounding CHANGELOG language).
4. **Doc consistency** — Open **`backend/docs/INDEX.md`** and **`workflow-changelog.mdc`** cross-update table: if behavior/API/env/deploy changed, patch the listed guides and **`backend/docs/TECHNICAL.md`**.
5. **Stale version grep** — Search for the **previous** `vX.Y.Z` / `X.Y.Z` in:
   - `README.md` (version lines + highlights section, `` `Новое в v…` `` pattern)
   - `backend/api/__init__.py`, `backend/config/settings.py`, `backend/.version`
   - `backend/docs/UPDATES.md`, **`backend/docs/ARCHITECTURE_SCHEMAS.md`** (when the header is a **product** release line), and any path that still advertises the **old** release as current

Do **not** treat ADR/guide **internal** doc-edition headings (e.g. text like `` `Версия документа` ``) as the product semver unless the file explicitly tracks releases. Do **not** re-stamp **TECHNICAL.md** / every guide with product semver unless that file is meant to carry it.

---

## 2) Apply the new version

1. Set **`backend/pyproject.toml`** `[project].version` = `X.Y.Z` (no `v`).
2. Sync **runtime / tooling copies** of the same semver (no `v` in code defaults):
   - **`backend/api/__init__.py`** → `__version__ = "X.Y.Z"`
   - **`backend/config/settings.py`** → `AppSettings.version` default (`Field(default="X.Y.Z", …)` — used by **`api/main.py`** for OpenAPI / health metadata)
   - **`backend/.version`** → single line `X.Y.Z`
3. Update **root `README.md`**: top product version line (often `` `**Версия:**` `` today), footer **Version** (if present), and highlights block (`` `Новое в vX.Y.Z` `` pattern) — all **`vX.Y.Z`** must match **X.Y.Z** from `pyproject`.
4. Append/prepend **`backend/docs/CHANGELOG.md`** release block (and dated entries if that is the house style).
5. If you maintain **`backend/docs/UPDATES.md`**, add/adjust the current-release bullet so it matches the new version (otherwise skip).
6. Replace any other stale **product** stamps found in step 1.5; add month/year only where that line already carries a date.
7. If **Alembic** revisions shipped: ensure **`alembic-migrations.mdc`** checklist and CHANGELOG mention revision ids + deploy order.

---

## 3) Verify

1. **Grep** — From repo root, search for the **previous** `X.Y.Z` / `vX.Y.Z` (escape dots in regex); expect **no** stale **product** stamps except inside CHANGELOG history and intentional archives.
2. **Backend** (from `backend/`): **`make lint`**, **`make typecheck`**, **`make tests-mock`** (or **`make test`** if scope demands).
3. **Spot-check** — Root **`README.md`** often links `docs/…` while files live under **`backend/docs/`**; if those links 404 from repo root, rewrite to a working form (e.g. `backend/docs/…`) or add a documented indirection—fix when editing that README section.

---

## Do not

- Commit secrets; env vars in notes = **names only**.
- Bump unrelated **docker-compose** `version:` keys or **Python** `target-version` in Ruff — those are not product semver.
