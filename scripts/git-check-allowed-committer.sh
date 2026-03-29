#!/usr/bin/env sh
# Local commit gate: when config/git-allowed-committers exists, only listed
# emails may create commits. Pair with GitHub branch protection for real enforcement.

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ALLOW_FILE="$ROOT/config/git-allowed-committers"

if [ "${GIT_COMMITTER_ALLOW_ALL:-}" = "1" ]; then
  exit 0
fi

if [ ! -f "$ALLOW_FILE" ]; then
  if [ "${GIT_STRICT_COMMITTER:-}" = "1" ]; then
    echo "husky: GIT_STRICT_COMMITTER=1 requires $ALLOW_FILE (copy from config/git-allowed-committers.example)." >&2
    exit 1
  fi
  exit 0
fi

email="$(git config user.email 2>/dev/null || true)"
if [ -z "$email" ]; then
  echo "husky: Refusing commit: git user.email is not set." >&2
  exit 1
fi

matched=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    \#*) continue ;;
    "") continue ;;
  esac
  allowed="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [ "$email" = "$allowed" ]; then
    matched=1
    break
  fi
done < "$ALLOW_FILE"

if [ "$matched" -ne 1 ]; then
  echo "husky: Refusing commit: user.email '$email' is not listed in $ALLOW_FILE" >&2
  echo "husky: To bypass locally (emergency only): GIT_COMMITTER_ALLOW_ALL=1 git commit ..." >&2
  exit 1
fi

exit 0
