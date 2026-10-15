# Content Delivery Foundation — Slice 1

## Current scope

The pure `cme_api.content_delivery` policy module defines publication states,
explicit transition rules, tenant/organization scope comparison, and UTC
scheduling validation. This is a tested *foundation*, not an end-to-end
publishing implementation.

The policy requires approval before scheduling/queueing and treats ambiguous
provider responses as reconciliation events. Terminal states do not transition.

## Not yet implemented

- Durable publication, attempt, receipt, media asset and provider-account tables
- Request authorization/RBAC and audited approval identities
- Transactional outbox, worker leases, retries, crash recovery and deduplication
- Encrypted OAuth tokens and official provider API connectors
- Media storage, FFmpeg processing and content studio UX
- End-to-end tests with provider sandbox credentials

## Next vertical slice

Implement additive Alembic migrations with tenant- and organization-scoped
foreign keys, a transactional publication service (including actor authorization
and immutable events), a durable outbox with idempotent worker execution, and
real PostgreSQL concurrency tests. Do not expose a live publishing endpoint
before token security, provider consent and reconciliation are verified.

Cloudflare, DNS, tunnels and shared infrastructure remain owned by
`zworkforce`. CMe supplies contracts only.

## Verification

```bash
cd apps/api
.venv/bin/ruff check cme_api/content_delivery.py tests/test_content_delivery.py
.venv/bin/ruff format --check cme_api/content_delivery.py tests/test_content_delivery.py
.venv/bin/pytest -q tests/test_content_delivery.py
```

Release acceptance remains governed by `docs/release-evidence.md` and
`docs/production-readiness-audit.md`.
