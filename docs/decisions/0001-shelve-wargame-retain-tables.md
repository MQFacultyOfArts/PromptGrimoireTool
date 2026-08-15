# 0001 — Shelve the wargame feature, retain its tables

**Status:** Accepted
**Date:** 2026-08-06
**Deciders:** Brian Ballsun-Stanton

## Context

The wargame was built backend-first and never received a UI. A case-insensitive
sweep of `src/promptgrimoire/` found no wargame pages or routes, so no user could
reach it. Despite that, `deadline_worker` was started unconditionally at app
startup — not behind a feature flag — and had been polling in production for
months.

It carried roughly 2050 lines across `wargame/`, `db/wargames.py` and
`deadline_worker.py`, twelve test files, and the project's only dependency on
`pydantic-ai`. That dependency resolved as the batteries-included metapackage
with every provider extra, which is what dragged in `mcp` (a duplicate vulnerable
`starlette` and `python-multipart`), `xai-sdk` (a third `aiohttp`), plus
`fastmcp`, `cohere`, `groq`, `mistralai`, `google-genai`, `temporal` and
`logfire`.

The recorded justification for `pydantic-ai` — multi-provider abstraction for a
playground provider factory — was stale. `wargame/agents.py` named exactly one
model, `anthropic:claude-sonnet-4-6`, and the cited playground files were never
built. Roleplay never used it; it calls the `anthropic` SDK directly via
`llm/client.py`.

## Decision

Remove the wargame service layer, turn cycle engine, PydanticAI agents and
deadline worker from `main`, preserving them on the `shelf/wargame` branch.
Remove `pydantic-ai` from `pyproject.toml`.

**Retain** the three tables (`wargame_config`, `wargame_team`,
`wargame_message`), their SQLModel classes, the `Activity.type` discriminator,
`ACLEntry.team_id` and `DuplicateCodenameError`.

## Consequences

Retention is the load-bearing half. `ACLEntry` carries a `team_id` foreign key to
`wargame_team` and a `num_nonnulls(workspace_id, team_id) = 1` check constraint,
so dropping the tables means a migration altering `acl_entry` — the table that
gates every workspace permission in production. That is not a trade worth making
for a feature nobody can reach. `verify_schema()` only fails on *missing* tables
(`db/bootstrap.py:294`), never on extra ones, so the inert tables cost nothing at
startup.

Measured: resolved packages 267 → 178, known vulnerabilities 117 → 92, affected
packages 26 → 21. `authlib`, `gitpython`, `mcp`, `pydantic-ai` and
`pydantic-ai-slim` left the tree entirely. Production also stops running a
background poller that could never do anything.

Test suite went 4052 → 3952 passing with no new failures.
`docs/database.md` and `docs/migration-checklist.md` remain factually correct and
were annotated rather than edited.

To revive: restore `shelf/wargame`, and prefer `pydantic-ai-slim[anthropic]` over
the metapackage.
