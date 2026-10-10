#!/bin/sh
set -eu
: "${CME_APP_ENV:?CME_APP_ENV is required}"
: "${CME_BACKUP_FILE:?CME_BACKUP_FILE is required}"
: "${CME_RESTORE_CONFIRM_DATABASE:?Set this to the exact target database name}"

case "$CME_APP_ENV" in
  development|test|production) ;;
  *)
    printf '%s\n' "FAIL: CME_APP_ENV must be development, test, or production." >&2
    exit 1
    ;;
esac

if [ "${CME_ALLOW_DESTRUCTIVE_RESTORE:-}" != "YES" ]; then
  printf '%s\n' "FAIL: set CME_ALLOW_DESTRUCTIVE_RESTORE=YES after reviewing the target." >&2
  exit 1
fi
if [ "$CME_APP_ENV" = production ] \
  && [ "${CME_ALLOW_PRODUCTION_RESTORE:-}" != "I_APPROVE_LIVE_DATABASE_RECOVERY" ]; then
  printf '%s\n' "FAIL: production restore requires explicit live recovery approval." >&2
  exit 1
fi

checksum_file="$CME_BACKUP_FILE.sha256"
if [ ! -f "$CME_BACKUP_FILE" ] || [ -L "$CME_BACKUP_FILE" ] || [ ! -s "$CME_BACKUP_FILE" ]; then
  printf '%s\n' "FAIL: backup file is missing, empty, or a symlink." >&2
  exit 1
fi
if [ ! -f "$checksum_file" ] || [ -L "$checksum_file" ]; then
  printf '%s\n' "FAIL: backup checksum is missing or is a symlink." >&2
  exit 1
fi

expected="$(cat "$checksum_file")"
case "$expected" in
  *[!0-9a-fA-F]*|'')
    printf '%s\n' "FAIL: backup checksum is malformed." >&2
    exit 1
    ;;
esac
if [ "${#expected}" -ne 64 ]; then
  printf '%s\n' "FAIL: backup checksum is malformed." >&2
  exit 1
fi
actual="$(sha256sum "$CME_BACKUP_FILE" | awk '{print $1}')"
if [ "$actual" != "$expected" ]; then
  printf '%s\n' "FAIL: backup checksum does not match." >&2
  exit 1
fi
if ! python3 scripts/production/postgres_client.py list "$CME_BACKUP_FILE" >/dev/null 2>&1; then
  printf '%s\n' "FAIL: backup format validation failed." >&2
  exit 1
fi

actual_database="$(python3 scripts/production/postgres_client.py database-name 2>/dev/null)" || {
  printf '%s\n' "FAIL: database target could not be verified; connection details were suppressed." >&2
  exit 1
}
if [ "$actual_database" != "$CME_RESTORE_CONFIRM_DATABASE" ]; then
  printf '%s\n' "FAIL: connected database does not match CME_RESTORE_CONFIRM_DATABASE." >&2
  exit 1
fi

if ! python3 scripts/production/postgres_client.py restore "$CME_BACKUP_FILE" >/dev/null 2>&1; then
  printf '%s\n' "FAIL: restore failed; database details were suppressed." >&2
  exit 1
fi
printf '%s\n' "PASS: restore completed for the confirmed target database."
