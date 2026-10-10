# Disaster Recovery Runbook

## Scope and ownership

CMe owns application data backup and restore procedures. Public DNS, Cloudflare tunnels, and shared infrastructure remain owned by the designated infrastructure repository and operator.

## PostgreSQL backup

Prepare a mode-`0600` file owned by the backup operator containing one PostgreSQL URL. On the Compose host, use the PostgreSQL service hostname in that URL and set `CME_POSTGRES_CLIENT_MODE=compose`; the helper runs the matching PostgreSQL client inside the `postgres` service, streams archives through Docker without storing another full copy in the container, and removes its temporary credential file. For a hosted PostgreSQL service reachable directly from the runner, leave the client mode at its default `local`. In both modes, set `CME_DATABASE_URL_FILE` to the protected URL file and choose a new protected `CME_BACKUP_FILE`. The helper places only the password in a temporary mode-`0600` `PGPASSFILE` and keeps credentials out of process arguments and logs. The script refuses to overwrite either an existing dump or checksum sidecar, validates the custom archive, and writes a SHA-256 checksum.

```bash
export CME_DATABASE_URL_FILE='/etc/cme/backup-database.url'
export CME_POSTGRES_CLIENT_MODE='compose'
export CME_BACKUP_FILE="/var/backups/cme/cme-$(date -u +%Y%m%dT%H%M%SZ).dump"
sh scripts/backup-postgres.sh
```

Credentials must come from the host secret store or a protected environment file, never Git or shell history. Store verified backups in encrypted off-host storage with owner-approved retention. Keep the generated `.sha256` file beside the dump. Never reuse a backup path.

## Isolated restore drill

The `DR and Supply Chain` workflow migrates an empty PostgreSQL 17 database, writes a sentinel, creates a backup and records timestamps, duration, size, checksum, and PostgreSQL version. It restores into a separate disposable database, checks the sentinel, then runs `scripts/production/verify-restored-db.py`.

The verifier checks the expected Alembic revision, PostgreSQL client/server major compatibility, the complete expected application table set, required indexes and constraints, balanced posted journal entries, read-only row counts, and API readiness against the restored database. CI service databases are disposable; production databases and backups are never targets of this workflow.

For a manual isolated drill, prepare an empty disposable database and set all variables explicitly:

```bash
export CME_APP_ENV=test
export CME_DATABASE_URL_FILE='/secure/path/to/drill-database.url'
export CME_POSTGRES_CLIENT_MODE=compose
export CME_BACKUP_FILE='/secure/path/to/cme.dump'
export CME_RESTORE_CONFIRM_DATABASE='cme_restore'
export CME_ALLOW_DESTRUCTIVE_RESTORE='YES'
sh scripts/restore-postgres.sh
python3 scripts/production/verify-restored-db.py
```

The restore script checks the backup checksum and format, confirms the connected database name, and requires explicit destructive authorization before using `pg_restore --clean`. Production mode additionally requires `CME_ALLOW_PRODUCTION_RESTORE=I_APPROVE_LIVE_DATABASE_RECOVERY`; that setting is reserved for a separately approved live recovery event. Never point a drill at the production database.

## Recovery objectives and evidence

No business RPO/RTO target is selected by this repository. The release owner must set `CME_RPO_TARGET` and `CME_RTO_TARGET` from approved policy before cutover. CI records observed backup and restore durations, but those measurements do not establish that the targets are met. Production acceptance requires a production-equivalent drill with actual off-host backup storage and measured recovery duration.

Keep workflow summaries and production drill evidence in the approved operator evidence system. Record the evidence path, UTC start/end times, duration, backup size and checksum, PostgreSQL versions, revision, table/index/constraint checks, consistency result, and application smoke result. Do not place customer data or secrets in summaries.

## Application rollback

Retain the prior known-good image by immutable image ID and its embedded Git SHA. Before an application rollback, run `scripts/production/rollback-check.sh` against the existing database. It starts the prior image as a read-only, capability-dropped container and stops if the prior code does not support the current schema revision. The check does not change the deployment or database.

Follow [Production Verification](production-verification.md) for release verification and the gated application rollback workflow. Database downgrade or restore is a separate recovery operation requiring explicit authorization and a verified backup. The application rollback tool must never restore or downgrade PostgreSQL automatically.

## Evidence boundary

A passing isolated CI restore drill verifies repository procedure behavior. It does not verify production backup cadence, off-host retention, RPO/RTO compliance, or disaster recovery acceptance. DNS, TLS, public routing, and shared tunnel checks remain with the infrastructure operator.
