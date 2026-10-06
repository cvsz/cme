#!/bin/sh
set -eu
: "${CME_DATABASE_URL:?CME_DATABASE_URL is required}"
: "${CME_BACKUP_FILE:?CME_BACKUP_FILE is required}"
test -f "$CME_BACKUP_FILE.sha256"
expected="$(cat "$CME_BACKUP_FILE.sha256")"
actual="$(sha256sum "$CME_BACKUP_FILE" | awk '{print $1}')"
test "$actual" = "$expected"
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$CME_DATABASE_URL" "$CME_BACKUP_FILE"
