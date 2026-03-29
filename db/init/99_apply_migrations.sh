#!/bin/sh
# Apply versioned SQL under db/migrations (mounted at /docker-entrypoint-initdb.d-migrations).
set -eu
if [ ! -d /docker-entrypoint-initdb.d-migrations ]; then
  echo "apply_migrations: missing mount /docker-entrypoint-initdb.d-migrations" >&2
  exit 1
fi
for f in /docker-entrypoint-initdb.d-migrations/*.sql; do
  [ -f "$f" ] || continue
  echo "Applying $f"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
done
