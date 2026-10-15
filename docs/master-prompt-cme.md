# CMe Production Engineering — Execution Entry Point

This document is the canonical entry point for executing the CMe master implementation directive. The full directive is maintained at [the content delivery master prompt](ai/prompts/cme-production-content-delivery-master.md). Read and follow that full prompt as a binding implementation task rather than a documentation-only request.

## Start here

1. Inspect current main/PR status and read AGENTS.md, CLAUDE.md, SECURITY.md and applicable architecture/release contracts.
2. Fix any failing CI in open PRs, run exact-head checks and request independent policedbc review before merging as cvsz.
3. Deliver production-grade changes in small tested PRs, starting with durable content publishing persistence, outbox, authorization and reconciliation.
4. Preserve databases, backup artifacts, current CI and shared infrastructure ownership; do not perform live cutovers or external posting without explicit authorization.
5. Report implementation evidence and remaining blockers in Thai; produce code, tests, technical docs and Git metadata in English.

The original comprehensive directive remains in the linked document to avoid maintaining two divergent copies.
