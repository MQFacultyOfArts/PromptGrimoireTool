# Plan: Add Missing Dependencies and Fetch Documentation

## Goal
Complete the documentation foundation for all derisking spikes by adding missing dependencies and fetching comprehensive docs with example code.

## Dependencies to Add (one by one)

### 1. asyncpg
- **Why:** Required for async PostgreSQL with SQLModel (Spike 4)
- **Add to:** `pyproject.toml` dependencies
- **Docs to fetch:**
  - Basic usage and connection pooling
  - Integration with SQLAlchemy async engine

### 2. alembic
- **Why:** Database migrations (required per PRD)
- **Add to:** `pyproject.toml` dev dependencies
- **Docs to fetch:**
  - Setup with SQLModel
  - Migration workflow

## Documentation to Fetch (for existing deps)

### 3. Playwright E2E testing
- **Why:** Spike 5 (full integration test) needs E2E patterns
- **Docs to fetch:**
  - Python Playwright basics
  - Testing NiceGUI apps
  - Async test patterns with pytest

### 4. pycrdt + WebSocket integration example
- **Why:** Spike 1 needs concrete transport layer example
- **Docs to fetch:**
  - y-crdt/pycrdt sync protocol examples
  - WebSocket provider patterns

### 5. Text selection JavaScript
- **Why:** Spike 2 needs browser selection API code
- **Docs to fetch:**
  - Browser Selection API
  - Range/getSelection() patterns
  - Integration with Python callbacks

### 6. Stytch callback flow
- **Why:** Spike 3 needs complete magic link redirect handling
- **Docs to fetch:**
  - Magic link callback URL handling
  - Session management after auth
  - Passkey setup (mentioned in PRD)

## Workflow for Each Item

1. Add dependency to pyproject.toml (if applicable)
2. Run `uv sync` to install
3. Fetch official documentation using WebFetch
4. Save to `docs/<library>/` with appropriate filename
5. Update `docs/_index.md`

## Files to Modify

- [pyproject.toml](pyproject.toml) - add asyncpg, alembic
- [docs/_index.md](docs/_index.md) - update index with new docs
- New files in `docs/`:
  - `docs/asyncpg/usage.md`
  - `docs/alembic/sqlmodel-setup.md`
  - `docs/playwright/e2e-testing.md`
  - `docs/pycrdt/websocket-sync.md`
  - `docs/browser/selection-api.md`
  - `docs/stytch/magic-link-flow.md`
  - `docs/stytch/passkeys.md`

## Verification

After each doc fetch:
- Confirm file saved to docs/
- Confirm contains actionable example code
- Run `uv sync` after dependency additions to verify installation
