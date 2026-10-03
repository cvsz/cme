# Integration Boundaries

## TikTok
Use only current official TikTok APIs supported for the approved application, region, products and scopes. OAuth credentials and user tokens are secrets and must never be committed. Posting actions require user authorization and must respect visibility, consent, review and rate-limit requirements.

## Billing
Billing is provider-adapter based. Monetary amounts are stored in integer minor units. Webhooks require signature verification, replay protection/idempotency and audit events. Currency is fixed by the selected price/subscription contract rather than silently converted after purchase.

## n8n
n8n orchestrates workflows but does not own authorization. Workflows call authenticated service endpoints using least-privilege service credentials and idempotency keys. n8n is not publicly exposed without access controls.

## AI
Local inference is the default zero-cost development path. External AI providers are optional adapters and require explicit credentials/configuration. Generated content is treated as untrusted input and validated before downstream use.
