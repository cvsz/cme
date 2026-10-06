# Production Verification Kit

Run these checks against the exact deployed release. Store resulting logs and timestamps in the operator evidence system; do not commit secrets.

## Deployment smoke

Set CME_BASE_URL to the production-equivalent endpoint and run:

    sh scripts/verify-deployment.sh

This verifies public application liveness and dependency readiness. DNS/TLS/routing remain owned by the infrastructure operator.

## Release identity and rollback

The deployment process must write the immutable deployed commit or image digest to an operator-controlled release evidence file. Set CME_RELEASE_FILE and CME_EXPECTED_RELEASE, then run:

    sh scripts/verify-release.sh

For a rollback drill, deploy the prior known-good immutable artifact, run the verifier with that prior identity, exercise critical smoke paths, then restore the intended current artifact and verify again. Record elapsed recovery time. Do not claim rollback or RTO until this has been exercised against the target environment.

## Capacity

Choose thresholds from product SLOs rather than repository defaults. Example:

    python3 scripts/load_probe.py --url "$CME_BASE_URL/health" --requests 1000 --concurrency 25 --max-p95-ms 250 --max-error-rate 0.01

The probe exits non-zero if either threshold is exceeded. Repository CI must not invent production capacity targets.

## Required operator evidence

Record exact artifact identity, environment, start/end timestamps, smoke result, restore/rollback result, measured RPO/RTO, load parameters/results, DNS/TLS verification, monitoring/alert delivery result, and secret-rotation evidence.

CMe supplies application verification commands only. zworkforce remains responsible for zeaz.dev infrastructure operations including Cloudflare, DNS, tunnels and shared deployment controls.
