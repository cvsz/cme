#!/bin/sh
set -eu
exec python3 scripts/production/preflight.py "$@"
