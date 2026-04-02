#!/usr/bin/env bash
# Apply db/migrations/*.sql in lexical order against POSTGRES_DSN (requires psql).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DSN="${POSTGRES_DSN:-postgresql://library:library@localhost:5432/library}"
shopt -s nullglob
files=("$ROOT/db/migrations"/*.sql)
if [ "${#files[@]}" -eq 0 ]; then
  echo "No SQL files in $ROOT/db/migrations" >&2
  exit 1
fi
for f in "${files[@]}"; do
  echo "Applying $(basename "$f")"
  psql "$DSN" -v ON_ERROR_STOP=1 -f "$f"
done
echo "Done."
