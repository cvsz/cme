# CMe CheerTsuMe' Enterprise Platform

## Product scope
CMe is an enterprise commerce operating system combining ERP, commerce operations, AI-assisted content production, analytics, automation, and an administration control plane.

## Application architecture
- Web/Admin: Next.js + TypeScript
- API: FastAPI + Python
- Database: PostgreSQL
- Queue/cache: Redis
- Object storage: MinIO/S3-compatible
- Workflow automation: n8n
- Media: FFmpeg
- Local AI default: CPU-capable local provider; external providers are optional adapters
- Local deployment: Docker Compose
- Scale path: k3s/Kubernetes

## ERP domains
Products/PIM, inventory, warehouse, procurement, suppliers, manufacturing, BOM, lot/batch traceability, quality, sales orders, fulfillment, returns/RMA, CRM, accounting/GL/AP/AR, expenses, tax/VAT integration boundary, assets, HR integration boundary, billing, multi-company, multi-branch, multi-currency, and analytics.

## Commerce and AI domains
TikTok integrations must use supported official APIs and explicit user authorization. AI features cover hooks, scripts, captions, localization, content calendars, media jobs, subtitles, voice adapters, and configurable analytics heuristics. No heuristic is represented as TikTok's proprietary ranking algorithm.

## Security baseline
Tenant isolation, RBAC, short-lived access tokens, refresh-token rotation, external-token encryption at rest, secret redaction, request validation, rate limits, audit events, least-privilege service credentials, signed/idempotent billing webhooks, and allowlisted admin operations.

## Delivery states
Documentation is DESIGN evidence. Code is IMPLEMENTED only after committed implementation exists. A capability becomes VERIFIED only after its relevant tests or operational checks pass on the exact commit. Production readiness requires deployment, recovery, security, capacity, and operational evidence.
