#!/bin/sh
set -eu
: "${CME_DATABASE_URL:?CME_DATABASE_URL is required}"
: "${CME_BACKUP_FILE:?CME_BACKUP_FILE is required}"
test -f "$CME_BACKUP_FILE.sha256"
sha256sum -c "$CME_BACKUP_FILE.sha256"
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$CME_DATABASE_URL" "$CME_BACKUP_FILE"
