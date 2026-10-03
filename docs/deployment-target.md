# Deployment Target

## Local-first
The first runnable target is Ubuntu/WSL2 using Docker Compose. PostgreSQL, Redis, MinIO and n8n remain private to the application network. Only the web/API ingress is exposed.

## Production path
The scale target is k3s/Kubernetes with separate web/API/workers, autoscaling based on measured workload, managed secrets, network policy, persistent storage, metrics/logs/traces, and controlled rollout/rollback.

## Required evidence before production
- Fresh-clone setup succeeds.
- Lint, type checks, unit/integration tests and security checks pass.
- Container and dependency scans are reviewed.
- Backup and isolated restore drill are recorded.
- Rollback is exercised in a production-equivalent environment.
- Capacity is based on measured p50/p95 job duration and queue behavior.
- Public DNS/TLS and monitoring are verified against the deployed artifact.
