# Dependency security audit

Snapshot: 2026-10-13. This is an advisory scan of the local lockfiles and installed development environment, not a penetration test or a claim that every finding is exploitable in LEAP.

## Frontend

The previous lockfile used Next.js 16.2.6. Registry advisories included critical Next.js findings. The project now pins `next` and `eslint-config-next` to 16.3.8 and uses Axios 1.20.x. The pnpm lockfile and `pnpm-workspace.yaml` also select patched transitive packages where published versions exist.

Run from `frontend/`:

```bash
pnpm install --frozen-lockfile
pnpm audit --prod --audit-level high
pnpm audit --audit-level high
pnpm lint
pnpm build
```

At this snapshot, the production audit reports zero known advisories. The full audit reports one high finding in development-only `braces@3.0.3`. The two moderate findings in `postcss` and `brace-expansion` were resolved by selecting published patched versions. The `braces` advisory names 3.0.4 as fixed, but npm has not published that version; do not add an override to a nonexistent package. `braces` is reached through the ESLint toolchain, not the production bundle. Recheck on a future dependency update.

## Backend

`pip-audit` was run against `backend/.venv/lib/python3.14/site-packages` using `--path`. An initial scan reported 147 advisory entries across 24 packages. After the backend lockfile and environment were updated, a repeat scan covered 174 installed packages and reported zero known vulnerabilities. This development environment includes test dependencies and may not exactly match the production image. The updated lockfile must be used to rebuild the production image before these package fixes reach production.

To repeat the scan after syncing the virtual environment:

```bash
cd backend
uv sync --locked
uvx pip-audit --path .venv/lib/python3.14/site-packages
```

Re-run the backend unit suite and API integration checks after future lockfile changes. Advisory databases change, so zero findings is a dated observation rather than a permanent guarantee.

After the queue and source-revision review, the backend unit suite passed 1,128 tests, including real FFmpeg checks for short and multi-sheet videos. The security-marked quality subset passed 2 tests, and Ruff lint and format checks passed. `ty check` completed with the same 87 diagnostics in existing code; none points to the new preview implementation. A real temporary Redis verified claim, renewal, and release of the preview and poster locks. The frontend passed 63 unit tests and ESLint. A local production build with `pnpm exec next build --webpack` passed; plain Turbopack build in the restricted runner stopped because it could not bind its internal port. Terraform validation passed with the installed provider plugins.

The production frontend audit and the backend installed-environment audit were repeated on 2026-10-13 after this review; both reported zero known vulnerabilities. The frontend development-only `braces` finding remains as described above. A later latency review in the same release reran the backend unit suite: 1,133 passed, including scoped poster queries, bounded attachment lookups, and extraction reads without a redundant HEAD. Frontend unit tests (63), ESLint, and the Webpack production build passed. `ty check` still reports the same 87 existing diagnostics. The default Turbopack build remains unverified locally because this runner restricts its internal port; CI must pass that exact build before deployment.

On 2026-10-15, the installed backend environment was scanned again with `uvx pip-audit --path .venv/lib/python3.14/site-packages`, and the frontend production dependencies with `pnpm audit --prod --audit-level high`; both reported zero known vulnerabilities. The queue recovery changes add no dependencies. The full backend unit suite passed 1,189 tests; Ruff, frontend ESLint and the Webpack production build passed. `ty check` completed with exit code 0 and 83 diagnostics in existing code; no diagnostic points to the new upload dispatch or preview recovery modules. The remaining development-only `braces` finding was not rescanned in this pass.

## Preview access checks

Owner preview routes scope the lookup to the authenticated user. Public recording and playlist preview routes resolve an enabled share or playable playlist item before reading a VTT or JPEG. For S3, authorized sheet requests redirect to signed object URLs; for LOCAL, they return JPEG bytes directly from the checked route. As with other signed media, revoking a share cannot immediately revoke an S3 URL already issued to a browser; the URL remains usable until its expiry.
