# CMe Development

## Local setup

1. Clone cvsz/cme.
2. Copy .env.example to an ignored .env.
3. Use Python 3.12+ for the API.
4. Install API development dependencies:

   ```bash
   cd apps/api
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -e '.[dev]'
   pytest
   ruff check .
   ```

5. Run the API:

   ```bash
   uvicorn cme_api.main:app --reload
   ```

6. Run repository validation before opening a PR:

   ```bash
   make validate-template
   ```

## Quality expectations

Add tests with behavior changes, preserve tenant boundaries, keep secrets out of source, use Decimal/integer minor units for financial values, and do not weaken CI/security gates to make checks pass.

## Pull-request validation

Capture exact-head evidence for every applicable check. Repository administration state is verified with scripts/github_admin.py; documentation alone is not evidence.

## Documentation

Update architecture, migrations, security, deployment and rollback documentation when implementation changes their assumptions.
