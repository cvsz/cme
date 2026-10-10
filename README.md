# CMe CheerTsuMe' Enterprise Platform ERP

CMe is a production-structured commerce and ERP platform being built on the ZEAZ secure repository baseline. It combines ERP operations, commerce workflows, AI-assisted content production, analytics, automation, and an administration control plane.

> Current state: CMe has a healthy development deployment and repository CI coverage for core API behavior. Production release remains blocked until a least-privilege runtime role, production configuration, current restore evidence, exact-head CI/review, and authorized cutover are verified. See the [production readiness audit](docs/production-readiness-audit.md) and [release evidence gates](docs/release-evidence.md).

## Target stack

- Next.js + TypeScript for web/admin
- FastAPI + Python for APIs and workers
- PostgreSQL for transactional data
- Redis for cache/queues
- MinIO/S3-compatible object storage
- n8n for workflow orchestration
- FFmpeg for media processing
- Local CPU-capable AI by default; external AI providers are optional adapters
- Docker Compose for local-first deployment
- k3s/Kubernetes as the scale path

## Product domains

ERP scope includes PIM/SKU, inventory, warehouse, procurement, suppliers, manufacturing/BOM, lot/batch traceability, quality, sales/OMS, fulfillment, returns, CRM, accounting/GL/AP/AR, billing, multi-company, multi-branch, multi-currency and enterprise analytics.

Commerce scope includes TikTok integration boundaries, content workflows, AI-assisted scripts/captions/localization, media jobs, content calendar, analytics, automation and admin controls.

## Architecture and setup

Read these before implementation:

- [Enterprise platform architecture](docs/cme-enterprise-platform.md)
- [ERP domain model](docs/erp-domain-model.md)
- [Deployment target](docs/deployment-target.md)
- [Integration boundaries](docs/integrations.md)
- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
- [Security policy](SECURITY.md)
- [Implementation checklist](IMPLEMENTATION-CHECKLIST.md)
- [Roadmap](ROADMAP.md)
- [Release evidence](docs/release-evidence.md)
- [Disaster recovery](docs/disaster-recovery.md)
- [Database credential rotation](docs/database-credential-rotation.md)
- [Production verification](docs/production-verification.md)
- [Production operations](docs/production-operations.md)
- [Production readiness audit](docs/production-readiness-audit.md)

### Repository baseline validation

```bash
make validate-template
```

The inherited application `setup/lint/test/build/security` Make targets remain gates: they must be replaced with real stack-specific commands as implementation lands. A placeholder target is not treated as success.

### GitHub administration

Preview/verify repository controls with the inherited administration helper and an authenticated repository administrator:

```bash
python3 scripts/github_admin.py --repo cvsz/cme --verify
```

Apply only after reviewing the planned changes:

```bash
python3 scripts/github_admin.py --repo cvsz/cme --apply
```

## Security rules

- Never commit credentials, tokens, private keys or production secrets.
- Enforce tenant isolation on every tenant-scoped operation.
- Encrypt external provider tokens at rest.
- Use least-privilege service credentials and GitHub Actions permissions.
- Admin operations are allowlisted and audited; the UI must not expose arbitrary shell execution.
- Billing webhooks are signature-verified and idempotent.
- TikTok capabilities use supported official APIs and explicit user authorization.
- Generated/third-party content is untrusted input.

## Delivery policy

CMe follows the ZEAZ evidence states. Documentation is design evidence, committed code is implementation evidence, and a feature becomes verified only after relevant checks pass on the exact commit. Production readiness additionally requires deployment, rollback, backup/restore, security, capacity, observability and incident-response evidence.

## Development workflow

1. Read `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md` and the relevant design docs.
2. Work on a reviewable feature branch.
3. Add tests with implementation where practical.
4. Run relevant validation/security checks.
5. Update documentation and migration/rollback notes.
6. Open a PR and merge only with required exact-head checks satisfied.

## License

MIT. See `LICENSE`.
