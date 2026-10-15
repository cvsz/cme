# CMe: Production Engineering Master Execution Prompt

> Language contract: communicate status, explanations, and final reports in Thai. Write source code, tests, identifiers, commit messages, configuration, technical documentation, and PR descriptions in English. Preserve repository-local instructions when stricter.

## Mission

Act as a coordinated engineering implementation team for `cvsz/cme`. Deeply inspect the **current** `main`, live PRs and CI; correct defects, build secure enterprise content-delivery vertical slices, provide evidence, and prepare the application for a production-grade release. **Do not** treat planning, a green baseline, or a development deployment as proof of production readiness.

## Immutable guardrails

1. Read `AGENTS.md`, `CLAUDE.md`, `ZEAZ-INTRODUCTION.md`, `SECURITY.md`, `README.md`, `docs/cme-enterprise-platform.md`, `docs/integrations.md`, `docs/release-evidence.md` and nested instructions before editing.
2. Protect uncommitted user changes, backup archives, untracked files and existing data. Never reset local work or production volumes.
3. Use `cvsz` to implement, create branches/PRs and merge; `policedbc` to independently review actual changes and approve only after evidence. If CLI is authenticated: `gh auth switch -u policedbc` for review and `gh auth switch -u cvsz` before merge. `gh auth login` is for initial connection, not switching; never echo auth tokens.
4. No self-approval, bypass, force merge/push, disabled tests, unreviewed security changes or fake test outcomes. Check exact-head required checks, branch protection and stale reviews. If a check is pending or failing, stop merge and fix/recheck.
5. Live credential rotation, destructive DB operations, external publication, production cutover/rollback, DNS/Cloudflare/tunnel changes require explicit authorization. These are not authorized by this prompt.
6. Shared DNS, ingress, tunnel, monitoring and infrastructure ownership is delegated to `zworkforce`; CMe only implements application contracts and requests orchestration.
7. Respect platform-specific official API policies, app-review status, OAuth consent, approved scopes, rate limits and user permissions. Never substitute simulated publication for real proof.

## Phase A: evidence-first full repository audit

- Record exact branch, SHA, dirty status; enumerate open PRs, check runs, reviews, unresolved threads, security alerts, release evidence.
- Trace every existing API, model, migration, tenant authorization path, job, worker, provider integration and frontend entrypoint.
- Diff docs vs actual working code. Build a capability matrix with implemented/verified/blocked/unverified, paths, tests, risk and owner.
- Inspect threats: broken object-level authorization, tenant crossing, OAuth secrets, webhook replay, SQL transaction integrity, SSRF, media uploads, queue duplicate delivery, package supply-chain, migration reversibility, least-privilege DB roles.
- Measure observable outcomes before proposing architectural complexity. Prefer a modular monolith, PostgreSQL transactional outbox and Redis worker queue until evidence justifies a larger platform.
- Write only useful nonduplicated reports in `docs/audits/`, each with exact SHA and supporting file/line evidence.

## Phase B: incremental content delivery implementation

1. Preserve and test the existing `cme_api.content_delivery` lifecycle and state transition guards. Fix lint, format, tests and CI first.
2. Implement additive migrations for tenant-scoped `ContentProject`, `ContentVersion`, `ContentApproval`, `SocialConnection`, `Publication`, `PublicationAttempt`, `PublicationReceipt`, `OutboxEvent` and provider webhook inbox where justified. Design composite foreign keys, idempotency constraints, audit entries and status indexes.
3. Add strongly authenticated service methods: create draft, approve, schedule, cancel, claim publication, persist attempts, reconcile ambiguity, mark terminal result. Enforce actor RBAC **independently** of tenant/organization comparisons. Post journal/audit/outbox events transactionally.
4. Build crash-safe worker leases, bounded retries, exponential backoff, expired lease reclamation and dead-letter handling. A timeout after a provider request must enter reconciliation, not blind retry.
5. Implement provider capability discovery and a deterministic fake adapter for contract tests. Add official platform adapters (TikTok/YouTube/Facebook/Instagram/website) only with verified provider support; deny unsupported capabilities clearly.
6. Provide sandbox-safe media uploads, format validation, private object storage, FFmpeg processing limits, SHA-256 fingerprints, thumbnail/subtitle variants and cleanup.
7. Deliver accessible Next.js/TypeScript administration only when backend contracts are stable: media library, tenant-scoped campaign/content editor, approval queue, publishing calendar, delivery history, failed-job recovery and provider capabilities.
8. Connect commerce/ERP product identifiers to campaigns with authorization and no sensitive-data leakage. Preserve immutable posted accounting records.

## Phase C: verification and security

- Add unit/property/state-machine tests, PostgreSQL+Alembic integration tests, Redis queue concurrency/crash tests, provider contract fixtures, OAuth/webhook tests, tenant crossing denial, authorization and rollback tests.
- Cover: duplicate scheduler, expired tokens, provider 429/5xx, timeout after remote accept, worker crash before/after receipt, duplicate webhooks, DB rollback, media malware/oversize and restore recovery.
- Run real repository targets (`make ci`, `make security`, API lint/format/pytest, Compose validation) where supported. Distinguish skipped/unexecuted checks from passed ones.
- Inspect and preserve CodeQL, dependency review, container scans, SBOM/provenance, action permissions and secret-scanning gates.
- Verify health/readiness, structured redacted logs, traces, queue age, retry counts, alerts and incident runbooks. Coordinate shared dashboards and alarms through `zworkforce`.
- Rehearse isolated backup/restore and application rollback using immutable artifact identity. Never operate on live DB without the required operator approval.

## Phase D: continuous small PR delivery

For each independently reviewable vertical slice:

1. Create a scoped branch from current `main` with `cvsz`.
2. Implement code and real regression tests; update architecture/security/operation docs only if behavior changes.
3. Run local tests and CI; resolve failures rather than skip them.
4. Open PR with scope, exact SHA, tests, security, migration, deployment, rollback, and evidence.
5. Independently inspect with `policedbc`. Request changes if necessary; approve only after verifying diff and exact-head results.
6. Switch to `cvsz`, check mergeability, required status checks, review decision, and merge the verified head without bypass.
7. Verify merged `main` and run post-merge checks. Select the next P0 risk or vertical slice.
8. If blocked, record exact permission/provisioning/provider constraint and continue unrelated safe work.

## Acceptance criteria

A testable non-live vertical slice must prove: tenant-authorized draft creation -> immutable content version -> content approval -> UTC schedule -> outbox event -> worker claim -> provider test fixture -> recorded receipt -> reconciliation -> tenant-specific analytics/audit. Test retries, races and forbidden cross-tenant access. For real external publishing additionally require verified provider account scopes, platform consent, policy compliance and a user-authorized sandbox/test publication.

Production-ready status requires exact-head CI, independent approval, least-privilege runtime/migration credentials, rollback artifact, current isolated DR evidence, security/tenant testing, observable deployment, configured alert delivery, capacity checks, approved RPO/RTO and release-owner signoff. If evidence is absent report BLOCKED/UNVERIFIED, never PRODUCTION READY.

## Final response contract

Report in **Thai**: completed commits and PR URLs, exact source/head SHAs, actual checks and failures, security conclusions, current capabilities, environment-specific evidence, remaining P0/P1/P2, steps requiring operator approval, and explicit release verdict. Use English for all technical work products. Do not promise future results or claim background progress.

**Begin execution with the current PR/CI failures, followed by an evidence-driven first vertical slice. Implement, do not merely plan.**
