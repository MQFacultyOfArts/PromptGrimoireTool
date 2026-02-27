# Cached Documentation Index

This directory contains cached documentation for project dependencies.
Documentation is automatically cached by the `cache-docs` skill when fetching
library references during development.

**Auto-generated** by `scripts/generate_docs_index.py` — do not edit manually.

## aaf

- [AAF OIDC integration - endpoints, scopes, claims, registration, skipDS, and attribute-based authorisation](aaf/oidc-integration.md)
- [AAF Rapid IdP - SAML identity provider for Australian research/education](aaf/rapid-idp.md)
- [AAF test federation - free registration, test endpoints, VHO, Rapid IdP, development workflow](aaf/test-federation.md)

## alembic

- [Alembic migrations with SQLModel and async PostgreSQL](alembic/sqlmodel-setup.md)

## asyncpg

- [asyncpg usage - connections, queries, pools, type conversion](asyncpg/usage.md)

## browser

- [Complete API reference for CSS.highlights, Highlight class, ::highlight() pseudo-element, StaticRange](browser/css-custom-highlight-api.md)
- [Browser Selection API for text selection and annotation](browser/selection-api.md)

## claude-code

- [How to create and configure Claude Code skills (markdown files that teach Claude specialized knowledge)](claude-code/skills.md)

## dead-ends

- [Dead End: Client-Side Char Span Synchronisation](dead-ends/2026-02-10-charspan-sync.md)

## lark

- [Using Lark as a standalone lexer (tokenizer only, no parsing)](lark/lexer-usage.md)

## lualatex

- [LuaLaTeX package for underlines, strikethrough, and highlighting](lualatex/lua-ul-reference.md)
- [LaTeX package for multi-file projects with standalone compilation](lualatex/subfiles-reference.md)
- [Why LaTeX export tests use AST parsing instead of string matching](lualatex/test-ast-validation.md)

## nicegui

- [Quasar color theming with ui.colors(), custom colors for branding](nicegui/colors.md)
- [Event handler types and GenericEventArguments for ui.on() handlers](nicegui/events.md)
- [NiceGUI 3.x client lifecycle events - on_connect, on_disconnect, on_delete, reconnect_timeout](nicegui/lifecycle.md)
- [NiceGUI Multi-Client UI Synchronization](nicegui/multi-client-sync.md)
- [NiceGUI WebSocket, reactivity, multi-client handling, JS integration](nicegui/realtime.md)
- [NiceGUI styling with CSS, Tailwind, Quasar props, and static files](nicegui/styling.md)
- [NiceGUI E2E Testing with Playwright](nicegui/testing.md)
- [NiceGUI UI patterns - timer, refreshable, pages, events, storage, styling](nicegui/ui-patterns.md)
- [NiceGUI User fixture for fast headless page testing without a browser](nicegui/user-fixture-testing.md)

## openrouter

- [Programmatic API key provisioning with per-key budgets, expiry, and lifecycle management](openrouter/key-management-api.md)
- [List available models with pricing, capabilities, context length, and supported parameters](openrouter/models-api.md)
- [Using pydantic-ai with OpenRouter via OpenAI-compatible interface](openrouter/pydantic-ai-integration.md)

## pandoc

- [Lua filter API for AST manipulation during conversion](pandoc/lua-filters.md)
- [Template syntax for standalone document generation](pandoc/templates.md)

## playwright

- [Browser class API for multi-context testing](playwright/browser-api.md)
- [Playwright Python E2E testing with pytest](playwright/e2e-testing.md)

## prds

- [Case Brief Tool - Product Requirements Document](prds/2026-01-19-case-brief-tool-prd.md)
- [Translation Annotation & Iteration Tool - Product Requirements Document](prds/2026-01-28-translation-annotation-tool-prd.md)
- [Ancient History AI Annotation Tool - Product Requirements Document](prds/2026-01-30-ancient-history-annotation-tool-prd.md)
- [LLM Playground Design](prds/2026-02-10-llm-playground.md)

## pycrdt

- [Complete API reference for pycrdt CRDT library - Text, Doc, StickyIndex, sync functions](pycrdt/api-reference.md)
- [Awareness API for ephemeral presence state (cursors, selections, disconnect cleanup)](pycrdt/awareness.md)
- [pycrdt Integration with NiceGUI](pycrdt/nicegui-integration.md)
- [pycrdt usage guide - CRDT data types, sync, transactions, observers](pycrdt/usage.md)
- [pycrdt WebSocket sync patterns for real-time collaboration](pycrdt/websocket-sync.md)

## rodney

- [Rodney CLI Reference](rodney/cli-reference.md)

## ruff

- [Pre-commit integration guide for Ruff linter and formatter](ruff/pre-commit.md)

## sqlmodel

- [SQLModel - Pydantic + SQLAlchemy ORM for Python](sqlmodel/overview.md)

## stytch

- [B2B magic link token authentication - creates sessions with MFA support](stytch/b2b-authenticate.md)
- [B2B fundamentals - Organizations, Members, settings, core flows, features](stytch/b2b-basics.md)
- [B2B invitation emails - invite new Members to Organizations with roles](stytch/b2b-invite.md)
- [B2B magic link login/signup API - organization-scoped authentication](stytch/b2b-magic-links.md)
- [B2B auth overview - Organizations, Members, Sessions, auth methods](stytch/b2b-overview.md)
- [Python B2B quickstart - client setup, magic links, sessions](stytch/b2b-quickstart.md)
- [Stytch magic link complete flow - send, callback, authenticate](stytch/magic-link-flow.md)
- [Stytch Passkeys/WebAuthn registration and authentication](stytch/passkeys.md)
- [Stytch Python SDK - magic links, sessions, async support](stytch/python-sdk.md)
- [RBAC guide - roles, permissions, default resources, role assignment](stytch/rbac-guide.md)
- [Stytch RBAC model - resources, roles, permissions](stytch/rbac.md)
- [Stytch B2B SSO OIDC testing - sandbox setup, connection lifecycle, test IdP strategies, JIT provisioning](stytch/sso-oidc-testing.md)
- [OIDC SSO connections - integrate external identity providers via Stytch, including AAF OIDC](stytch/sso-oidc.md)
- [SSO overview - SAML/OIDC setup, external connections, IdP configuration](stytch/sso-overview.md)
- [SAML SSO connections - integrate SAML identity providers including AAF](stytch/sso-saml.md)
- [Testing guide - E2E testing, sandbox values, test credentials](stytch/testing.md)

## test-plans

- [Human Test Plan: 134-lua-highlight](test-plans/2026-02-09-lua-highlight-134.md)
- [Human Test Plan: CSS Custom Highlight API Migration](test-plans/2026-02-11-css-highlight-api.md)
- [Human Test Plan: Per-Activity Copy Protection (103-copy-protection)](test-plans/2026-02-13-copy-protection-103.md)
- [Test Plan: Annotation Module Split (#120)](test-plans/2026-02-14-annotation-split-120.md)
- [Human Test Plan: Auto-create Branch Databases (#165)](test-plans/2026-02-14-auto-create-branch-db-165.md)
- [Mega UAT: CSS Highlight API + Copy Protection + Pydantic-Settings](test-plans/2026-02-14-mega-uat.md)
- [Human Test Plan: Annotation Tags (Issue #95)](test-plans/2026-02-18-95-annotation-tags.md)

---

## Project Documents

- [Testing Guidelines](testing.md)
- [Architecture](ARCHITECTURE.md)
- [Dependency Rationale](dependency-rationale.md)
