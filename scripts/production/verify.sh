#!/bin/sh
set -eu
exec python3 scripts/production/verify.py "$@"
