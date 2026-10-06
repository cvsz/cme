#!/bin/sh
set -eu
command -v docker >/dev/null
command -v python3 >/dev/null
docker compose config >/dev/null
python3 scripts/validate_repo.py
python3 -m unittest discover -s tests -v
docker build -t cme-api:fresh-clone .
uid="$(docker run --rm --entrypoint=id cme-api:fresh-clone -u)"
test "$uid" != "0"
printf '%s\n' "fresh-clone verification passed"
