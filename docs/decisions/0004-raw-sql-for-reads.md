# 0004 — Raw SQL is the convention for query-shaped reads

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** Brian Ballsun-Stanton

## Context

The ty 0.0.24 → 0.0.72 upgrade surfaced ~77 diagnostics across 45 functions
where SQLModel column expressions (`Model.field` in `.where()` / `.join()` /
`.order_by()` / `.in_()`) resolve to instance types under ty. The April 2026
design (`docs/design-plans/2026-04-23-ty-sa-typing-cleanup.md`, DR1) had
already chosen raw SQL over `sqlmodel.col()` wrapping for these sites, but was
never executed: none of its phases shipped, its `deadline_worker.py` prior-art
module has since been deleted, and its diagnostic estimate (~180) does not
match what is measurable today (~77).

A code survey (2026-08-17) established what the ORM layer actually carries
here: zero `relationship()` declarations across 19 tables, zero
`model_validate()` calls anywhere (the one untrusted-input path, character-card
upload, uses plain dataclasses), and 68/79/13 `session.add`/`get`/`delete`
sites that produce no ty diagnostics at all. The genuinely hard queries — the
navigator's four-way `UNION ALL` CTE and `acl.py::list_importable_workspaces`
— went raw years before any convention required it. The main cost identified:
multi-model hydration such as `resolve_annotation_context`'s five-object
outerjoin becomes hand-written row mapping.

ty will not fix the descriptor inference: the tracking issue (astral-sh/ty
#3421) has a maintainer statement that it will not be prioritised before ty's
stable release, for which no timeline exists.

## Decision

Raw SQL is the convention for query-shaped reads. SQLModel remains the owner
of schema definitions, Alembic autogeneration, and simple unit-of-work writes
(`session.add` / `session.get` / `session.delete` / attribute mutation).

The write idiom for migrated reads is `tstring(t"...")` (SQLAlchemy 2.1, PEP
750), adopted directly so no site is migrated twice — see ADR 0005 for the
dependency ruling. Fallback if 2.1 fails validation: `text("...")` with
`:name` binding on stable 2.0, with tstring as the named successor.

Migration scope now: the ty-flagged functions. Other ORM reads migrate as
they are touched; new reads are written raw. `sqlmodel.col()` remains
rejected (per DR1) except as an interim measure inside a function already
scheduled for migration.

Every migrated query keeps or gains integration-test coverage, because a
column rename in a SQL string fails at runtime, not at type-check — this is
the accepted price, inherited from DR1's own analysis.

## Consequences

- The 45 flagged functions across `db/`, `cli/export.py`, `cli_loadtest.py`
  and tests get migrated; ty passes without suppressions or wrappers.
- Multi-model hydration sites pay tens of lines of explicit row mapping
  (`NavigatorRow` pattern); this is visible, greppable boilerplate rather
  than descriptor magic, and is the deliberate trade.
- Identifier interpolation (table/column names from trusted catalog queries)
  cannot use bind parameters; the planned `text()`/tstring safety guard must
  permit that narrow case (`cli/_shared.py::TRUNCATE` is the existing
  example) while rejecting value interpolation.
- The unexecuted 2026-04-23 design plan is superseded in its mechanism
  (tstring, not text; no `EXPLAIN`-gated index phase bundled in) but
  confirmed in its direction. Its index-candidate enumeration remains a good
  follow-up and is not part of this decision.
