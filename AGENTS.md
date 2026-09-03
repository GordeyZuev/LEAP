# Repository Guidelines

## Project Structure & Module Organization

LEAP is a monorepo for an educational video-processing platform. `backend/` contains the FastAPI application, Celery tasks, SQLAlchemy models, Alembic migrations, processing modules, and pytest suite. `frontend/` contains the Next.js application; routes live in `src/app`, reusable UI in `src/components`, and client utilities in `src/lib`. Infrastructure is under `terraform/`, `monitoring/`, `nginx/`, and `scripts/`. Use `backend/docs/INDEX.md` to find authoritative technical and operations documentation.

## Build, Test, and Development Commands

- `make dev-up` — start local PostgreSQL and Redis from the repository root.
- `cd backend && uv sync` — install Python 3.14 dependencies.
- `cd backend && make api` — run the development API on port 8000.
- `cd backend && make tests-mock` — run the fast unit-test suite and test linting.
- `cd backend && make lint && make typecheck` — run Ruff and `ty` checks.
- `cd backend && make migrate` — apply Alembic migrations.
- `cd frontend && pnpm install && pnpm dev` — install dependencies and run Next.js locally.
- `cd frontend && pnpm lint && pnpm build` — validate and build the web client.

## Coding Style & Naming Conventions

Python uses four-space indentation, type hints, 120-character lines, and double quotes. Format and lint with Ruff; write comments and docstrings in English. Follow existing `snake_case` module/function and `PascalCase` class naming. TypeScript is strict, uses two-space indentation, `PascalCase` React components, and `camelCase` functions. Run ESLint before submitting frontend changes. Alembic revisions use zero-padded IDs and matching filenames, for example `041_add_feature.py`.

## Testing Guidelines

Pytest tests live in `backend/tests/` and mirror production modules. Name files `test_*.py`, classes `Test*`, and functions `test_*`. Use registered markers such as `unit`, `integration`, `quality`, `security`, and `slow`. Add focused regression tests for changed behavior; run the narrowest relevant suite first, then lint and type checks.

## Commit & Pull Request Guidelines

Use concise, imperative commit subjects; release commits may use the established `vX.Y.Z` form. Pull requests should explain the user-visible outcome, list verification commands, link relevant issues, and identify migrations or deployment ordering. Include screenshots for visible frontend changes.

## Security & Architecture

Preserve tenant isolation by scoping access to the owning user and using existing validators. Never commit or log secrets, tokens, or credential files. Persistent media belongs in the configured S3-compatible storage backend; local files are temporary processing artifacts only.
