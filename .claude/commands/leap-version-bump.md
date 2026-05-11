# LEAP version bump and product update

**Canonical version:** `backend/pyproject.toml` → `[project].version` (no `v`). Everywhere else user-facing uses **`v` + same semver** (e.g. `v1.2.3`).

Confirm the **target version** with the user if not given (default: next logical semver from current `pyproject`).

---

## 1) Changes → business summary and doc audit

1. **Inventory** — from `git diff`, PR scope, or user's file list: modules, API paths, env vars (names only), migrations.
2. **Business summary** — 3–7 bullets for operators/users (outcomes, not refactors). Match voice of root `README.md` highlights (`Новое в v…` pattern).
3. **CHANGELOG draft** — technical bullets + `### Файлы` subsection per `workflow-changelog.mdc` (match surrounding CHANGELOG language).
4. **Doc consistency** — check `backend/docs/INDEX.md` cross-update table: if behavior/API/env/deploy changed, patch listed guides and `backend/docs/TECHNICAL.md`.
5. **Stale version grep** — search for **previous** `vX.Y.Z` / `X.Y.Z` in:
   - `README.md` (version lines + `Новое в v…` highlights)
   - `backend/api/__init__.py`, `backend/config/settings.py`, `backend/.version`
   - `backend/docs/UPDATES.md`, `backend/docs/ARCHITECTURE_SCHEMAS.md`
   - Any other path still advertising the old release

Do **not** treat ADR/guide internal doc-edition headings as product semver. Do **not** re-stamp `TECHNICAL.md` / every guide with product semver unless that file is meant to carry it.

---

## 2) Apply the new version

1. `backend/pyproject.toml` → `[project].version = "X.Y.Z"`
2. `backend/api/__init__.py` → `__version__ = "X.Y.Z"`
3. `backend/config/settings.py` → `AppSettings.version` default `Field(default="X.Y.Z", …)`
4. `backend/.version` → single line `X.Y.Z`
5. Root `README.md` → top version line, footer Version (if present), `Новое в vX.Y.Z` highlights block
6. `backend/docs/CHANGELOG.md` → append/prepend release block + dated entries
7. `backend/docs/UPDATES.md` → update current-release bullet if maintained
8. Replace other stale product stamps found in step 1.5
9. If Alembic revisions shipped: CHANGELOG mentions revision ids + deploy order

---

## 3) Verify

1. **Grep** from repo root for previous `X.Y.Z` / `vX.Y.Z` (escape dots). Expect no stale product stamps except inside CHANGELOG history and archives.
2. From `backend/`: `make lint`, `make typecheck`, `make tests-mock` (or `make test` if scope demands).
3. **Spot-check** — root `README.md` links to `docs/…`; if they 404 from repo root, rewrite to `backend/docs/…`.

---

## Do not

- Commit secrets; env vars in notes = names only.
- Bump unrelated `docker-compose` `version:` keys or Ruff `target-version`.
