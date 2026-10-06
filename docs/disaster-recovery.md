# Disaster Recovery Runbook

## Scope and ownership

CMe owns application data backup/restore procedures. Public DNS, Cloudflare tunnels and shared infrastructure remain owned by the designated infrastructure repository.

## PostgreSQL backup

Set `CME_DATABASE_URL` and a protected local `CME_BACKUP_FILE`, then run `sh scripts/backup-postgres.sh`. The script creates a custom-format dump, validates its catalog and writes a SHA-256 checksum with mode inherited from a restrictive `umask 077`.

Production operators must copy backups to encrypted off-host storage with retention appropriate to business requirements. Credentials must come from the runtime secret store, never the repository.

## Restore

Restore only into an isolated target first. Set the target `CME_DATABASE_URL` and `CME_BACKUP_FILE`, then run `sh scripts/restore-postgres.sh`. The checksum is verified before `pg_restore`.

CI performs a destructive isolated restore drill by creating sentinel data, backing it up, deleting it, restoring the dump and asserting the sentinel value.

## Rollback

Application rollback uses the last known-good immutable image/release artifact. Database migrations are forward-only by default once production data may have changed. Before a destructive or incompatible migration, take and verify a backup and document the explicit data rollback decision.

## Recovery objectives

No production RPO/RTO is claimed by repository CI. RPO/RTO must be measured against the actual production backup cadence, storage and deployment environment. Repository restore CI proves procedure behavior only, not production recovery time.

## Evidence boundary

A green restore drill is isolated CI evidence. Production readiness additionally requires a production-equivalent restore and rollback exercise plus deployed DNS/TLS/monitoring verification.
