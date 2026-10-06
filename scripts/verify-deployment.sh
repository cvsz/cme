#!/bin/sh
set -eu
: "${CME_BASE_URL:?CME_BASE_URL is required}"
base="${CME_BASE_URL%/}"
curl --fail --silent --show-error --max-time 10 "$base/health" | grep -q '"status":"ok"'
curl --fail --silent --show-error --max-time 10 "$base/ready" | grep -q '"status":"ready"'
printf '%s\n' "deployment smoke passed: $base"
