#!/bin/sh
set -eu
: "${CME_BASE_URL:?CME_BASE_URL is required}"
: "${CME_EXPECTED_RELEASE:?CME_EXPECTED_RELEASE is required}"
: "${CME_RELEASE_FILE:?CME_RELEASE_FILE is required}"
test -s "$CME_RELEASE_FILE"
actual="$(cat "$CME_RELEASE_FILE")"
test "$actual" = "$CME_EXPECTED_RELEASE"
CME_BASE_URL="$CME_BASE_URL" sh scripts/verify-deployment.sh
printf '%s\n' "release identity and smoke verification passed"
