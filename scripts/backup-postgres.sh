#!/bin/sh
set -eu
: "${CME_BACKUP_FILE:?CME_BACKUP_FILE is required}"
umask 077

checksum_file="$CME_BACKUP_FILE.sha256"
if [ -e "$CME_BACKUP_FILE" ] || [ -L "$CME_BACKUP_FILE" ]; then
  printf '%s\n' "FAIL: backup target already exists; choose a new path." >&2
  exit 1
fi
if [ -e "$checksum_file" ] || [ -L "$checksum_file" ]; then
  printf '%s\n' "FAIL: checksum target already exists; choose a new backup path." >&2
  exit 1
fi

temporary_dump="$(mktemp "${CME_BACKUP_FILE}.tmp.XXXXXX")"
temporary_checksum="$(mktemp "${checksum_file}.tmp.XXXXXX")"
trap 'rm -f -- "$temporary_dump" "$temporary_checksum"' EXIT HUP INT TERM

if ! python3 scripts/production/postgres_client.py dump "$temporary_dump" >/dev/null; then
  printf '%s\n' "FAIL: PostgreSQL backup failed; connection details were suppressed." >&2
  exit 1
fi
if ! python3 scripts/production/postgres_client.py list "$temporary_dump" >/dev/null 2>&1; then
  printf '%s\n' "FAIL: PostgreSQL backup format validation failed." >&2
  exit 1
fi

sha256sum "$temporary_dump" | awk '{print $1}' >"$temporary_checksum"
if ! ln -- "$temporary_dump" "$CME_BACKUP_FILE" 2>/dev/null; then
  printf '%s\n' "FAIL: backup target appeared during creation; no existing file was changed." >&2
  exit 1
fi
if ! ln -- "$temporary_checksum" "$checksum_file" 2>/dev/null; then
  printf '%s\n' "FAIL: checksum target appeared during creation; backup was preserved." >&2
  exit 1
fi

printf '%s\n' "PASS: backup created and validated at $CME_BACKUP_FILE"
printf '%s\n' "PASS: SHA-256 checksum recorded at $checksum_file"
