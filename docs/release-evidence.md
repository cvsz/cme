# Release Evidence

This file defines what repository automation proves and what remains an environment gate.

## Repository workflow coverage

- repository structure and bootstrap tests
- API lint, format, migrations, PostgreSQL behavioral tests and container build
- CodeQL and dependency review
- non-root container runtime, SBOM generation and fixable HIGH/CRITICAL image scan
- isolated PostgreSQL backup/restore drill with exact-file SHA-256 verification, schema/index/constraint/data checks, read-only application readiness, and timing evidence
- isolated least-privilege PostgreSQL runtime-role staging and authenticated access verification
- fresh-clone repository/Compose/container verification
- application liveness/readiness and privacy-safe request observability tests

## Production release checklist

- [ ] Required checks pass on the exact pull-request head and required independent reviews are complete.
- [ ] Candidate configuration selects `production`, validated secret sources, separate least-privilege runtime and migration roles, and the same database target.
- [ ] Candidate image is tied to a full Git SHA and its immutable image ID/digest is recorded.
- [ ] A new protected backup has a verified checksum and archive format, and an isolated restore drill against that artifact passes.
- [ ] The exact prior application image passes schema compatibility and the isolated API rollback drill.
- [ ] The release owner supplies approved RPO/RTO targets and the measured evidence is compared with them.
- [ ] Security scans, tenant/authentication regression tests, service privacy, and operational monitoring evidence are reviewed.
- [ ] The operator explicitly authorizes production credential changes and cutover.
- [ ] Post-cutover verification writes a protected release manifest and confirms health, readiness, dependencies, schema revision, image identity, restart counts, and backup evidence.

An unchecked item is not accepted as verified. A production cutover authorization does not follow from green repository CI, a local test stack, or a successful restore alone.

## External production gates

These cannot be truthfully verified by repository CI alone:

- production-equivalent restore and application rollback with measured RPO/RTO
- capacity/load targets derived from real workload
- deployed artifact identity
- public DNS/TLS and routing
- production metrics/logs/traces and alert delivery
- runtime secret-store and credential rotation evidence

CMe does not own Cloudflare, Terraform, DNS or shared tunnel resources. Those checks belong to the designated infrastructure operator (zworkforce).

Workflow coverage describes what the configured jobs are designed to test. A release decision must use successful checks on the exact pull-request head and current environment evidence. Locally implemented or pending workflows are not CI evidence. Effective GitHub governance requires authenticated provider read-back, not a helper script or repository configuration file.

A release is production-ready only when every applicable external gate is backed by current environment evidence. Green repository CI is necessary but not sufficient.
