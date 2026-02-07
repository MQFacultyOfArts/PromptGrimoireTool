# Cached Documentation Index

This directory contains cached documentation for project dependencies.
Documentation is automatically cached by the `cache-docs` skill when fetching
library references during development.

## pycrdt

- [Usage Guide](pycrdt/usage.md) - CRDT data types, sync, transactions, observers
- [WebSocket Sync](pycrdt/websocket-sync.md) - Real-time sync patterns for collaboration
- [API Reference](pycrdt/api-reference.md) - Complete API: Text, Doc, StickyIndex, sync functions
- [NiceGUI Integration](pycrdt/nicegui-integration.md) - *Project notes: Spike 1 learnings*

## nicegui

- [Real-Time & Reactivity](nicegui/realtime.md) - WebSocket, multi-client, JS integration
- [UI Patterns](nicegui/ui-patterns.md) - timer, refreshable, pages, events, storage, styling
- [Styling & Static Files](nicegui/styling.md) - CSS, Tailwind, Quasar, ui.add_css(), static files
- [Color Theming](nicegui/colors.md) - ui.colors(), custom colors for branding, Quasar color system
- [Events](nicegui/events.md) - GenericEventArguments, event handler types
- [Elements & Text](nicegui/elements-text.md) - ui.element, ui.html, ui.label, ui.markdown
- [E2E Testing](nicegui/testing.md) - *Project notes: Playwright testing with NiceGUI*
- [Multi-Client Sync](nicegui/multi-client-sync.md) - *Project notes: Broadcasting updates*

## stytch

### B2B Overview

- [B2B Basics](stytch/b2b-basics.md) - Organizations, Members, settings, core flows, features
- [B2B Overview](stytch/b2b-overview.md) - Organizations, Members, Sessions, auth methods
- [B2B Python Quickstart](stytch/b2b-quickstart.md) - Client setup, discovery flow, sessions

### Magic Links (B2B)

- [Login/Signup](stytch/b2b-magic-links.md) - Organization-scoped magic link emails
- [Authenticate](stytch/b2b-authenticate.md) - Token authentication, session creation
- [Invite](stytch/b2b-invite.md) - Invite new Members with roles

### SSO

- [SSO Overview](stytch/sso-overview.md) - SAML/OIDC setup, external connections
- [OIDC Connections](stytch/sso-oidc.md) - OpenID Connect IdP integration
- [SAML Connections](stytch/sso-saml.md) - SAML IdP integration, AAF setup

### RBAC & Testing

- [RBAC Guide](stytch/rbac-guide.md) - Roles, permissions, default resources
- [Testing Guide](stytch/testing.md) - E2E testing, sandbox values

### Reference (B2C)

- [Python SDK](stytch/python-sdk.md) - Magic links, sessions, async support
- [RBAC](stytch/rbac.md) - Resources, roles, permissions (B2B only)
- [Magic Link Flow](stytch/magic-link-flow.md) - Complete auth flow with NiceGUI integration
- [Passkeys](stytch/passkeys.md) - WebAuthn registration and authentication

## aaf

- [OIDC Integration](aaf/oidc-integration.md) - Endpoints, scopes, claims, registration process
- [Rapid IdP](aaf/rapid-idp.md) - SAML identity provider for Australian research/education

## sqlmodel

- [Overview](sqlmodel/overview.md) - Pydantic + SQLAlchemy ORM, PostgreSQL

## asyncpg

- [Usage Guide](asyncpg/usage.md) - Async PostgreSQL driver, connection pools, SQLAlchemy integration

## alembic

- [SQLModel Setup](alembic/sqlmodel-setup.md) - Database migrations with async PostgreSQL

## playwright

- [E2E Testing](playwright/e2e-testing.md) - pytest-playwright, locators, assertions, multi-user testing
- [Browser API](playwright/browser-api.md) - Browser class, multi-context testing, new_context()

## browser

- [Selection API](browser/selection-api.md) - Text selection for annotations, NiceGUI integration

## claude-code

- [Skills](claude-code/skills.md) - How to create and configure Claude Code skills

## pandoc

- [Lua Filters](pandoc/lua-filters.md) - AST manipulation, Table/Cell/Div elements, custom LaTeX output
- [Templates](pandoc/templates.md) - Template syntax, LaTeX variables, PDF generation

## ruff

- [Pre-commit Integration](ruff/pre-commit.md) - Pre-commit integration guide for Ruff linter and formatter

## lark

- [Lexer Usage](lark/lexer-usage.md) - Standalone lexer mode, Token attributes, grammar syntax, catch-all terminals
- [Lua-UL Reference](lark/lua-ul-reference.md) - LuaLaTeX underline/highlight package syntax and nesting

---

## Design Plans

- [Nested Highlight Marker Parser](design-plans/2026-01-28-nested-highlight-marker-parser.md) - Lark-based lexer for interleaved highlight markers
- [CSS Fidelity PDF Export](design-plans/2026-01-29-css-fidelity-pdf-export.md) - Tiered CSS handling for HTML-to-PDF pipeline
- [Unicode Robustness](design-plans/2026-01-29-unicode-robustness.md) - Unicode handling in marker tokenization

## Project Documents

- [Case Brief Tool PRD](design-plans/2026-01-19-case-brief-tool-prd.md) - Product requirements for legal education case briefing tool
- [Testing Guidelines](testing.md) - TDD workflow, E2E patterns, database test isolation
