#!/bin/bash
# Runtime entrypoint for api / celery_worker / celery_beat.
#
# Migrations live in a dedicated `migrate` compose service (see migrate.sh)
# that runs once before app containers start. This entrypoint only waits for
# Postgres to be reachable, then execs the command from CMD.
set -e

echo "⏳ Waiting for PostgreSQL..."
while ! pg_isready -h "${DATABASE_HOST:-localhost}" -p "${DATABASE_PORT:-5432}" -U "${DATABASE_USERNAME:-postgres}" > /dev/null 2>&1; do
    sleep 2
done
echo "✅ PostgreSQL is ready, starting: $*"

exec "$@"
