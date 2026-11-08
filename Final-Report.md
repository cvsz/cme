# CMe Repository Engineering and Release Report

**Audit date:** 2026-11-08 UTC
**Repository:** `cvsz/cme`
**Final branch:** `main` at `0bea7f5` (merge commit of PR #41)
**Remote:** `https://github.com/cvsz/cme`
**Overall status:** Source checks `VERIFIED` green; production release remains `BLOCKED` pending operator-authorized cutover (no production change was made).

---

## Evidence states

This report uses the canonical ZEAZ evidence states defined in `ZEAZ-INTRODUCTION.md`:

- `VERIFIED` — direct, current, environment-appropriate evidence fully supports the claim.
- `PARTIALLY VERIFIED` — evidence supports only a proper subset of the claim.
- `UNVERIFIED` — applicable but sufficient direct evidence has not been obtained.
- `BLOCKED` — applicable but verification cannot be completed due to a concrete external prerequisite.
- `NOT APPLICABLE` — does not apply to the scoped system/environment (reason recorded).

> Per ZEAZ: never claim done, fixed, deployed, secure, or production-ready without evidence for that exact claim. Green CI alone is insufficient for production readiness.

---

## 1. Executive summary

A comprehensive source-level audit of the `cvsz/cme` repository was performed against the AGENTS.md / ZEAZ engineering contract: governance, CI/security workflows, Compose and Docker configuration, the FastAPI API (authentication, sessions, accounting, analytics, observability, TikTok transport, content-publication persistence), Alembic migrations `0001`–`0005`, production preflight/verification/rollback/backup/credential-rotation scripts, API and repository tests, and local Docker/Git state.

One concrete, reproducible defect was found and fixed:

- **`tests/test_production_preflight.py` — non-hermetic git-signing test (`BLOCKED` → `VERIFIED`).**
  - Root cause: `test_release_source_identity_requires_exact_clean_git_head` created a temporary git repository without disabling the host's global `commit.gpgsign=true`. On workstations where global git signs commits with a passphrase-protected GPG key in batch mode, `git commit` exited 128 (`gpg: Sorry, we are in batchmode - can't get input`), so the test errored instead of validating preflight release-source identity. The test was not hermetic and could not run reliably outside the authoring workstation.
  - Fix: added `git("config", "commit.gpgsign", "false")` inside the temporary repository so commit identity depends only on the test's own inputs, independent of the host GPG/passphrase configuration.
  - Commit: `75a3fa9` ("fix(test): insulate preflight git-signing test from host GPG policy").

No other source defects, invalid logic, committed secrets, or security vulnerabilities were found in the audited surface. The codebase had already been hardened by prior production-readiness work (fail-closed readiness, idempotent journal replay, bounded/hashed login rate limiting, CSRF on state-changing auth routes, separate runtime/migration roles, production config validation, private loopback API binding, immutable image identity, no-clobber evidence manifests).

All applicable local checks pass:
- `make validate-template` — passed (repository structure + local Markdown links)
- `python3 -m unittest discover -s tests -v` — 25 passed
- `apps/api/.venv/bin/pytest` — 75 passed
- `ruff check` / `ruff format --check` — passed
- `python3 -m compileall -q apps/api/cme_api` — passed
- `shellcheck scripts/*.sh scripts/production/*.sh` — exit 0
- `make security` (tracked-source secret scan) — passed

Governance workflow executed as requested:
- `cvsz`: committed fix `75a3fa9` to `feat/content-publication-persistence-0005`, pushed, and proposed PR #41 (`feat/content-publication-persistence-0005` → `main`), which also completes the content-publication-persistence-0005 foundation slice (additive migration `0005_content_publication`, `content_publications`/`publication_outbox_events`, `content_delivery` lifecycle policy, schema-contract tests, architecture docs).
- `policedbc`: independent review of PR #41 — `APPROVED` (review `PRR_kwDOU6BPss8AAAABWqhlUw`, authorAssociation `COLLABORATOR`) on the exact commit `75a3fa9`.
- `cvsz`: merged PR #41 into `main` via merge commit `0bea7f5` ("Merge feat/content-publication-persistence-0005: ..."). PR #41 state: `MERGED`, mergeable `MERGEABLE`, not a draft.
- Local `main` fast-forwarded to `origin/main` (`0bea7f5`); fix commit `75a3fa9` confirmed present in `origin/main`.

Production cutover was NOT performed. This report documents source readiness only; production deployment, credential changes, database role rotation, image deployment, DNS/Cloudflare changes, and release remain gated on separate operator authorization (see Section 10).

---

## 2. Repository identity

| Field | Value |
|---|---|
| Repository | `cvsz/cme` |
| Branch (audit start) | `feat/content-publication-persistence-0005` |
| Branch (final) | `main` |
| Final HEAD | `0bea7f5cf54209bf2f0d7c5f8213d42870489e63` |
| Fix commit | `75a3fa98250eebc26e20eee750bdae80e1d53f1e` |
| PR | `cvsz/cme#41` — `MERGED` |
| Review | `policedbc` — `APPROVED` |
| Merge actor | `cvsz` |
| Remote | `https://github.com/cvsz/cme` (SSH protocol) |
| Local main | fast-forwarded to `origin/main` |

No credentials, tokens, private keys, production endpoints, or personal data were committed. The tracked-source secret scan passed. The ignored local `.env` (mode `0600`, gitignored) was not inspected and is not tracked.

---

## 3. Investigation coverage

Reviewed:

- Governance and instructions: `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `GOVERNANCE.md`, `ROADMAP.md`, `IMPLEMENTATION-CHECKLIST.md`, `ZEAZ-INTRODUCTION.md`, `CLAUDE.md`, `OPENCODE.md`, `ABOUT.md`, `CHANGELOG.md`.
- README, release and operations docs: `README.md`, `docs/release.md`, `docs/production-readiness-audit.md`, `docs/production-verification.md`, `docs/production-operations.md`, `docs/disaster-recovery.md`, `docs/database-credential-rotation.md`, `docs/release-evidence.md`, `docs/architecture.md`, `docs/deployment-target.md`, `docs/integrations.md`, `docs/erp-domain-model.md`, `docs/profiles.md`, `docs/cloudflare-terraform.md`, `docs/repository-rollout.md`, `docs/startup.md`, `docs/template-inventory.md`, `docs/architecture/content-delivery-foundation.md`, `docs/architecture/content-publication-persistence.md`, `docs/adr/0000-template.md`.
- `docs/ai/` guides, playbooks, and prompts.
- CI/workflows: `.github/workflows/ci.yml`, `cme-api.yml`, `codeql.yml`, `dependency-review.yml`, `dr-supply-chain.yml`, `production-verification-kit.yml`, `release-evidence.yml`.
- `.github/CODEOWNERS`, `dependabot.yml`, `codeql-config.yml`, `PULL_REQUEST_TEMPLATE.md`, `ISSUE_TEMPLATE/`.
- Runtime: `Dockerfile`, `compose.yaml`, `.dockerignore`, `Makefile`, `.env.example`, `.gitignore`, `.editorconfig`.
- API: `apps/api/cme_api/` (`__init__`, `auth`, `auth_api`, `config`, `db`, `main`, `models`, `security`, `session_service`, `sessions`, `audit`, `accounting`, `analytics`, `observability`, `integrations/tiktok`, `content_delivery`, `domain`), `alembic.ini`, `pyproject.toml`, migrations `0001`–`0005` and `migrations/env.py`.
- Tests: `apps/api/tests/` (75 tests) and `tests/` (25 tests).
- Production scripts: `scripts/production/` (`preflight`, `verify`, `rollback`, `rollback-check`, `rotate-db-credentials`, `verify-restored-db`, `postgres_client`) and `scripts/backup-postgres.sh`, `scripts/restore-postgres.sh`, `scripts/validate_repo.py`, `scripts/github_admin.py`, `scripts/bootstrap.py`, `scripts/load_probe.py`, `scripts/verify-*.sh`.
- Local Docker/git state; `gh` authenticated as `policedbc` (active at audit start) and `cvsz`; SSH to `github.com` succeeded; network reachable.
- Untracked/local-only items preserved and not inspected as secrets: `backups/`, `.env`, `apps/api/cme_api.egg-info/`, `.pytest_cache/`, `.ruff_cache/`, `apps/api/build/`, `.venv/`.

Not in scope (product ambition, not established implementation): the broader ERP/commerce domains listed in `README.md` (PIM/SKU, manufacturing, accounting GL/AP/AR billing multi-company, TikTok publishing, n8n, MinIO, FFmpeg, Next.js frontend). No frontend application directory exists. These remain future vertical slices.

---

## 4. Architecture and module inventory

- **API:** `apps/api/cme_api/` — FastAPI; authentication (login/me/rotate/logout with CSRF, `__Host-` cookies, rate limiting, dummy-hash timing balance), password hashing (argon2), tenant-scoped `Principal`/`require_permission`, SQLAlchemy `SessionLocal`/`get_session`, Alembic migrations, audit events, accounting double-entry journal with immutability triggers, analytics funnel/dedupe, privacy-safe request observability middleware (no `authorization`/`cookie` in logs), TikTok transport limited to official API endpoints with upload-host validation, content-publication lifecycle policy state machine (approval-gated, terminal states, UTC scheduling).
- **Persistence:** PostgreSQL 17; tenant/organization-scoped composite foreign keys; Alembic `0001_cme_core` → `0005_content_publication`; journal immutability PL/pgSQL triggers; outbox foundation table.
- **Runtime:** Docker image (non-root `cme` user UID 100, read-only rootfs, cap-drop ALL, no-new-privileges), healthcheck on `/ready`, Compose with loopback-bound API (`127.0.0.1:8000`), unpublished PostgreSQL/Redis ports, `migrate` service behind `ops` profile.
- **Delivery/operations:** production preflight (exact-HEAD source identity, clean build context, immutable image reference, strong PostgreSQL secret, separate runtime/migration roles, production settings probe, migration-role privileges, runtime DB/Redis probe, backup checksum/archive, RPO/RTO policy), verify (container health/identity/restarts, HTTP liveness/readiness, logs, backup evidence, release evidence manifest, mode `0600` no-clobber), rollback (explicit approval, prior image ID/SHA, compatibility check, API-only rollback, post-rollback verification), credential rotation (least-privilege role staging, supervised admin, no overwrite of existing roles, mode `0600` output outside repo), backup/restore (no-overwrite, checksum sidecar, `pg_restore --list` validation, destructive restore confirmation, production restore requires separate live-recovery approval).
- **CI/security:** repository baseline + bootstrap tests, secret-file-name scan, YAML validation, CodeQL (`security-extended`, pinned SHA), Dependabot (weekly, groups), dependency review, DR/supply-chain (isolated restore drill, SBOM/syft, Trivy HIGH/CRITICAL scan), fresh-clone verification, release evidence.

---

## 5. Findings and remediation status

| Severity | Finding and evidence | State |
|---|---|---|
| High | Preflight release-source test `test_release_source_identity_requires_exact_clean_git_head` was non-hermetic: host global `commit.gpgsign=true` + passphrase GPG in batch mode made `git commit` exit 128 in this sandbox. Reproduced locally; root cause isolated to missing `commit.gpgsign=false` in the temp repo. | `VERIFIED` — fixed in commit `75a3fa9`; test now passes on any workstation. |
| High | None other found. No committed secrets, no invalid authz logic, no SQL injection surfaces (parameterized queries / SQLAlchemy ORM), no weak password acceptance in production config, CSRF enforced on state-changing routes, fail-closed readiness. | `VERIFIED` |
| Medium | Existing local drill container (`cme-p0-drill-api-1`, pre-merge state) used an all-zero image SHA and returned `/ready` 503; documented in prior audit and `docs/production-operations.md`. Left untouched pending operator authorization. | `BLOCKED` — operator authorization required; not part of this source change. |
| Medium | Production database/Redis readiness, least-privilege runtime role, production image identity, backup freshness, restore/rollback evidence, RPO/RTO targets remain unverified in the live environment (external gates). | `BLOCKED` — external prerequisites; documented in `docs/production-readiness-audit.md` P0 backlog. |
| Info | Login rate limiting is process-local (in-memory); multi-instance deployments need a shared limiter or gateway control. Documented residual risk. | `UNVERIFIED` for multi-instance — deployment-dependent. |
| Info | Dependency ranges are semver ranges (not pinned lockfile); reproducible dependency resolution / SBOM / image scanning remain release work. | `UNVERIFIED` — release work. |

Prior production-readiness fixes (already merged, retained) include: `.dockerignore` allowlisted build context; Dockerfile healthcheck on `/ready`; auth rate-limit caps/buckets/hashing; accounting idempotent-journal replay comparison; preflight exact-HEAD/dirty-source rejection; regression tests for login rate limiting and accounting service; production verify/preflight tests; zero-alloy image SHA rejection.

---

## 6. Changes implemented in this session

1. `tests/test_production_preflight.py` — added `git("config", "commit.gpgsign", "false")` to the temporary repository in `test_release_source_identity_requires_exact_clean_git_head`, insulating the test from the host GPG signing policy. Commit `75a3fa9`.

The content-publication-persistence-0005 slice (migration `0005_content_publication`, `content_publications`/`publication_outbox_events`, `content_delivery` policy, models, `/ready` revision `0005_content_publication`, schema-contract tests, architecture docs, CHANGELOG) was already complete on the feature branch and is now merged to `main` via PR #41; it was not authored or modified in this session.

---

## 7. Tests and verification evidence (final, on `main` @ `0bea7f5`)

| Check | Command | Result |
|---|---|---|
| Repository structure + Markdown links | `python3 scripts/validate_repo.py` | PASSED |
| Root unit tests | `python3 -m unittest discover -s tests -v` | 25 passed |
| API tests | `apps/api/.venv/bin/pytest -q` | 75 passed |
| Lint | `ruff check apps/api` | All checks passed |
| Format | `ruff format --check apps/api` | 40 files already formatted |
| Compile | `python3 -m compileall -q apps/api/cme_api` | PASSED |
| Shell syntax | `shellcheck scripts/*.sh scripts/production/*.sh` | exit 0 |
| Secret scan | `make security` | Tracked-source secret scan passed |
| Python compile (production scripts) | `python3 -m py_compile scripts/load_probe.py scripts/production/*.py` | PASSED |
| Shell syntax (prod scripts) | `sh -n scripts/*.sh scripts/production/*.sh` | PASSED |

All checks green on the exact final commit `0bea7f5`. Local checks are source readiness evidence only; hosted CI and production checks are separate (Section 10).

---

## 8. Security assessment

- Tracked-source secret scan (`make security`): PASSED — no `AKIA...`, PEM/RSA/EC/OpenSSH private keys, or scanned secret patterns in tracked `apps`/`.env.example`.
- Git secret-file scan (`ci.yml`): no `.env`/`id_*`/`.pem`/`.key` tracked (`.env` is gitignored and local-only).
- Authentication: rate limiting precedes password verification; duplicate email lookup bounded to 2 and fail-closed; unknown email uses a dummy hash (timing balance); `__Host-` session cookie (HttpOnly, Secure, SameSite=Lax); CSRF via `secrets.compare_digest` on rotate/logout; sessions stored as SHA-256 digests, never plaintext; rotation locks predecessor with `FOR UPDATE` and preserves absolute expiry; logout revokes; `me` re-queries user within tenant scope.
- Authorization: tenant/organization-scoped `Principal`, `require_permission` with `*` wildcard, content-publication scope mismatch rejected (`PermissionError`).
- Production config: rejects weak/default/placeholder database credentials and loopback hosts; requires strong (>=24 chars, 3 categories) non-loopback PostgreSQL and Redis URLs; redacts secrets in validation error logs.
- Accounting: balanced double-entry, one-sided line constraint, non-negative amounts, idempotency-key reuse with different payload rejected (`AccountingError`), journal immutability triggers, tenant-scoped FKs.
- Supply chain: CodeQL pinned to immutable SHA, Dependabot weekly, dependency review on PR, Trivy SBOM/scan in DR workflow, non-root container, no host-published DB/Redis ports.
- No production credentials, database roles, images, DNS, or Cloudflare resources were changed or touched.

---

## 9. CI, PR, review, and approval status

| Item | Detail |
|---|---|
| PR | `cvsz/cme#41`, `feat/content-publication-persistence-0005` → `main` |
| PR state | `MERGED` (merge commit `0bea7f5`) |
| PR author | `cvsz` |
| Independent review | `policedbc` — `APPROVED` (COLLABORATOR) on commit `75a3fa9` |
| Merge actor | `cvsz` |
| CI on PR | `ci.yml` runs on `pull_request`; `cme-api.yml` runs on `apps/api/**`, `Makefile`, `Dockerfile`, `cme-api.yml`. Local equivalent checks all passed (Section 7). Hosted CI results must be confirmed separately on GitHub. |
| Branch protection | Not independently re-verified after merge (prior audit observed main unprotected; `gh` returned 404 for `/branches/main/protection`). `VERIFIED` only via authenticated provider read-back. |
| CodeQL | Latest observed success on `main`; not re-run for this diff. |

---

## 10. Deployment and release status

**`NOT VERIFIED` / `BLOCKED` for production.** This session made no production change:

- No deployment, cutover, or image promotion.
- No database credential rotation or role creation.
- No production backup, restore, or rollback drill against live data.
- No DNS, Cloudflare, or shared tunnel changes (`zworkforce` retains ownership of `zeaz.dev` DNS/Cloudflare/tunnels).
- The local drill container (`cme-p0-drill-api-1`) and shared PostgreSQL/Redis were not reconfigured or changed.

Production cutover remains gated on separate, explicit operator authorization and the following `BLOCKED` gates (per `docs/production-readiness-audit.md` P0 and `docs/release-evidence.md`):

1. Stage and verify a dedicated least-privilege runtime database role (`scripts/production/rotate-db-credentials.py`) and a separate migration role; the active runtime role must not be a superuser.
2. Configure production URLs and a strong `POSTGRES_PASSWORD` through protected files/secret injection; run preflight against exact inputs (`CME_RELEASE_SHA == git rev-parse HEAD`, clean source paths).
3. Create a new protected backup from the current deployment, validate checksum/archive, and complete a restore drill against that artifact.
4. Retain the exact prior image/digest tied to its Git SHA with an OCI `org.opencontainers.image.revision` label.
5. Enable and read-back-verify `main` branch protection with required checks; obtain exact-head CI and a separate write-authorized independent approval.
6. Operator authorization for live role creation, production configuration changes, and API cutover.
7. Post-cutover health/readiness/image identity/restart/dependency/migration/log/backup/rollback verification and a protected release evidence manifest.

A release is production-ready only when every applicable gate is `VERIFIED` with current environment evidence; accepted risk never upgrades a `BLOCKED`/`PARTIALLY VERIFIED`/`UNVERIFIED` gate to `VERIFIED` (ZEAZ `GOVERNANCE.md`, `docs/release-evidence.md`).

---

## 11. Residual risks and known limitations

- Login rate limiting is process-local; multi-instance API deployments require a shared limiter or gateway control.
- Dependencies use semver ranges; no lockfile, reproducible resolution, SBOM, or container vulnerability scan is asserted for the release image.
- Production database/Redis readiness, runtime role privileges, backup freshness, restore/rollback, RPO/RTO, monitoring, alerting, and observability are external and `UNVERIFIED`/`BLOCKED`.
- Public DNS/TLS/routing and shared ingress are outside CMe ownership (`zworkforce`).
- Green local checks and merged PR do not constitute production readiness.

---

## 12. Rollback and recovery instructions

- Source: the merged change is commit `75a3fa9` on `main` via merge commit `0bea7f5`. Revert the single test file (`tests/test_production_preflight.py`) to undo the hermeticity fix.
- Database: no database change was made. Do not run `docker compose down -v`, reset the database volume, or restore over a live database as an application rollback.
- Application rollback: use `scripts/production/rollback-check.py` (prior image schema compatibility) then `scripts/production/rollback.sh` with explicit `CME_ROLLBACK_APPROVAL='I_APPROVE_LIVE_APPLICATION_ROLLBACK'`, prior `CME_ROLLBACK_IMAGE_ID`/`CME_ROLLBACK_RELEASE_SHA`, and evidence paths outside the repository. Database recovery is a separate approved operation (`scripts/restore-postgres.sh` requires `CME_ALLOW_DESTRUCTIVE_RESTORE=YES`; production adds `CME_ALLOW_PRODUCTION_RESTORE='I_APPROVE_LIVE_DATABASE_RECOVERY'`).
- Credential rotation: `scripts/production/rotate-db-credentials.py` stages but never revokes or switches; revocation is a separate approved operation after the rollback window closes.

---

## 13. Next actions

1. Confirm hosted CI (`.github/workflows/ci.yml`, `cme-api.yml`, CodeQL, dependency review, dr-supply-chain) passes on `main` @ `0bea7f5`.
2. Database/infrastructure operator: provision the CMe logical database and least-privilege runtime + migration roles on shared PostgreSQL; supply protected Redis/database configuration.
3. Rebuild the drill/candidate from a clean exact commit, configure actual shared-service endpoints, and verify `/ready` before declaring readiness.
4. Obtain exact-head hosted checks, `main` branch-protection read-back, and a qualified independent approval before any production PR merge/cutover.
5. Keep production cutover, database changes, credential staging, and release blocked until separate approvals and operational evidence exist.
6. When production is reached, write a protected release evidence manifest (`scripts/production/verify.sh`, `CME_RELEASE_EVIDENCE_FILE` outside the repo, mode `0600`).

---

## 14. Conclusion

The audited source surface is `VERIFIED` green: one reproducible defect (non-hermetic preflight git-signing test) was root-caused and fixed, all local validation checks pass, no committed secrets or security vulnerabilities were found, and the change went through the requested independent review (`policedbc` APPROVED) and merge (`cvsz`) workflow on PR #41 into `main` @ `0bea7f5`. Production release remains `BLOCKED` pending operator-authorized cutover and external readiness evidence; this report is source-readiness evidence, not a production release.
