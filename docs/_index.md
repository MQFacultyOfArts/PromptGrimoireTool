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

## architecture

- [[1] Learning Workspace — Level 1 Decomposition](architecture/dfd/1-level-1-decomposition.md)
- [[5] Annotate Texts — Level 2 Decomposition](architecture/dfd/5-annotate-texts.md)

## asyncpg

- [asyncpg usage - connections, queries, pools, type conversion](asyncpg/usage.md)

## browser

- [Complete API reference for CSS.highlights, Highlight class, ::highlight() pseudo-element, StaticRange](browser/css-custom-highlight-api.md)
- [Browser Selection API for text selection and annotation](browser/selection-api.md)

## browserstack

- [BrowserStack integration patterns for Python pytest and Playwright suites, Automate REST APIs, Local Testing, and MCP workflows](browserstack/python-integration-and-apis.md)

## claude-code

- [How to create and configure Claude Code skills (markdown files that teach Claude specialized knowledge)](claude-code/skills.md)

## dead-ends

- [Dead End: Client-Side Char Span Synchronisation](dead-ends/2026-02-10-charspan-sync.md)
- [Dead End: \annot with \par inside longtable + luatexja](dead-ends/2026-03-15-annot-par-in-longtable.md)

## design-notes

- [Design Notes: Bottom-Anchored Tag Bar](design-notes/bottom-tag-bar.md)

## guides

- [PromptGrimoire Guides](guides/index.md)

## investigations

- [Causal Analysis: Connection Pool Shrinkage Under CancelledError (#403)](investigations/2026-03-21-pool-shrinkage-403.md)

## lark

- [Using Lark as a standalone lexer (tokenizer only, no parsing)](lark/lexer-usage.md)

## lualatex

- [LuaLaTeX package for underlines, strikethrough, and highlighting](lualatex/lua-ul-reference.md)
- [LaTeX package for multi-file projects with standalone compilation](lualatex/subfiles-reference.md)
- [Why LaTeX export tests use AST parsing instead of string matching](lualatex/test-ast-validation.md)

## milkdown

- [Crepe high-level editor API — constructor, features, featureConfigs, getMarkdown, setReadonly, events](milkdown/crepe-api.md)
- [Editor actions — replaceAll, insert, getMarkdown, callCommand, direct ProseMirror access](milkdown/editor-actions.md)

## nicegui

- [Quasar color theming with ui.colors(), custom colors for branding](nicegui/colors.md)
- [ui.run() parameters, environment variables, native mode configuration](nicegui/configuration.md)
- [Server hosting, Docker, HTTPS/SSL, reverse proxy (nginx, traefik)](nicegui/deployment.md)
- [Event handler types and GenericEventArguments for ui.on() handlers](nicegui/events.md)
- [NiceGUI 3.x client lifecycle events - on_connect, on_disconnect, on_delete, reconnect_timeout](nicegui/lifecycle.md)
- [NiceGUI Multi-Client UI Synchronization](nicegui/multi-client-sync.md)
- [NiceGUI WebSocket, reactivity, multi-client handling, JS integration](nicegui/realtime.md)
- [NiceGUI styling with CSS, Tailwind, Quasar props, and static files](nicegui/styling.md)
- [NiceGUI E2E Testing with Playwright](nicegui/testing.md)
- [NiceGUI UI patterns - timer, refreshable, pages, events, storage, styling](nicegui/ui-patterns.md)
- [ui.table (Quasar QTable) — columns, rows, pagination, selection, slots, cell templates](nicegui/ui-table.md)
- [NiceGUI User fixture for fast headless page testing without a browser](nicegui/user-fixture-testing.md)

## openpyxl

- [Read-only mode for memory-efficient XLSX parsing, load_workbook API, iter_rows usage](openpyxl/read-only-mode.md)

## openrouter

- [Programmatic API key provisioning with per-key budgets, expiry, and lifecycle management](openrouter/key-management-api.md)
- [List available models with pricing, capabilities, context length, and supported parameters](openrouter/models-api.md)
- [Using pydantic-ai with OpenRouter via OpenAI-compatible interface](openrouter/pydantic-ai-integration.md)

## operation-solano-dawn

- [Operation Solano Dawn Planning](operation-solano-dawn/README.md)
- [Operation Solano Dawn Brainstorming Notes](operation-solano-dawn/brainstorming-notes.md)
- [Operation Solano Dawn - Wargame Simulation Platform - Product Requirements Document](operation-solano-dawn/client-prd.md)
- [Operation Solano Dawn: Final Epic and Seam Issues](operation-solano-dawn/final-epic-and-seams.md)
- [Operation Solano Dawn Internal Design Draft](operation-solano-dawn/internal-design-draft.md)
- [Operation Solano Dawn Internal Spec Outline](operation-solano-dawn/internal-spec-outline.md)

## pandoc

- [Lua filter API for AST manipulation during conversion](pandoc/lua-filters.md)
- [Template syntax for standalone document generation](pandoc/templates.md)

## playwright

- [Browser class API for multi-context testing](playwright/browser-api.md)
- [Playwright Python E2E testing with pytest](playwright/e2e-testing.md)

## postmortems

- [Root Cause: luaotfload harf-plug crash on server (color emoji PNG cache)](postmortems/2026-03-15-harf-emoji-cwd-crash.md)
- [Post-Mortem: 2026-03-15 Production OOM Outage](postmortems/2026-03-15-production-oom.md)
- [Afternoon Incident Analysis: 2026-03-16 14:50–17:20 AEDT](postmortems/2026-03-16-afternoon-analysis.md)
- [Post-Mortem: 2026-03-16 Service Degradation and Data Loss During Live Class](postmortems/2026-03-16-gateway-failures-data-loss.md)
- [Incident Response Commands: 2026-03-16](postmortems/2026-03-16-incident-response.md)
- [Investigation: 2026-03-16 Gateway Failures](postmortems/2026-03-16-investigation.md)
- [New Errors Observed 2026-03-16 ~15:00 AEDT](postmortems/2026-03-16-new-errors.md)
- [Proposed Incident Analysis Tools](postmortems/2026-03-16-proposed-analysis-tools.md)
- [Investigation: Firefox E2E CI Failures](postmortems/2026-03-18-firefox-e2e-failures.md)
- [Investigation: #377 Page Load Latency](postmortems/2026-03-18-page-load-latency-377.md)
- [Causal Analysis: NiceGUI Slot Deletion Race (#369)](postmortems/2026-03-20-slot-deletion-investigation-369.md)
- [Post-Mortem: 2026-03-21 PDF Export Failure + Journal PII Leak](postmortems/2026-03-21-export-failure-pii-leak.md)
- [Investigation: #377 Workspace Performance — Large Document Baseline](postmortems/2026-03-22-workspace-performance-377.md)
- [WIP Handoff: #377 Workspace Performance — Epoch Analysis](postmortems/2026-03-24-377-wip-handoff.md)
- [Clobber Scan Prompt — for Codex/Gemini](postmortems/2026-03-24-clobber-scan-prompt.md)
- [Incident: PgBouncer Double-Pooling SIGABRT and LaTeX Export Failures](postmortems/2026-03-25-pgbouncer-crash-and-export-failures.md)
- [PromptGrimoire Incident Analysis Playbook](postmortems/incident-analysis-playbook.md)

## prds

- [Case Brief Tool - Product Requirements Document](prds/2026-01-19-case-brief-tool-prd.md)
- [Translation Annotation & Iteration Tool - Product Requirements Document](prds/2026-01-28-translation-annotation-tool-prd.md)
- [Ancient History AI Annotation Tool - Product Requirements Document](prds/2026-01-30-ancient-history-annotation-tool-prd.md)
- [LLM Playground Design](prds/2026-02-10-llm-playground.md)
- [Operation Solano Dawn - Wargame Simulation Platform - Product Requirements Document](prds/2026-03-04-operation-solano-dawn-wargame-prd.md)

## pycrdt

- [Complete API reference for pycrdt CRDT library - Text, Doc, StickyIndex, sync functions](pycrdt/api-reference.md)
- [Awareness API for ephemeral presence state (cursors, selections, disconnect cleanup)](pycrdt/awareness.md)
- [pycrdt Integration with NiceGUI](pycrdt/nicegui-integration.md)
- [pycrdt usage guide - CRDT data types, sync, transactions, observers](pycrdt/usage.md)
- [pycrdt WebSocket sync patterns for real-time collaboration](pycrdt/websocket-sync.md)

## ruff

- [Pre-commit integration guide for Ruff linter and formatter](ruff/pre-commit.md)

## sqlmodel

- [SQLModel - Pydantic + SQLAlchemy ORM for Python](sqlmodel/overview.md)

## stytch

- [aiohttp session lifecycle in the Stytch Python SDK — lazy creation, external session injection, GC-based cleanup](stytch/async-session-management.md)
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
- [Human Test Plan: Empty-Tag Annotation UX (#210)](test-plans/2026-03-01-empty-tag-ux-210.md)
- [Wargame Turn Cycle Engine — Human Test Plan](test-plans/2026-03-10-turn-cycle-296.md)

---

## Project Documents

- [Testing Guidelines](testing.md)
- [Architecture](ARCHITECTURE.md)
- [Dependency Rationale](dependency-rationale.md)
