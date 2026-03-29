#!/usr/bin/env sh
# Create long-lived branches at the current HEAD (run after the first commit).
# Safe to re-run: skips branches that already exist.

set -e

if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "No commits yet. Commit first, then run this script again." >&2
  exit 1
fi

for name in main development staging testing production; do
  if git show-ref --verify --quiet "refs/heads/$name"; then
    echo "branch exists: $name"
  else
    git branch "$name"
    echo "branch created: $name"
  fi
done

echo ""
git branch --list --format='%(refname:short)'
