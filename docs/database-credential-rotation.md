# PostgreSQL Runtime Credential Rotation

## Safety model

PostgreSQL does not change an initialized role password when `POSTGRES_PASSWORD` changes in Compose. Update application role credentials through PostgreSQL itself. The rotation utility stages a new role and verifies it without altering the old role, active API configuration, or database contents. It never revokes the prior role and never switches the application.

Live role creation is a production database change. It requires a verified pre-rotation backup, a reviewed restore path, a maintenance/release record, and explicit operator authorization. Do not run the production command below until that authorization has been given. The repository tool does not execute the live operation automatically.

## Role policy

The rotation administrator must be a PostgreSQL superuser because it creates a role and grants reviewed table privileges. Use a short-lived admin secret from the approved secret store. The new runtime role is created with `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, and `NOBYPASSRLS`. It receives only the reviewed API table privileges for the current ten-table schema. The tool fails if the schema table set has drifted and does not set broad future default privileges.

The migration role is a separate, pre-existing login role. This tool does not grant it DDL rights, change object ownership, or change its password. Give it only database `CONNECT`, schema `USAGE` and `CREATE`, and ownership (or inherited ownership) of the application tables, sequences, views, domains, enums, and functions that Alembic must change. The production preflight connects through the configured migration URL and checks the current Alembic revision, those ownership/DDL prerequisites, and that the role is not superuser, cannot create databases or roles, cannot replicate, cannot bypass row security, and is not a member of another elevated role. If ownership must change, inventory the affected objects, verify a backup and restore path, and use a reviewed administrator operation during an approved maintenance window. Do not grant the migration role broad superuser access to avoid that work. Never use the runtime role for migrations. The current deployment evidence shows runtime role `cme` is a superuser; that is a P0 blocker until the staged runtime role has passed acceptance and the migration role is independently validated.

## Stage and validate

1. Inspect active database clients and current role attributes using a privileged read-only query. Identify runtime and migration users separately.
2. Create a new uniquely named backup with `scripts/backup-postgres.sh`; verify the checksum, archive format, and an isolated restore before staging credentials.
3. Prepare a protected administrator URL file outside the repository with mode `0600` or stricter. The file contains only the database administrator connection URL and is never printed. Create the output directory with mode `0700`; the output file must not already exist.
4. Select the actual database name, new runtime role, migration role, and unique output path. Set the literal approval variable only after the operator has authorized this production role-creation step.
5. Run the tool. It confirms the target database, verifies the admin role, refuses an existing new role, grants only the reviewed runtime privileges, and tests a real login and read of `alembic_version`. The new connection URL is written to an exclusive file with mode `0600`; no secret value is printed.
6. Add the generated runtime file as the last `--env-file` in `CME_COMPOSE_ENV_FILES` for preflight, after the candidate release file. Run `scripts/production/preflight.sh` while the current application still uses its original configuration. The preflight must prove the candidate runtime role has no elevated cluster privileges and can connect, the distinct migration role targets the same database and has the reviewed DDL access, Redis is available, schema is current, and backup/release inputs pass.
7. Keep the prior runtime environment file and role available through the approved rollback window. After explicit cutover authorization, switch only the API container to the new runtime configuration, then run `scripts/production/verify.sh` and preserve its release manifest.
8. Revoke old runtime access only after acceptance, rollback-window closure, and confirmation that no runtime or migration clients use it. Record that action in the operator audit system. Never revoke a role that is still used for migrations.

Example command shape; values are placeholders and must be supplied through a protected operator file:

```bash
cd ~/cme
export CME_APP_ENV=production
export CME_ROTATION_ADMIN_URL_FILE='/etc/cme/rotation-admin.url'
export CME_ROTATION_CONFIRM_DATABASE='cme'
export CME_ROTATION_ROLE='cme_runtime_20261008'
export CME_ROTATION_MIGRATION_ROLE='cme_migrator'
export CME_ROTATION_OUTPUT_FILE='/etc/cme/runtime-next.env'
export CME_ROTATION_APPROVAL='I_APPROVE_LIVE_DATABASE_ROLE_CHANGE'
sh scripts/production/rotate-db-credentials.sh
```

The example must be edited for the actual authorized operation. It is not a command to run against production without approval. For the automated isolated test, the DR workflow uses a disposable PostgreSQL service and a loopback connection; the tool restricts `CME_APP_ENV=test` to loopback hosts.

## Reversible configuration switch

Use ordered Compose environment files so the candidate runtime URL overrides the existing runtime URL without replacing the old secret file. Do not source either runtime file into the interactive shell:

```bash
export CME_COMPOSE_ENV_FILES='/etc/cme/runtime.env:/etc/cme/release.env:/etc/cme/runtime-next.env'
docker compose --env-file /etc/cme/runtime.env --env-file /etc/cme/release.env --env-file /etc/cme/runtime-next.env config --quiet
```

After the separately approved cutover, recreate only `api` with the same ordered environment files. To roll back application credentials, restore the prior environment-file list and recreate only `api`; do not edit PostgreSQL role passwords during rollback. Keep both roles available until the release owner closes the rollback window. PostgreSQL credential revocation is a separate, approved operation.

## Failure handling

The utility never overwrites an existing output file or role. A failure before database commit leaves existing roles unchanged and removes only the temporary file it created. If validation fails after role creation committed, the secret file is retained and the tool reports that the staged role may exist; inspect the exact role and preserve that credential securely before cleanup. Do not blindly rerun with the same role name. All connection and database error details are suppressed from output.
