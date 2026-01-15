# Cached Documentation Index

This directory contains cached documentation for project dependencies.
Documentation is automatically cached by the `cache-docs` skill when fetching
library references during development.

## pycrdt

- [Usage Guide](pycrdt/usage.md) - CRDT data types, sync, transactions, observers
- [WebSocket Sync](pycrdt/websocket-sync.md) - Real-time sync patterns for collaboration
- [API Reference](pycrdt/api-reference.md) - Complete API: Text, Doc, StickyIndex, sync functions

## nicegui

- [Real-Time & Reactivity](nicegui/realtime.md) - WebSocket, multi-client, JS integration
- [UI Patterns](nicegui/ui-patterns.md) - timer, refreshable, pages, events, storage, styling

## stytch

- [Python SDK](stytch/python-sdk.md) - Magic links, sessions, async support
- [RBAC](stytch/rbac.md) - Resources, roles, permissions (B2B only)
- [Magic Link Flow](stytch/magic-link-flow.md) - Complete auth flow with NiceGUI integration
- [Passkeys](stytch/passkeys.md) - WebAuthn registration and authentication

## sqlmodel

- [Overview](sqlmodel/overview.md) - Pydantic + SQLAlchemy ORM, PostgreSQL

## asyncpg

- [Usage Guide](asyncpg/usage.md) - Async PostgreSQL driver, connection pools, SQLAlchemy integration

## alembic

- [SQLModel Setup](alembic/sqlmodel-setup.md) - Database migrations with async PostgreSQL

## playwright

- [E2E Testing](playwright/e2e-testing.md) - pytest-playwright, locators, assertions, multi-user testing

## browser

- [Selection API](browser/selection-api.md) - Text selection for annotations, NiceGUI integration

## claude-code

- [Skills](claude-code/skills.md) - How to create and configure Claude Code skills

## ruff

- [Pre-commit Integration](ruff/pre-commit.md) - Pre-commit integration guide for Ruff linter and formatter
