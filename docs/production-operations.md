# Production Operations Runbook

## Signals and service health

The API binds to loopback in the Compose deployment. `/health` is a liveness check and does not require database or Redis access. `/ready` verifies the Alembic revision, PostgreSQL connectivity, and Redis PING. A successful liveness response alone does not mean the application is ready.

Use the existing ZEAZ monitoring stack where supported. This audit did not verify an alert receiver, production dashboard, disk-capacity alert, backup-failure alert, or alert delivery path. Coordinate shared monitoring and ingress changes through the infrastructure owner (`zworkforce`); do not add a second monitoring stack without an approved design.

Monitor at least:

- API, PostgreSQL, and Redis health and unexpected restart counts.
- `/ready` failures, database connection failures, Redis availability, and migration errors.
- Host and PostgreSQL volume capacity, backup completion, and off-host backup retention.
- Release SHA/image ID, deployment verification, and backup/restore evidence paths.

Application logs include request IDs and suppress sensitive configuration validation details. Do not paste production logs into public issues or untrusted services. Review logs before sharing them because third-party integrations may log data outside the application controls.

## First response to an incident

1. Record the UTC start time, affected release SHA/image ID, observed impact, and the operator making changes.
2. Check `docker compose ps`, `/health`, and `/ready`. Preserve recent API logs and container restart counts in the approved evidence store.
3. Check database and Redis health, disk capacity, the current Alembic revision, and the latest backup checksum. Do not include connection URLs or customer rows in the incident record.
4. Prefer the smallest reversible application action. Run the schema compatibility check before an application rollback; obtain the separately required authorization before live rollback or database recovery.
5. Keep PostgreSQL data and backups intact. Never use `docker compose down -v`, reset the database volume, or restore over the live database as an application rollback.
6. After recovery, run post-change verification, retain both failed and recovered release evidence, and document remaining impact and follow-up work.

For suspected security incidents, preserve relevant evidence, contain access through the approved incident process, and report vulnerabilities through [SECURITY.md](../SECURITY.md), not a public issue. Database role revocation, credential changes, and external infrastructure changes require separate authorization.

## Troubleshooting commands

Run from `~/cme`. Keep runtime values in protected environment files and pass them to Compose with `--env-file`; do not print resolved configuration.

```bash
cd ~/cme
docker compose --env-file /etc/cme/runtime.env --env-file /etc/cme/release.env config --quiet
docker compose --env-file /etc/cme/runtime.env --env-file /etc/cme/release.env ps
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:8000/ready
sh scripts/production/preflight.sh
```

`/health` can remain available while `/ready` fails. In that case, review sanitized API logs, PostgreSQL/Redis health, connection availability, and schema revision. Do not run migrations as an incident shortcut; use the reviewed migration procedure and the migration role.

## Known operational limits

- Public DNS, Cloudflare, tunnels, and shared ingress are outside CMe ownership.
- Production alert routing, disk monitoring, backup alerting, and delivery evidence were not verified in this audit.
- The current deployment uses a superuser database identity and an image without an OCI revision label; production role rotation and exact-image rollback remain blocked.
- Production RPO/RTO targets must come from the release owner. CI durations and test-only sentinel values are not approved recovery objectives.
- Local restore and rollback drills verify procedure behavior only; they do not prove current production backup freshness, off-host retention, or disaster recovery acceptance.
