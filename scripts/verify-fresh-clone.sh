#!/bin/sh
set -eu
command -v docker >/dev/null
command -v python3 >/dev/null
docker compose config >/dev/null
python3 scripts/validate_repo.py
python3 -m unittest discover -s tests -v
release_sha="$(git rev-parse HEAD)"
image="cme-api:fresh-clone-$release_sha"
docker build --build-arg CME_RELEASE_SHA="$release_sha" -t "$image" .
uid="$(docker run --rm --entrypoint=id "$image" -u)"
test "$uid" != "0"
printf '%s\n' "fresh-clone verification passed"
