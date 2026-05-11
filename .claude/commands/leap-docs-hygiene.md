# LEAP documentation hygiene

Canonical rules: `documentation.mdc` (now in `CLAUDE.md`). This command is the **workflow** for cleanup.

## Authority order

1. `backend/docs/INDEX.md` — must list all navigable entry points.
2. `backend/docs/guides/` — **current** procedures (deployment, OAuth, Celery, integrations, templates).
3. `backend/docs/TECHNICAL.md`, `backend/docs/ADR_*.md`, `backend/docs/DATABASE_DESIGN.md` — reference architecture and API narrative.
4. `backend/docs/CHANGELOG.md` — what shipped; not a substitute for guides.
5. `backend/docs/archive/` — historical or superseded whole documents (read-only).
6. `backend/docs/dev_notes/` — drafts and TODOs; **do not** treat as runbooks when they conflict with `guides/`.

## Cleanup workflow

1. **Pick one canonical page** per procedure. Merge or delete duplicates; replace secondary copies with a single link.
2. **Superseded content:**
   - Add a short top banner: `**Status: superseded** — use guides/….md (YYYY-MM-DD).`
   - If the file is noise: move to `backend/docs/archive/` and link from INDEX only if still referenced externally.
3. **dev_notes:**
   - If still true: promote content into `guides/` or ADR, then trim or archive the note.
   - If obsolete: archive or delete; do not leave contradictory instructions.
4. **INDEX:** add/remove links when files move; remove dead links.
5. **Cross-links:** prefer paths relative to `backend/docs/` (e.g. `guides/DEPLOYMENT.md`).

## Language

Keep **one language per file** consistent with the rest of that file (existing Russian guides may stay Russian).

## Do not

- Add new root-level `.md` files without an INDEX home.
- Paste secrets or real tokens in docs.
