# Production Readiness Audit

**Assessment date:** 2026-10-08 UTC
**Repository:** `cvsz/cme`
**Audited source head:** `c63ffc4c10687ccf7079708c52b41bc2cb44509e`
**Runtime selection:** Docker Compose, FastAPI, PostgreSQL 17, Redis 7
**Assessment scope:** current deployment and production release gates

## Evidence rule

Evidence states follow [ZEAZ-INTRODUCTION.md](../ZEAZ-INTRODUCTION.md): `VERIFIED`, `PARTIALLY VERIFIED`, `UNVERIFIED`, `BLOCKED`, or `NOT APPLICABLE`. A passing source check is not deployment evidence; a healthy development deployment is not a production release.

## Current deployment evidence

| Gate | State | Evidence |
| --- | --- | --- |
| Source deployment identity | `PARTIALLY VERIFIED` | The audited checkout and supplied deployed SHA are `c63ffc4c10687ccf7079708c52b41bc2cb44509e`. The running API image ID is `sha256:8b3af7c3b6769f5615e000772d9a0bb7e2027634978cc695a04025c3041d9661`; its OCI revision label is empty, so image-to-commit linkage is not independently verified. |
| Compose configuration | `VERIFIED` | `docker compose config --quiet` succeeds. |
| API, PostgreSQL, and Redis health | `VERIFIED` | Live Compose inspection reports all three healthy, with API bound to `127.0.0.1:8000` and no host-published PostgreSQL or Redis ports. |
| Container restarts | `VERIFIED` | The three inspected services report restart count zero. |
| API liveness and readiness | `PARTIALLY VERIFIED` | Loopback `/ready` returned HTTP 200 and reported `environment=development`; it does not establish production mode. |
| Database schema | `VERIFIED` | PostgreSQL reports version 17.11, Alembic revision `0004_accounting_journal`, and ten public base tables. |
| Runtime database privilege | `VERIFIED` | Read-only role inspection reports current role `cme` has `rolsuper=true`. This is a production blocker. |
| Application logs | `PARTIALLY VERIFIED` | Sanitized inspection found no error, exception, traceback, or critical markers in the last 16 API log lines. This is a short development sample, not production observability evidence. |
| Backup artifact | `VERIFIED` | `backups/cme-pre-production-20261008-070952.dump` exists (23,204 bytes, mode `0600`); its mode-`0600` SHA-256 sidecar matches, `pg_restore --list` succeeds, and a fresh restore into a new database in isolated PostgreSQL 17.11 completed in 13 seconds. Read-only validation passed at `0004_accounting_journal` with 10 tables, all 7 required indexes, all 17 required constraints, balanced posted journals, and an application readiness smoke test. Evidence: `/tmp/cme-p0-drill/operator-backup-drill-evidence.json`. The backup predates this audit and was not freshly captured from the current live database. |
| Production credential configuration | `BLOCKED` | The current runtime is development. Live secrets and production role setup must be explicitly authorized and validated through the documented rotation process. |
| Production cutover | `BLOCKED` | The deployment is not in production mode. Cutover requires approved secrets, preflight, a staged least-privilege runtime role, and explicit operator authorization. |
| Effective GitHub governance | `BLOCKED` | `gh` is authenticated as `cvsz` with repository `ADMIN`, but GitHub returned `Branch not protected` for `main`. The repository Actions token is read-only and cannot approve reviews. |
| Independent review | `BLOCKED` | `policedbc` has `read` permission on this repository, so that account cannot approve a pull request. A separate write-authorized reviewer is required. |
| DNS, Cloudflare, and shared tunnels | `NOT APPLICABLE` | These controls remain owned by `zworkforce`; CMe must not migrate or change them. The production operator must attach their separate current evidence before a public release. |

## Prioritized backlog

Priority describes release impact. Evidence state remains separate from P0/P1/P2 priority.

### P0 — production release blockers

1. Stage a dedicated runtime database role, verify its exact least-privilege grants, and switch only after a tested rollback path and explicit operator approval. The active `cme` role is currently a superuser.
2. Establish and independently verify a separate migration role with required DDL/object ownership. Do not grant runtime superuser or migration rights.
3. Configure production URLs and PostgreSQL bootstrap secret through protected files/secret injection; run the new production validator and cutover preflight against those exact inputs.
4. Create a new non-overwriting backup from the current deployment, validate its checksum/archive, and complete a restore drill against that protected artifact. The isolated procedure test below does not satisfy this live-data gate.
5. Retain the exact prior application image/digest tied to its Git SHA. The current running image has no `org.opencontainers.image.revision` label, so it cannot pass the new rollback identity gate as-is.
6. Enable and read-back-verify `main` branch protection with the CMe required checks, then obtain exact-head CI and a separate write-authorized independent approval. The branch is currently unprotected and `policedbc` is read-only.
7. Obtain operator authorization for live role creation, production configuration changes, and API cutover. These actions have not been performed.
8. Complete post-cutover health, readiness, image identity, restart, dependency, migration, log, restore, and rollback verification before declaring a release.

### P1 — reliability and security acceptance

1. Measure production-equivalent restore and application rollback; compare results with owner-approved, configurable RPO/RTO targets.
2. Verify authentication and tenant isolation regression suites on the exact PR head and inspect current dependency, CodeQL, secret-scanning, and container-scan results.
3. Demonstrate production monitoring and alert delivery, disk-capacity monitoring, backup-failure detection, and actionable incident runbooks.
4. Exercise API rollback against an isolated environment using the previous deployed application artifact and current schema before accepting the live procedure.
5. Run capacity/load checks against thresholds approved from actual workload and SLOs.

### P2 — follow-up improvements

1. Add production-equivalent observability dashboards and alert routing through the existing ZEAZ stack where supported, coordinated by `zworkforce`.
2. Automate release evidence retention and policy comparison after the release owner selects RPO/RTO values.
3. Add signed artifact provenance and long-term artifact retention where supported by the repository's release platform.

## Repository procedure verification

The following checks were run on 2026-10-08 against an isolated Compose project named `cme-p0-drill`; they did not change the current deployment or its database volume:

- API suite: `58 passed`; three deprecation warnings were reported.
- Repository script and bootstrap tests: `23 passed`, including production preflight policy validation, secret strength, credential cleanup, backup safety, and rollback approval gates.
- Production configuration, shell syntax, workflow YAML, repository structure, Ruff checks, and formatting checks passed for the changed files.
- The supplied backup was restored into a newly created database in the isolated PostgreSQL 17.11 test project. Restore ran from `2026-10-08T03:50:12Z` to `2026-10-08T03:50:25Z` (13 seconds). Checksum, archive format, schema revision, base tables, required indexes and constraints, posted-journal consistency, and a read-only application readiness smoke test passed using the runtime role with read-only grants confined to that isolated restored database. A separate isolated backup ran from `2026-10-08T03:59:44Z` to `2026-10-08T03:59:48Z` (4 seconds), producing a validated 23,605-byte archive and checksum. Evidence: `/tmp/cme-p0-drill/operator-backup-drill-evidence-final.json` (mode `0600`). The original deployment database and backup bytes were not modified. The supplied backup is not a fresh backup from the current live database, and no approved RPO/RTO target was evaluated.
- Isolated preflight passed after verifying separate runtime/migration roles, the runtime role's least privilege, and the migration role's schema ownership/DDL rights. Test-only RPO/RTO sentinel values were supplied; no approved production targets were tested.
- Release verification wrote `/tmp/cme-p0-drill/release-evidence.json` with mode `0600`. The manifest records a test image and test-only policy sentinels; it is not a production release manifest.
- Rollback compatibility and the API-only rollback workflow passed against a container image rebuilt from source SHA `c63ffc4c10687ccf7079708c52b41bc2cb44509e`. The exact image artifact previously deployed was unavailable, so its rollback identity remains unverified.

The temporary test project and evidence remain outside the repository. The existing `backups/` directory and generated `apps/api/cme_api.egg-info/` artifact were not staged. A checksum sidecar was added beside the supplied backup without changing the backup itself; the sidecar remains untracked.

## Change status at audit

The production-hardening changes are implemented on a feature branch from the audited head. Until exact-head CI, repository review, and merge complete, these source changes are `IMPLEMENTED LOCALLY` only. No production environment, credential, database role, image deployment, DNS, or shared infrastructure was changed during this audit.

## Release decision

The release is **BLOCKED** for production. The development services are healthy, but the current runtime mode is development, the application database role is a superuser, production secrets and a current verified backup are not evidenced, and effective repository governance and live cutover have not been accepted.
