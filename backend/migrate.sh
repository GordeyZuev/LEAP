#!/bin/bash
# One-shot DB bootstrap: wait for postgres, create the target DB if it doesn't
# exist, run all pending Alembic revisions, exit.
#
# This script owns the entire migration step for the stack. The api,
# celery_worker and celery_beat services depend on it via
# `service_completed_successfully` and must NOT run migrations themselves.
set -e

echo "🔄 [migrate] Waiting for PostgreSQL..."
while ! pg_isready -h "${DATABASE_HOST:-localhost}" -p "${DATABASE_PORT:-5432}" -U "${DATABASE_USERNAME:-postgres}" > /dev/null 2>&1; do
    sleep 2
done
echo "✅ [migrate] PostgreSQL is ready"

echo "🔄 [migrate] Ensuring database exists..."
python <<EOF
import asyncio
from database.config import DatabaseConfig
from database.manager import DatabaseManager

async def init_db():
    db_manager = DatabaseManager(DatabaseConfig.from_env())
    await db_manager.create_database_if_not_exists()
    await db_manager.close()

asyncio.run(init_db())
EOF

echo "🔄 [migrate] Applying Alembic migrations..."
python -m alembic upgrade head
echo "✅ [migrate] Migrations applied"
