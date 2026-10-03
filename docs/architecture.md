# CMe Enterprise Platform Architecture

## Purpose

CMe is a modular commerce and ERP application. Repository governance is inherited from the ZEAZ baseline, while runtime implementation is CMe-specific.

## Runtime layers

### Web and administration
Next.js/TypeScript is the target user/admin surface.

### API and domain
FastAPI/Python owns authenticated application APIs and ERP domain rules. Domain invariants must not depend on HTTP handlers.

### Data
PostgreSQL is the transactional system of record. Redis supports queues/cache and MinIO/S3-compatible storage holds media/object payloads.

### Workers and automation
Background workers execute asynchronous jobs. n8n may orchestrate workflows but never owns authorization or bypasses application policy.

### ERP invariants
Inventory uses an append-only movement ledger with derived balances. Accounting uses balanced double-entry journals. Tenant/company/branch boundaries are explicit on persisted business records.

### Integrations
External integrations use provider adapters, encrypted credentials, idempotent operations and audit events. TikTok capabilities are limited to approved official APIs/scopes.

## Repository control plane

AGENTS.md, SECURITY.md, GOVERNANCE.md, CI workflows and scripts/github_admin.py remain the governance layer. Their presence is not production evidence; effective state and exact-head checks must be verified.

## Production boundary

A committed capability is IMPLEMENTED. It is VERIFIED only after its applicable tests/checks pass on the exact commit. Production readiness additionally requires deployment, recovery, security, observability and capacity evidence.
