# CMe Repository Engineering and Release Report

**Audit date:** 2026-11-03

**Status:** `PARTIAL` — repository checks pass and local source defects were fixed; the local drill API is not ready, deployment provenance is invalid, and production database/Redis readiness remains unverified.

> Follow-up after the audit snapshot: an authenticated local `zRedis` service was created and connected to the current repository Docker networks. The ignored CMe `.env` now uses a CMe-specific ACL user restricted to `PING`. The existing drill API container was not recreated, so this does not verify Redis readiness in that running process or change production configuration.

## 1. Executive Summary

The audit found that production preflight accepted any forty-character hexadecimal value as a release SHA, including forty zeroes. The running `cme-p0-drill-api-1` image uses that zero value, which is not a Git commit. The preflight now requires the SHA to equal the checkout `HEAD`, the Compose build context to resolve to this repository, and all image/release source paths to match Git. It also rejects zero SHA values.

Other fixes bound and hash in-memory login rate-limit keys, reject idempotency-key reuse with a different journal payload, restrict Docker build context to API runtime inputs, make Docker health reflect `/ready`, and capture the candidate image ID before cutover in the deployment instructions.

The existing local drill container was not changed. It reports Docker `healthy` under its older `/health` check, but `/ready` returns HTTP 503. At inspection time its configured `postgres` and `redis` names did not resolve on its network. The shared `zPostgreSQL` service is reachable, but its current catalog has no CMe `cme` database or `cme` role. The audit did not change shared PostgreSQL, its credentials, production deployment, or GitHub state. A later local Redis service and a CMe-specific local Compose credential were created, but the drill API container was left untouched.

## 2. Repository Identity

- Repository: `cvsz/cme`
- Branch: `feat/p0-production-readiness`
- Audit snapshot HEAD: `76d392e100e2dc4ff289dfd2b4f0494045f73218`
- Remote: `git@github.com:cvsz/cme`
- At the audit snapshot, no commit, push, merge, release, or deployment had been performed. Later synchronization and delivery are recorded in Git history.
- Existing untracked files were preserved, including `backups/`, `docs/engineering/`, `docs/master-prompt-cme.md`, `full-codex-master-prompt.md`, and generated `apps/api/cme_api.egg-info/`. Backup contents were not inspected.

## 3. Scope and Investigation Coverage

Reviewed repository instructions and governance, README and development/security/release documentation, Compose and Docker build configuration, API settings/authentication/session/accounting/analytics/integration modules, Alembic migrations, production preflight/verification/rollback and backup scripts, API and repository tests, CI/security workflows, local Git/GitHub state, the local drill container, and read-only shared PostgreSQL metadata.

The repository currently contains a FastAPI API and foundational services, PostgreSQL/Alembic persistence, Redis readiness checks, and operational scripts. The broader ERP and commerce domains in the README are product scope; this audit does not establish that all of those features exist or are production-complete. No frontend application directory was found.

## 4. Architecture and Module Inventory

- API: `apps/api/cme_api/` with authentication, password/session security, tenant-scoped models, accounting, analytics, observability, configuration, database access, and TikTok transport.
- Persistence: SQLAlchemy models and migrations `0001_cme_core` through `0004_accounting_journal`; tenant-scoped foreign keys and journal immutability triggers are present.
- Runtime: Docker image, Compose PostgreSQL/Redis/API services, readiness endpoint, production preflight, image verification, rollback checks, and backup/restore scripts.
- Delivery: GitHub Actions for API CI, CodeQL, dependency review, DR/supply-chain, production verification tooling, and fresh-clone validation.

## 5. Findings and Remediation Status

| Severity | Finding and evidence | Status |
| --- | --- | --- |
| High | The drill image `cme-api:0000000000000000000000000000000000000000` was created on 2026-10-08 with the same all-zero OCI revision label. `git cat-file` does not recognize that value as a commit. The old preflight only checked SHA shape. | Fixed in source: source identity now requires the actual `HEAD`, repository build context, and clean image/release source paths. Regression tests reject all-zero, wrong-head, dirty, or untracked source paths. |
| High | The existing drill container is configured for `CME_APP_ENV=production` but is not ready: `GET /ready` returns 503. At inspection, `postgres` and `redis` did not resolve; `zPostgreSQL:5432` was reachable, but the shared server had no `cme` database or role. | Shared local `zRedis` was subsequently created and the drill network can resolve it, but the running container's Redis URL/environment was not changed. CMe database/role provisioning and drill reconfiguration remain blocked pending operator authorization. |
| Medium | The old image health check probes only `/health`, so Docker says `healthy` while required dependencies are unavailable. | Fixed in source: the image health check now calls `/ready`; operations documentation explains the distinction. Existing container was not recreated. |
| Medium | Docker build context previously contained unrelated repository files, including local backup and configuration paths. | Fixed: `.dockerignore` allowlists only the Dockerfile's API package, migrations, and metadata inputs. Final build context measured 14.16 KB. |
| Medium | Login throttling kept an unbounded in-process map keyed by IP and raw email. | Fixed locally: email length is bounded, keys are hashed, expired buckets are reclaimed, and the number of buckets is capped. Residual: this limiter is process-local and does not coordinate multiple API instances. |
| Medium | `post_journal()` returned an existing journal for a duplicate key without comparing the new request payload. | Fixed locally: replay compares description and normalized account/debit/credit lines; a different request raises `AccountingError`. No schema change was needed. |
| Medium | Deployment instructions set the expected image ID from the running container after cutover, making the expected identity self-referential. | Fixed in documentation: capture and check the candidate image ID/revision before cutover, then verify the running service against that captured ID. |

## 6. Changes Implemented

- `.dockerignore` — limits build context to runtime inputs.
- `Dockerfile` — Docker health status now follows dependency readiness.
- `apps/api/cme_api/auth_api.py` — caps login identity size and in-memory buckets; hashes rate-limit identities.
- `apps/api/cme_api/accounting.py` — validates duplicate journal requests before returning an idempotent result.
- `apps/api/tests/test_login_rate_limit.py` and `apps/api/tests/test_accounting_service.py` — regression coverage for bucket bounds, expiry, input length, and idempotency replay.
- `scripts/production/preflight.py` and `tests/test_production_preflight.py` — verify exact Git source/build context and reject invalid or dirty release inputs.
- `tests/test_production_verify.py` — checks Docker healthcheck contract.
- `docs/production-verification.md` and `docs/production-operations.md` — document source identity, candidate image capture, readiness semantics, and the observed local drill blocker.
- `Final-Report.md` — this evidence report.

## 7. Tests and Verification Evidence

`make ci` completed with exit code 0 on the final implementation:

- `python3 scripts/validate_repo.py` — passed; repository structure and Markdown links valid.
- `python3 -m unittest discover -s tests -v` — 25 passed.
- `apps/api/.venv/bin/ruff check apps/api` — passed.
- `cd apps/api && .venv/bin/pytest` — 64 passed, 4 deprecation warnings.
- `python3 -m compileall -q apps/api/cme_api` — passed.
- `make ci` tracked-source secret scan — passed.
- `apps/api/.venv/bin/ruff check --config apps/api/pyproject.toml scripts/production/preflight.py tests/test_production_preflight.py tests/test_production_verify.py` — passed.
- `python3 -m unittest discover -s tests -p 'test_production_preflight.py' -v` — 7 passed.
- `apps/api/.venv/bin/ruff format --check apps/api` — passed after the accounting change (36 files already formatted).

Docker build verification passed using Python 3.12-slim and the allowlisted build context (14.16 KB). Final audit image `cme-api:final-audit-76d392e` has image ID `sha256:5021a15502d6c4bdc84286d0556a82ec065885ce9122fb266e2095a01c77b911`, its OCI revision label matches the repository SHA, the healthcheck probes `/ready`, and `docker run --rm --entrypoint=id cme-api:final-audit-76d392e -u` returned UID `100`. This image was built for local verification only and was not deployed.

The local API test environment used Python 3.14.4. The container build uses Python 3.12. The passing local checks do not substitute for exact-head hosted CI or production validation.

Post-sync pre-commit verification ran after the local branch fast-forwarded to `origin/main` at `26bf12178faaf0fa37b91602d1b4b384ee360e12`: `make ci` exited 0, including repository validation, 25 root unit tests, Ruff, 72 API tests (4 deprecation warnings), compileall, and the tracked-source secret scan. These checks ran against the source changes before commit; hosted CI and production checks remain separate.

## 8. Security Assessment

- The local secret scan checks tracked source files and passed. Untracked backups were not inspected; `.dockerignore` excludes them from image build context.
- GitHub currently reports zero open Code Scanning alerts and zero open Dependabot alerts. The latest observed CodeQL success is on `main` at `26bf12178faaf0fa37b91602d1b4b384ee360e12`, not this worktree.
- Trivy and `pip-audit` were unavailable locally, so no local dependency/image vulnerability scan was completed for this candidate.
- The shared PostgreSQL service was queried read-only for CMe database/role existence. No CMe DB or role was found; no customer rows or secrets were read.
- Production database privileges, current production image identity, external backup freshness, restore, rollback, monitoring, and RPO/RTO remain unverified.

## 9. CI, PR, Review, and Approval Status

- No pull request exists for `feat/p0-production-readiness`.
- GitHub returned HTTP 404 for `repos/cvsz/cme/branches/main/protection`; effective main-branch protection is therefore not verified.
- Open PRs observed were #29 (setup-python update), #25 (Python 3.14 base image update), and #24 (content publication persistence); none is this audit branch.
- The latest successful main CodeQL run and PR #24 workflow runs do not validate this local diff. No independent review or approval was performed.

## 10. Deployment and Release Status

`NOT VERIFIED` for production. The existing `cme-p0-drill-api-1` container remains on the old all-zero-tagged image and returns 503 from `/ready`. Its Docker `healthy` status reflects the old `/health` check only. The local validation image was not deployed. Shared PostgreSQL and the CMe production configuration were not changed. The later local `zRedis` setup is not connected to the running drill through authenticated application configuration.

## 11. Residual Risks and Known Limitations

- The local drill requires an authorized CMe-specific database and least-privilege roles on the shared PostgreSQL service. A local shared Redis service and ignored Compose URL now exist, but the running drill retains its previous environment and has not verified authenticated Redis access.
- Login rate limiting remains local to one process; multi-instance deployments need a shared limiter or gateway control.
- Dependency ranges are not locked for the container build. Reproducible dependency resolution and exact-candidate SBOM/image scanning remain release work.
- Current local source paths are modified, so the new preflight correctly rejects this worktree as a release candidate until changes are committed and checked on an exact candidate.
- Hosted CI, independent review, branch protection, production backup/restore, rollback, and post-deployment verification are not established by local tests.

## 12. Rollback and Recovery Instructions

No CMe database or CMe drill API container was changed. Shared local `zRedis` was created separately and was not deployed to production. Source changes can be reviewed/reverted file by file. The local validation images were not deployed and are separate from the running drill container. For production application rollback, follow `docs/production-verification.md` and run the compatibility check against the recorded prior image ID and database revision; do not restore or alter shared PostgreSQL as an application rollback.

## 13. Next Actions

1. Have the database/infrastructure operator provision the CMe logical database and separate runtime/migration roles on the shared PostgreSQL service, and supply the protected Redis/database configuration.
2. Rebuild the drill from a clean exact commit, configure its actual shared-service endpoints, and verify `/ready` before calling it ready.
3. Obtain exact-head hosted checks, branch-protection read-back, and a qualified independent review before any PR merge.
4. Keep production cutover, database changes, credential staging, and release blocked until their separate approvals and operational evidence exist.
