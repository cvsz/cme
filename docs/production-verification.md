# Production Verification

Run the checks against the exact candidate or deployed release. The scripts print only gate results and sanitized details. Store manifests and CI summaries outside Git in the operator evidence system.

## Preflight

Prepare protected runtime and candidate release environment files outside the checkout. The current active release file remains in place until an authorized cutover. Supply at least:

- `CME_APP_ENV=production`
- a strong, non-default PostgreSQL runtime URL and Redis URL
- a distinct migration database URL
- a strong `POSTGRES_PASSWORD` for the PostgreSQL service configuration
- a full 40-character `CME_RELEASE_SHA`
- a unique `CME_API_IMAGE` for the candidate image
- a verified backup path and adjacent `.sha256` sidecar
- owner-approved `CME_RPO_TARGET` and `CME_RTO_TARGET`

Keep the runtime file at mode `0600` in a directory restricted to the deployment account. Do not source database URLs into the interactive shell; the scripts pass the protected files to Compose without displaying their values. This example uses placeholders only:

```bash
cd ~/cme
export CME_RELEASE_SHA="$(git rev-parse HEAD)"
export CME_API_IMAGE="cme-api:${CME_RELEASE_SHA}"
export CME_COMPOSE_ENV_FILES='/etc/cme/runtime.env:/etc/cme/release-candidate.env'
export CME_BACKUP_FILE='/var/backups/cme/verified-backup.dump'
export CME_RPO_TARGET='REPLACE_WITH_OWNER_APPROVED_TARGET'
export CME_RTO_TARGET='REPLACE_WITH_OWNER_APPROVED_TARGET'
docker compose --env-file /etc/cme/runtime.env --env-file /etc/cme/release-candidate.env config --quiet
sh scripts/production/preflight.sh
```

Preflight returns `PASS`, `FAIL`, or `BLOCKED` for each gate. It validates production configuration, private API binding, unpublished database and Redis ports, separate runtime/migration roles targeting the same database, the candidate image configuration, runtime privileges, migration login and ownership/DDL access, PostgreSQL schema revision, Redis PING, backup checksum/archive, and configured recovery policy. It exits nonzero unless every gate passes. Preflight does not deploy, migrate, rotate credentials, or change database roles.

The scripts reject empty values and obvious documentation placeholders for `CME_RPO_TARGET` and `CME_RTO_TARGET`. They cannot prove who approved those values or whether measured recovery evidence meets them; retain owner approval and the comparison in the external release record.

Build the candidate under a unique release tag after setting its full SHA and image name:

```bash
docker compose --env-file /etc/cme/runtime.env --env-file /etc/cme/release-candidate.env build api migrate
```

The Docker image records `CME_RELEASE_SHA` in the OCI revision label. Keep the resulting image ID and image tag in the release record. Do not reuse mutable `latest` or `local` tags for a release.

## Cutover and verification

After preflight passes, obtain explicit operator authorization before promoting the candidate release file to the active release configuration. Keep the previous file and image for rollback. Then recreate only the API service:

```bash
docker compose --env-file /etc/cme/runtime.env --env-file /etc/cme/release.env up -d --no-deps api
```

Do not run migrations as part of an unreviewed cutover. Use a separately reviewed migration window and the migration database role. Never run `docker compose down -v`.

After deployment, obtain the exact running image ID and write a unique release manifest outside the repository:

```bash
export CME_EXPECTED_RELEASE_SHA="$CME_RELEASE_SHA"
export CME_EXPECTED_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$(docker compose --env-file /etc/cme/runtime.env --env-file /etc/cme/release.env ps -q api)")"
export CME_RELEASE_EVIDENCE_FILE="/var/lib/cme/evidence/release-${CME_RELEASE_SHA}-$(date -u +%Y%m%dT%H%M%SZ).json"
export CME_BASE_URL='http://127.0.0.1:8000'
sh scripts/production/verify.sh
```

Verification checks exact Git SHA and image ID, OCI image label, API/PostgreSQL/Redis health, zero container restarts, private port bindings, HTTP liveness, production readiness, schema revision, PostgreSQL and Redis dependency state, recent application logs, backup checksum/archive, and RPO/RTO policy values. It writes a mode-`0600` JSON manifest without overwriting an existing file and exits nonzero if any gate fails. HTTP 200 by itself is insufficient.

## Application rollback

Retain the previous application image and release environment values. Run the compatibility check before changing the API service. It starts the prior image with a read-only root filesystem, no Linux capabilities, and no-new-privileges; it verifies the exact image ID/embedded SHA and reads the database revision. It does not modify production state.

```bash
export CME_ROLLBACK_IMAGE_ID='sha256:REPLACE_WITH_RECORDED_IMAGE_ID'
export CME_ROLLBACK_RELEASE_SHA='REPLACE_WITH_PRIOR_40_CHARACTER_SHA'
export CME_CURRENT_RELEASE_SHA='REPLACE_WITH_CURRENT_40_CHARACTER_SHA'
sh scripts/production/rollback-check.sh
```

For an authorized live rollback, first restore the previous `CME_API_IMAGE` and `CME_RELEASE_SHA` in the protected release environment file, then set the exact prior `CME_ROLLBACK_IMAGE_REF`, `CME_ROLLBACK_IMAGE_ID`, and `CME_ROLLBACK_RELEASE_SHA`. Set `CME_RELEASE_EVIDENCE_FILE` and `CME_ROLLBACK_RECORD_FILE` to unique paths outside the repository. After compatibility passes, this gated command recreates only the API service, waits for readiness, runs post-rollback verification, and writes a no-clobber audit record:

```bash
export CME_ROLLBACK_APPROVAL='I_APPROVE_LIVE_APPLICATION_ROLLBACK'
export CME_COMPOSE_ENV_FILES='/etc/cme/runtime.env:/etc/cme/release.env'
sh scripts/production/rollback.sh
```

Preserve the failed and recovered release manifests. If post-rollback verification fails, the script stops and reports failure without changing the database or attempting a second rollback. A database recovery requires its own explicit approval and verified backup.

## Capacity and external ownership

Choose capacity thresholds from approved product SLOs rather than repository defaults. Example:

```bash
python3 scripts/load_probe.py --url "$CME_BASE_URL/health" --requests 1000 --concurrency 25 --max-p95-ms 250 --max-error-rate 0.01
```

The probe is a local HTTP utility, not a production load result. Record exact artifact identity, environment, timestamps, load parameters, smoke results, restore/rollback evidence, observed RPO/RTO, DNS/TLS checks, and alert delivery in the operator evidence system. CMe supplies application checks only. `zworkforce` retains ownership of `zeaz.dev` DNS, Cloudflare, tunnels, and shared deployment controls.
