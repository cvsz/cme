#!/bin/sh
set -eu
: "${CME_DATABASE_URL:?CME_DATABASE_URL is required}"
: "${CME_BACKUP_FILE:?CME_BACKUP_FILE is required}"
umask 077
pg_dump --format=custom --no-owner --no-acl --dbname="$CME_DATABASE_URL" --file="$CME_BACKUP_FILE"
pg_restore --list "$CME_BACKUP_FILE" >/dev/null
sha256sum "$CME_BACKUP_FILE" >"$CME_BACKUP_FILE.sha256"
