# Content Publication Persistence — Foundation Slice

This slice introduces `content_publications` and `publication_outbox_events` tables with scoped composite foreign keys, tenant/organization idempotency uniqueness, and an additive Alembic migration (`0005_content_publication`). `/ready` now requires this schema revision.

## Safety and operational contract

- This is database groundwork only. No API routes, publisher workers, provider credentials, or external publishing are enabled.
- All outbox inserts must occur in the **same PostgreSQL transaction** as their associated publication state changes. This invariant is not yet implemented by a service.
- Application services must independently enforce actor authentication, RBAC, and tenant/organization authorization before mutation. A client-provided tenant ID does not grant access.
- The event key provides a database uniqueness guard, not an end-to-end guarantee of exactly-once remote publication.
- Before running the migration outside disposable test environments, take a verified backup and follow the release owner's migration and rollback process. The documented downgrade drops these new tables and is destructive once data exists; **never run it automatically against production**.
- Worker leases, retries, event delivery and reconciliation remain future independently reviewable vertical slices.

## Validation

Run `ruff check apps/api`, `ruff format --check apps/api`, and API pytest. Exercise Alembic upgrade and schema constraints on disposable PostgreSQL; review repository CI results on the exact PR head. Do not infer production-ready status from tests alone.
