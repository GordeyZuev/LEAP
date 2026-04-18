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
2. **Business summary** — 3–7 bullets **for operators/users** (outcomes, not refactors). Reuse tone from root **`README.md`** «Новое в v…».
3. **CHANGELOG draft** — Technical bullets + `### Файлы` / `### Files` per **`workflow-changelog.mdc`**.
4. **Doc consistency** — Open **`backend/docs/INDEX.md`** and **`workflow-changelog.mdc`** cross-update table: if behavior/API/env/deploy changed, patch the listed guides and **`backend/docs/TECHNICAL.md`**.
5. **Stale version grep** — Search for the **previous** `vX.Y.Z` / `X.Y.Z` in:
   - `README.md`
   - `backend/docs/TECHNICAL.md`
   - `backend/docs/guides/TEMPLATES_PRESETS_SOURCES_GUIDE.md` (and any guide with a **product** version line)
   - `backend/docs/ADR_OVERVIEW.md` (product status line, if present)
   - `backend/docs/archive/UPDATES.md` or similar **only if** you still curate them

Do **not** treat ADR/guide **internal** “Версия документа” as the product semver unless the file explicitly tracks releases.

---

## 2) Apply the new version

1. Set **`backend/pyproject.toml`** `[project].version` = `X.Y.Z` (no `v`).
2. Update **root `README.md`**: `**Версия:**`, footer **Version**, and add/adjust **«Новое в vX.Y.Z»** from step 1.
3. Append/prepend **`backend/docs/CHANGELOG.md`** release block (and dated entries if that is the house style).
4. Replace stale **product** version strings found in step 1.5 with **`vX.Y.Z`** and current month/year where those lines include a date.
5. If **Alembic** revisions shipped: ensure **`alembic-migrations.mdc`** checklist and CHANGELOG mention revision ids + deploy order.

---

## 3) Verify

1. **Grep** — From repo root, search for the **previous** `X.Y.Z` / `vX.Y.Z` (escape dots in regex); expect **no** stale **product** stamps except inside CHANGELOG history and intentional archives.
2. **Backend** (from `backend/`): **`make lint`**, **`make typecheck`**, **`make tests-mock`** (or **`make test`** if scope demands).
3. **Spot-check** — README links to docs: repo uses **`backend/docs/`**; if README still uses `docs/...` links, keep **one** consistent style and ensure targets exist (fix broken links if you touch that section).

---

## Do not

- Commit secrets; env vars in notes = **names only**.
- Bump unrelated **docker-compose** `version:` keys or **Python** `target-version` in Ruff — those are not product semver.
