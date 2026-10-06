# Release Evidence

This file defines what repository automation proves and what remains an environment gate.

## Verified by CI

- repository structure and bootstrap tests
- API lint, format, migrations, PostgreSQL behavioral tests and container build
- CodeQL and dependency review
- non-root container runtime, SBOM generation and fixable HIGH/CRITICAL image scan
- isolated PostgreSQL backup/restore drill with exact-file SHA-256 verification
- fresh-clone repository/Compose/container verification
- application liveness/readiness and privacy-safe request observability tests

## External production gates

These cannot be truthfully verified by repository CI alone:

- production-equivalent restore and application rollback with measured RPO/RTO
- capacity/load targets derived from real workload
- deployed artifact identity
- public DNS/TLS and routing
- production metrics/logs/traces and alert delivery
- runtime secret-store and credential rotation evidence

CMe does not own Cloudflare, Terraform, DNS or shared tunnel resources. Those checks belong to the designated infrastructure operator (zworkforce).

A release is production-ready only when every applicable external gate is backed by current environment evidence. Green repository CI is necessary but not sufficient.
