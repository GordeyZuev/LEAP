---
name: leap-docs-hygiene
description: >-
  Reorganizes LEAP documentation—canonical locations, INDEX updates, superseded
  banners, archive vs dev_notes. Use when cleaning up docs, consolidating
  guides, marking files obsolete, or resolving duplicate how-tos.
---

# LEAP documentation hygiene

Canonical rules live in **`documentation.mdc`**. This skill is the **workflow** for cleanup.

## Authority order

1. `backend/docs/INDEX.md` — must list navigable entry points.
2. `backend/docs/guides/` — **current** procedures (deployment, OAuth, Celery, integrations, templates).
3. `backend/docs/TECHNICAL.md`, `backend/docs/ADR_*.md`, `backend/docs/DATABASE_DESIGN.md` — reference architecture and API narrative.
4. `backend/docs/CHANGELOG.md` — what shipped; not a substitute for guides.
5. `backend/docs/archive/` — historical or superseded **whole documents** worth keeping read-only.
6. `backend/docs/dev_notes/` — drafts and TODOs; **do not** treat as runbooks when they conflict with `guides/`.

## Cleanup workflow

1. **Pick one canonical page** per procedure. Merge or delete duplicates; replace secondary copies with a single link to the canonical file.
2. **Superseded content**
   - Add a short top banner, e.g. `**Status: superseded** — use guides/….md (YYYY-MM-DD).` with a concrete path to the replacement doc.
   - If the file is noise: move to `backend/docs/archive/` and link from INDEX only if still referenced externally.
3. **dev_notes**
   - If the note is still true: promote content into `guides/` or ADR, then trim or archive the note.
   - If obsolete: archive or delete per team policy; do not leave contradictory instructions in `dev_notes/`.
4. **INDEX**
   - Add/remove links when files move. Remove dead links.
5. **Cross-links**
   - Prefer links relative to `backend/docs/` (e.g. `guides/DEPLOYMENT.md`) consistent with surrounding files.

## Language

- Keep **one language per file** consistent with the rest of that file (existing Russian guides may stay Russian).

## Do not

- Add new root-level `.md` files without an INDEX home.
- Paste secrets or real tokens in docs.
