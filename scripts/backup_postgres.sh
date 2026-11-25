#!/usr/bin/env sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
file="backups/edms-postgresql-${stamp}.dump"
pg_dump "$DATABASE_URL" --format=custom --file="$file"
sha256sum "$file"
