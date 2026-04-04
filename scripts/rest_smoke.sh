#!/usr/bin/env bash
# Optional smoke checks against a running REST gateway (e.g. after docker compose up).
# Usage: REST_BASE_URL=http://localhost:8080 ./scripts/rest_smoke.sh
set -euo pipefail
BASE="${REST_BASE_URL:-http://localhost:8080}"
BASE="${BASE%/}"

echo "GET $BASE/health"
curl -sfS "$BASE/health" | head -c 200
echo
echo "GET $BASE/health/ready"
curl -sfS "$BASE/health/ready" | head -c 400
echo
echo "GET $BASE/books?limit=2"
curl -sfS "$BASE/books?limit=2" | head -c 400
echo
echo "GET $BASE/api/members/22222222-2222-2222-2222-222222222201/borrowed (seed loan)"
curl -sfS "$BASE/api/members/22222222-2222-2222-2222-222222222201/borrowed" | head -c 400
echo
echo "OK"
