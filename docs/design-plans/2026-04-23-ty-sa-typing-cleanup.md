# ty SQLAlchemy Typing Cleanup Design

**GitHub Issue:** None

## Summary

The type checker `ty` is pinned at version 0.0.24 because upgrading to 0.0.25 or later surfaces 277 diagnostics. Those diagnostics are not false alarms — ty legitimately flags patterns that are hard to verify in the presence of SQLAlchemy's column descriptors. When code writes `Model.field == x` inside a `.where(...)` call, SQLAlchemy's runtime machinery produces a SQL expression, but `ty` 0.0.25+ correctly refuses to guess at the descriptor protocol without a stronger signal. The codebase had also accreted 115 `# type: ignore[<mypy-code>]` suppressions that `ty` silently ignores (it honours only `ty:<ty-rule>`-prefixed comments), so those sites were already quietly unguarded.

This design clears all 277 diagnostics by fixing underlying patterns rather than adding suppressions. The dominant fix (Category A, ~180 sites) migrates ORM-expression queries to raw SQL via `session.execute(text("..."), {params})` — a pattern already established in `db/tags.py`, `db/navigator.py`, and several workers, now extended systematically. The remaining diagnostics fall into three smaller categories: real bugs in scripts (Category B, ~15 sites), loosely-typed test helpers (Category C, ~50 sites), and two SQLModel metaclass accesses (Category D). Every fixed class gets an AST guard test in `tests/unit/` so the patterns cannot be re-introduced. As a free byproduct of enumerating every migrated `WHERE`/`JOIN`/`ORDER BY` column, the design runs an index audit gated by before/after `EXPLAIN (ANALYZE, BUFFERS)` evidence — only indices that the PostgreSQL planner demonstrably uses are added. The `ty` pin stays at 0.0.24 for pre-commit stability; 0.0.32 is verified clean but not adopted as the hook version until ty reaches a stable release cadence.

## Definition of Done

1. **`uvx ty@0.0.32 check` exits 0** with "All checks passed!" on `src/`, `scripts/`, and `tests/` (with `alembic/` remaining excluded per the existing `[tool.ty.src]` config).

2. **Five AST guard tests exist in `tests/unit/` and pass**, one per anti-pattern class:
   - Category A — `$MODEL.$FIELD.<in_|not_in|is_|is_not|like|desc|asc>(...)` at class-level, and `$MODEL.$FIELD == $X` / `!= $X` appearing inside `.where(...)` / `.join(...)` / `.order_by(...)` / `.group_by(...)` / `.having(...)` call arguments. Failure message directs migration to `session.execute(text(...), {...})` per `docs/architecture/raw-sql-convention.md`.
   - Category B — `__import__(...)` appearing inside a type annotation.
   - Category B — module-level `name = None` that shadows a top-level `import name` / `from X import name`.
   - Category D — attribute access `<SQLModelClass>.__table__` (prefer `__tablename__` or `.metadata.tables[...]`).
   - Safety — f-string / `%` / `+` concatenation appearing inside a `text(...)` argument. Only literal string, `tstring(t"...")` (once SA 2.1 lands), or a prepared-statement-shaped `text("... :name ...")` + separate params dict are permitted.

   Each guard is AST-walking (does not import project code), lives in the unit lane, and fails if its anti-pattern is reintroduced.

3. **Existing `ty@0.0.24` pre-commit hook stays green.** No regression from the fix pass; `uvx ty@0.0.24 check` continues to exit 0.

4. **`uv run grimoire test all` passes** with no net new failures attributable to this work. Baseline (failure/skip count from `main` at design-plan creation) is recorded in this document and compared post-implementation.

5. **Every column referenced by a migrated `WHERE` clause has a PostgreSQL index**, added via an Alembic migration (`CREATE INDEX CONCURRENTLY` to avoid production locks). The set is enumerated deterministically from the raw-SQL conversion pass — each migrated site contributes its `WHERE` / `JOIN ... ON` / `ORDER BY` columns to a checklist; the migration covers the union, minus already-indexed columns.

   **Effectiveness gate:** For each proposed new index, capture `EXPLAIN (ANALYZE, BUFFERS)` output for a representative query **before** and **after** creating the index.

   Plans are run against a **production clone** — a current `pg_restore` of grimoire.drbbs.org into the dev DB. This is required, not optional: before/after numbers are only comparable when the underlying data distribution is identical, and identical means prod data.

   **If no prod `pg_restore` is available when phase 6 begins, the phase PAUSES** until one is obtained. Do not proceed with a synthetic or fixture-only dev DB — the effectiveness gate's verdict would not reflect production planner behaviour.

   *Fallback only if prod access is genuinely unavailable (e.g. emergency / offline):* seed + rehydrate the scrubbed fixtures (`pabai_workspace_scrubbed.json`, `workspace_lawlis_v_r.json`, `workspace_cjk_yuki.json`, `workspace_dogs_breakfast_overflow.json`, `workspace_legal_will_57hl_scrubbed.json`) + `cli_loadtest` scale + `ANALYZE;`. Record "fallback used, no prod dump" in the plans files if this path is taken.

   The AFTER plan must show the new index being chosen by the planner (Index Scan / Bitmap Index Scan referencing the index name) AND a reduction in both total cost AND actual execution time. Indices that don't earn their place by this test are **not added**.

   Both BEFORE and AFTER `EXPLAIN (ANALYZE, BUFFERS)` plans are committed alongside the migration, with the `indices-checklist.md` recording concrete numeric measurements per index:

   | Column | Table | Rep. query | Before cost | Before time (ms) | After cost | After time (ms) | Verdict |
   |---|---|---|---|---|---|---|---|

   The migration lands only the indices with `Verdict = added`. Rejected candidates stay in the checklist with their numbers and a reason (e.g. "table too small: seqscan preferred even with index").

6. **Documentation updated** per `.ed3d/design-plan-guidance.md`:
   - `CLAUDE.md` § Conventions gains a rule establishing `session.execute(text(...), {params})` as the canonical column-predicate idiom when ORM syntax would require a `col()` wrapper, linking to this design.
   - `docs/database.md` gains a short section on the query-migration pattern and the indices added.
   - `docs/dependency-rationale.md` ty entry updated to note why the pin stays at 0.0.24 despite ty 0.0.32 reading clean after this work.

**Explicit exclusions:**
- Bumping the `ty` pin from 0.0.24 is out of scope.
- Changes to `alembic/` migrations prior to the index-addition phase are out of scope.
- Third-party site-packages / `.venv/` ty errors are out of scope.
- **t-string adoption via `sqlalchemy.tstring()` is deferred** — requires SA 2.1, currently beta-only (2.1.0b2). Captured as follow-up issue. Revisit when 2.1 GA ships.
- **N+1 / query-in-loop audit is deferred** — captured-as-we-go in a follow-up issue, but fixes ship in a separate PR (behaviour-changing, needs per-site test coverage).

## Acceptance Criteria

### ty-sa-typing-cleanup.AC1: Category A query migration
- **ty-sa-typing-cleanup.AC1.1 Success:** After phases 2+3, `uvx ty@0.0.32 check src/ scripts/ tests/` reports zero diagnostics of class `invalid-argument-type` / `unresolved-attribute` / `unknown-argument` / `no-matching-overload` matching the `Model.field` descriptor pattern.
- **ty-sa-typing-cleanup.AC1.2 Success:** Each migrated file's previously-passing unit tests continue to pass.
- **ty-sa-typing-cleanup.AC1.3 Success:** Migrated sites have adjacent dead `# type: ignore[<mypy-code>]` comments removed.
- **ty-sa-typing-cleanup.AC1.4 Failure:** Introducing `Model.field.in_(xs)` (or `.not_in`, `.is_`, `.is_not`, `.like`, `.desc`, `.asc`) at class level in `src/` or `scripts/` fails `test_orm_column_predicate_guard`.
- **ty-sa-typing-cleanup.AC1.5 Failure:** Introducing `Model.field == x` inside `.where(...)` / `.join(...)` / `.order_by(...)` / `.group_by(...)` / `.having(...)` in `src/` or `scripts/` fails the same guard.
- **ty-sa-typing-cleanup.AC1.6 Edge:** The same textual pattern appearing inside a comment or docstring does not trigger the guard (AST-level matching only).

### ty-sa-typing-cleanup.AC2: Category B real-bug fixes
- **ty-sa-typing-cleanup.AC2.1 Success:** `scripts/incident/ingest.py` has no `__import__(...)` in any annotation (parameter, return, or `AnnAssign`).
- **ty-sa-typing-cleanup.AC2.2 Success:** `_fetch_beszel` typed as `Callable[..., ...] | None` with call sites guarded before invocation.
- **ty-sa-typing-cleanup.AC2.3 Success:** `Result[Any].rowcount` sites typed correctly via `CursorResult` or explicit cast.
- **ty-sa-typing-cleanup.AC2.4 Success:** `scripts/smoke_turn_cycle.py`'s `summary_system_prompt: str | None → str` site types cleanly.
- **ty-sa-typing-cleanup.AC2.5 Success:** `docx` import resolves via stubs OR is explicitly excluded under `[tool.ty.src]`.
- **ty-sa-typing-cleanup.AC2.6 Failure:** Introducing `__import__(...)` inside any annotation in `src/` / `scripts/` / `tests/` fails `test_annotation_dynamic_import_guard`.
- **ty-sa-typing-cleanup.AC2.7 Failure:** Introducing module-level `name = None` that shadows a top-level import in `src/` / `scripts/` fails `test_module_level_callable_shadow_guard`.

### ty-sa-typing-cleanup.AC3: Category C test scaffolding
- **ty-sa-typing-cleanup.AC3.1 Success:** `tests/unit/test_settings.py` monkey-patch wrappers contain no `*args: object` / `**kwargs: object`; parameters explicitly typed.
- **ty-sa-typing-cleanup.AC3.2 Success:** `tests/unit/test_word_count_models.py` builders use explicit typed kw-only params, not `dict[str, object]` defaults.
- **ty-sa-typing-cleanup.AC3.3 Success:** Both files pass `uvx ty@0.0.32 check` with zero diagnostics.
- **ty-sa-typing-cleanup.AC3.4 Success:** Existing tests in both files continue to pass post-refactor.

### ty-sa-typing-cleanup.AC4: Category D metaclass
- **ty-sa-typing-cleanup.AC4.1 Success:** No `<SQLModelClass>.__table__` accesses remain in `src/` or `scripts/` — the two current sites use `__tablename__` or `.metadata.tables[...]`.
- **ty-sa-typing-cleanup.AC4.2 Failure:** Introducing a new `<SQLModelClass>.__table__` access in `src/` / `scripts/` / `tests/` fails `test_sqlmodel_table_dunder_guard`.

### ty-sa-typing-cleanup.AC5: Indices with effectiveness gate
- **ty-sa-typing-cleanup.AC5.1 Success:** `tools/ty-sa-cleanup/indices-checklist.md` is empty at end of phase 6 (every candidate either landed as an index or is documented with a rejection reason).
- **ty-sa-typing-cleanup.AC5.2 Success:** Alembic migration file exists with BEFORE and AFTER `EXPLAIN (ANALYZE, BUFFERS)` plan pairs for each landed index.
- **ty-sa-typing-cleanup.AC5.3 Success:** `alembic upgrade head` applies cleanly to a dev DB.
- **ty-sa-typing-cleanup.AC5.4 Success:** Integration test `test_ty_sa_indices_active` asserts each landed index appears in `pg_indexes` AND in its representative EXPLAIN plan.
- **ty-sa-typing-cleanup.AC5.5 Failure:** A proposed index whose AFTER plan doesn't reference it, or doesn't drop both cost AND actual time relative to BEFORE, is not present in the migration (checklist documents the drop reason).
- **ty-sa-typing-cleanup.AC5.6 Edge:** `test_ty_sa_indices_active` documents the minimum dev-DB shape (base fixtures + loadtest scale) and skips with an informative message when tables are too small for meaningful planning results.

### ty-sa-typing-cleanup.AC6: AST guards installed
- **ty-sa-typing-cleanup.AC6.1 Success:** Five guard files exist in `tests/unit/`: `test_orm_column_predicate_guard.py`, `test_annotation_dynamic_import_guard.py`, `test_module_level_callable_shadow_guard.py`, `test_sqlmodel_table_dunder_guard.py`, `test_text_sql_safety_guard.py`.
- **ty-sa-typing-cleanup.AC6.2 Success:** Each guard contains the standard trio (main scanner, allowlist-exact-set, synthetic-violation) — 15 tests across the 5 files.
- **ty-sa-typing-cleanup.AC6.3 Success:** All 15 tests pass under `pytest tests/unit/ -k "guard"`.
- **ty-sa-typing-cleanup.AC6.4 Success:** Each scanner is pure AST (no project-code imports in any guard test).
- **ty-sa-typing-cleanup.AC6.5 Failure:** Removing a scanner's detection logic causes its synthetic-violation test to fail (scanner actually catches the anti-pattern).
- **ty-sa-typing-cleanup.AC6.6 Failure:** Modifying `_ALLOWLIST` without updating the paired exact-set test causes the allowlist-exact-set test to fail.
- **ty-sa-typing-cleanup.AC6.7 Failure:** Writing `text(f"SELECT ... {x}")` in `src/` / `scripts/` / `tests/` fails `test_text_sql_safety_guard`.
- **ty-sa-typing-cleanup.AC6.8 Success:** `text("SELECT ... :x ...", {"x": ...})` (prepared-statement form) and `tstring(t"SELECT ... {x}")` (PEP 750 form) both pass the safety guard.

### ty-sa-typing-cleanup.AC7: Documentation
- **ty-sa-typing-cleanup.AC7.1 Success:** `CLAUDE.md` § Conventions has the raw-SQL rule linking to `docs/architecture/raw-sql-convention.md`.
- **ty-sa-typing-cleanup.AC7.2 Success:** `docs/architecture/raw-sql-convention.md` exists covering parameter binding, result-shape choice, boundary casting.
- **ty-sa-typing-cleanup.AC7.3 Success:** `docs/database.md` has a new section describing the migration pattern and the indices added.
- **ty-sa-typing-cleanup.AC7.4 Success:** `docs/dependency-rationale.md`'s `ty` entry explains the 0.0.24-pin rationale.
- **ty-sa-typing-cleanup.AC7.5 Success:** `uv run grimoire docs build` succeeds.
- **ty-sa-typing-cleanup.AC7.6 Success:** Two follow-up GitHub issues exist (`ty-sa-tstring-adoption`, `ty-sa-n-plus-one-audit`) with `phase:post-mvp` label and findings collected from phases 2–3.

## Glossary

- **ty**: Astral's Python type checker (distinct from mypy and pyright). Pre-1.0, with a history of diagnostic-set changes between minor releases. The project pins `ty@0.0.24` as a pre-commit hook. This design validates the codebase against `ty@0.0.32` and leaves open a follow-up to bump the pin when ty reaches stability.
- **SQLModel**: Python library that combines SQLAlchemy (ORM/schema) with Pydantic (validation). Model classes are used both as database table definitions and as validated data containers.
- **SQLAlchemy**: The ORM and SQL toolkit SQLModel builds on. Provides `select()`, `text()`, `col()`, session management, and the descriptor protocol that makes `Model.field == x` work at runtime.
- **ORM**: Object-Relational Mapper. The SQLAlchemy layer that lets Python code write `session.exec(select(Model).where(Model.field == x))` instead of raw SQL. This migration moves ty-flagged column-predicate sites away from ORM expression syntax and onto `text()`.
- **`col()`**: `sqlmodel.col()` — a thin runtime no-op that wraps a column descriptor so type checkers recognise it as a column expression. The design explicitly rejects this approach as a cosmetic fix.
- **`text()`**: `sqlalchemy.text()` — wraps a raw SQL string so SQLAlchemy can execute it with named-placeholder binding (`":name"` style). The canonical query idiom after migration: `session.execute(text("SELECT ... WHERE col = :val"), {"val": x})`.
- **`InstrumentedAttribute`**: The SQLAlchemy descriptor type that `Model.field` resolves to at class access time. `ty` 0.0.25+ does not type-narrow comparisons on `InstrumentedAttribute`, which is the root cause of the Category A diagnostics.
- **`Mapped[T]`**: SQLAlchemy 2.0+ annotation for typed column declarations (e.g., `field: Mapped[str]`). The presence of `Mapped` annotations is what signals to `ty` that a class is a mapped ORM model.
- **AST guard**: A pytest test that walks Python source files using `ast.parse` / `ast.walk` (without importing the project code) and fails if a banned pattern is found. The project already has 11 such guards; this design adds 4 more.
- **Alembic**: The database migration tool for SQLAlchemy-based projects. All schema changes (including new indices) must go through Alembic revision files rather than being applied directly.
- **`EXPLAIN (ANALYZE, BUFFERS)`**: PostgreSQL command that executes a query and returns the planner's execution plan annotated with actual timing, row counts, and buffer usage. Used here as the effectiveness gate: a proposed index is only added if the AFTER plan shows the planner chose the index and cost/time dropped.
- **`CREATE INDEX CONCURRENTLY`**: PostgreSQL syntax for building an index without holding a write lock on the table. Required for production safety when adding indices to live tables. In SQLAlchemy/Alembic: `postgresql_concurrently=True`.
- **CRDT**: Conflict-free Replicated Data Type. The project uses `pycrdt` for real-time collaborative annotation state. Appears in this document only as context for why the scrubbed workspace fixtures are non-trivial in shape.
- **pabai fixture**: `tests/fixtures/pabai_workspace_scrubbed.json` — a scrubbed production workspace with 190 highlights, used to give the dev database realistic content shape for EXPLAIN measurements. "Pabai" is a workspace name from production data.
- **`cli_loadtest`**: The project's load-test CLI (`uv run grimoire cli_loadtest`) that populates the dev database at realistic scale — 30 units × 1100/80/15 student tiers with activities, enrolments, and ACLs. Required before running EXPLAIN ANALYZE so table statistics reflect production volumes.
- **xdist**: `pytest-xdist` — runs pytest tests in parallel across multiple worker processes. The AST guards are pure file-walk tests, safe under xdist in the unit lane.
- **PEP 750 / t-strings**: A Python 3.14 language feature for template literals that carry interpolation metadata. SQLAlchemy 2.1 adds `sqlalchemy.tstring()` to consume t-strings as safe parameterised SQL. Deferred in this design because SQLAlchemy 2.1 is beta-only at plan time.
- **`dataclass_transform` / PEP 681**: A typing mechanism that allows type checkers to understand libraries like SQLModel that use metaclass magic to behave like dataclasses. Incomplete `dataclass_transform` support in `ty` 0.0.24–0.0.32 is a contributing cause of the Category A diagnostic volume.
- **`CursorResult`**: SQLAlchemy's typed return for `session.execute()`, a subclass of the more generic `Result[Any]`. Accessing `.rowcount` on the base `Result[Any]` is a Category B bug site because `ty` cannot verify `rowcount` is present on the generic type.

## Architecture

**Problem.** `ty@0.0.24` passes clean on the current codebase, but `ty@0.0.25+` reports 277 diagnostics on the same source. Upgrading `ty` is blocked because the codebase has accreted typing patterns that ty 0.0.25+ legitimately flags. Four classes of issue (A–D) account for every diagnostic. Suppression is already attempted at 115 sites via `# type: ignore[<mypy-rule>]`; ty honours ignore comments only when prefixed with `ty:<ty-rule>`, so every existing suppression is invisible to it.

**Approach.** Fix underlying patterns rather than suppress. For the dominant class (Category A, ~180 sites), migrate from ORM-expression queries (`session.exec(select(Model).where(Model.field == x))`) to raw SQL via `session.execute(text("..."), {...})`. This eliminates the entire class of ty errors structurally, with no runtime wrapper. The pattern is already used in `db/tags.py`, `db/navigator.py`, `db/courses.py`, `search_worker.py`, `deadline_worker.py`, `cli/_shared.py` — the design extends the established idiom to new sites.

**Opportunity.** Enumerating every `.where(...)` / `.join(...)` / `.order_by(...)` column for the migration yields a deterministic list of index candidates. Currently only 4 columns across 19 SQLModel tables carry `index=True`. Phase 6 adds indices for the enumerated set, gated by a before/after `EXPLAIN (ANALYZE, BUFFERS)` effectiveness test — indices that don't demonstrably change the planner's choice aren't added.

**Non-migrated work.** Categories B (15 real bugs), C (~50 test-scaffolding sites), D (2 metaclass accesses) are fixed case-by-case with per-site logic. Each has a distinct root cause and none belong in a mechanical sweep.

**Regression prevention.** Five AST guards in `tests/unit/` — one per anti-pattern class (A, B-import, B-shadow, D) plus a safety guard rejecting f-string / `+` / `%` interpolation inside `text(...)` calls. Each walks source via `ast.parse`/`ast.walk`, modelled on `test_run_javascript_guard.py` and the other 10 existing guards. The text-safety guard permits both prepared-statement (`text("... :name ...")` + params dict) and PEP 750 t-string (`tstring(t"...")`, once adopted) forms.

**What stays.** SQLModel continues as ORM for schema, Alembic autogeneration, Pydantic validation, and simple CRUD (`session.add`, `session.get(Model, id)`, `session.delete(obj)`). The migration is targeted at ty-flagged sites only, not a wholesale ORM rip-out.

**Out-of-scope, captured.** SQLAlchemy 2.1 `tstring()` adoption and systematic N+1 auditing are deferred to follow-up issues. Findings accumulate naturally during phases 2–3 and seed those issues.

## Decision Record

### DR1: Raw SQL via `text()` + params over `col()` wrapping
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If SQLAlchemy 2.1's `tstring()` goes GA and the codebase adopts it; if the `text()`+params pattern causes measurable regressions from SQL typos not caught at authoring time.

**Decision:** We chose to migrate ORM-expression query sites (`Model.field == x` in `.where()`, `.in_()`, etc.) to raw SQL via `session.execute(text("..."), {...})` rather than wrap every site in `sqlmodel.col()`.

**Consequences:**
- **Enables:** Native ty-clean code without a cosmetic type-level wrapper. Queries legible as SQL, directly amenable to `EXPLAIN ANALYZE`. Aligns with the established raw-SQL idiom already present in `db/tags.py`, `db/navigator.py`, etc. Produces the exact list of indexed-column candidates as a free byproduct.
- **Prevents:** ~180 `col()` call sites whose only role is to placate the type checker. Keeps the codebase from "fighting the tool" at every column-access point.
- **Prevents (trade-off):** Compile-time column-rename detection that ORM attribute access gave us. With `Model.field` a rename at the model propagates to every call site as a type error; with `text("... WHERE field = :x")` the column name is a string literal and a schema rename fails at runtime with `column "field" does not exist`, not at type-check time. **Mitigation:** every migrated query requires integration-test coverage so a rename breaks CI rather than production. Tracked per call site during phases 2–3.

**Alternatives considered:**
- **`col()` wrapping (initial proposal):** Rejected because `col()` is a runtime no-op whose sole purpose is type narrowing. Every reader must learn "this is here for ty, not for behaviour."
- **Full move to raw SQL (all query sites, not just flagged):** Rejected for this design — blast radius is weeks and would erase the ORM's legitimate value for simple CRUD. Captured as a possible future design.

### DR2: AST guards, one per anti-pattern class
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If ty gains a mode that reliably honours mypy-style `# type: ignore` across minor versions; if ty 1.0 ships with a stability guarantee that makes it safe to rely on as the sole guard.

**Decision:** We chose four AST-walking pytest guards (one per anti-pattern class A, B-import, B-shadow, D) over bumping the ty pin and relying on ty itself as the regression guard.

**Consequences:**
- **Enables:** Fast unit-lane feedback with specific failure messages (e.g., "Migrate to session.execute(text(...))"). Independent of ty's diagnostic churn across minor releases. Inspectable and allowlisted as needed.
- **Prevents:** Coupling our CI to ty's internal inference decisions. Avoids the risk that ty 0.0.33+ introduces a new false-positive class that would break otherwise-valid code.

**Alternatives considered:**
- **Bump ty pin + gate CI on `ty check`:** Rejected — each minor ty release has reshuffled its diagnostic set so far; upgrading couples the project to an immature tool's release cadence.
- **Combined ty check + AST guards:** Rejected — redundancy without value; pick one regression-prevention mechanism and own it.

### DR3: Stay on `ty@0.0.24` pin
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** When ty 1.0 ships with documented stability; or when a newer ty version backfills a feature we want that 0.0.24 lacks.

**Decision:** We chose to keep `ty@0.0.24` as the pinned pre-commit check, despite this work making `ty@0.0.32` read clean.

**Consequences:**
- **Enables:** Stable pre-commit experience. No churn from ty's frequent minor releases introducing new diagnostic classes in unrelated PRs.
- **Prevents:** Surprise diagnostic regressions from upstream ty changes.

**Alternatives considered:**
- **Bump to ty@0.0.32:** Rejected — 0.0.32 is current latest but history shows each minor bump introduces new classes. Stability preferred at the pre-commit layer.
- **Ty latest in CI, 0.0.24 locally:** Rejected — creates two-tier type checking where CI disagrees with local workflows.

### DR4: Bundle index audit in scope; defer t-strings and N+1
**Status:** Accepted
**Confidence:** Medium
**Reevaluation triggers:** If phase 6's EXPLAIN cycle blows past a week; if the effectiveness gate drops so many candidates that the phase produces negligible value.

**Decision:** We chose to include index auditing (bounded by the effectiveness gate) in this design and defer t-string adoption and systematic N+1 auditing to separate follow-up issues.

**Consequences:**
- **Enables:** The SQL migration produces the exact checklist needed for indexing as a free byproduct; bundling avoids repeating that work in a follow-up.
- **Prevents:** Scope creep into a multi-week refactor. Avoids committing to SA 2.1 beta in a production codebase. Avoids bundling behaviour-changing N+1 fixes with typing cleanup.

**Alternatives considered:**
- **Only typing + guards; defer everything else:** Rejected — the indices checklist is free at migration time and costly to reconstruct later.
- **Bundle everything into one mega-PR:** Rejected — review burden, risk concentration, behaviour changes mixed with typing changes.

### DR5: Effectiveness gate on every proposed index
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If maintaining before/after plan files becomes a chore that drives skipping the gate; if we find we're dropping so few indices that the gate isn't earning its cost.

**Decision:** We chose to gate every proposed index on a before/after `EXPLAIN (ANALYZE, BUFFERS)` comparison. An index is added only if the AFTER plan shows the planner chose it AND total cost + execution time both drop.

**Consequences:**
- **Enables:** Only effective indices land. Each new index is provably pulling its weight. Plans committed as audit trail.
- **Prevents:** Index bloat — the write-cost, storage, and vacuum-cost penalty of indices that the planner never picks because the table is small or the predicate isn't selective.

**Alternatives considered:**
- **Add indices by rule (every WHERE column gets one):** Rejected — indices aren't free; the gate catches the ones that wouldn't help.
- **Add indices only when production profiling shows slow queries:** Rejected for this design — the checklist is available now; waiting loses the cheap opportunity.

### DR6: Production-shaped dev DB for EXPLAIN, not synthetic-scale alone
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If the scrubbed fixture set becomes stale relative to production data shape; if regular access to a current prod `pg_dump` becomes available.

**Decision:** We chose to use a production-shaped dev DB (scrubbed prod workspace fixtures + `cli_loadtest` scale + `ANALYZE`) for EXPLAIN measurement, with a current prod `pg_restore` as an acceptable alternative.

**Consequences:**
- **Enables:** Planner decisions reflect production realities. Effectiveness gate is meaningful.
- **Prevents:** False positives from measuring on an empty or synthetic DB where seqscan always wins.

**Alternatives considered:**
- **Measure on default dev DB only:** Rejected — tables are too small; seqscan wins regardless of indices.
- **Measure on production directly:** Rejected — production safety; dev DB is the right surface for EXPLAIN ANALYZE on mutating queries.

## Existing Patterns

**Raw SQL via `text()`.** Established in `db/tags.py`, `db/navigator.py`, `db/courses.py`, `db/engine.py`, `db/workspaces.py`, `search_worker.py`, `deadline_worker.py`, `cli/_shared.py`. Convention: `:name` placeholders + dict, UUIDs str-cast at the binding boundary, projected result shapes as `NamedTuple` (e.g. `NavigatorRow`, `SearchHit` in `db/navigator.py`). This design extends the pattern to ~180 new sites.

**AST guard tests.** 11 existing guards in `tests/unit/` share a consistent shape: `_SRC_DIR = Path(__file__).parents[2] / "src" / "promptgrimoire"`, `rglob("*.py")`, `ast.parse` + `ast.walk`, accumulated violations list, single `assert not violations` with bulk message, `_ALLOWLIST: set[str]` for exemptions, synthetic-violation test + allowlist-exact-set test. `test_run_javascript_guard.py` (127 LOC) is the canonical template; `test_async_fixture_safety.py`, `test_setlevel_guard.py`, `test_print_usage_guard.py`, `test_exception_logging_guard.py`, `test_psycopg_guard.py` follow the same pattern. The four new guards in this design match it exactly.

**`sqlmodel.col()` partial adoption.** Already present in `db/export_jobs.py` and `db/users.py`, 12 call sites total. Those uses stay — they're ty-clean; this design does not force re-migration of already-typed sites.

**Alembic concurrent indices.** Infrastructure ready via SQLAlchemy's standard `postgresql_concurrently=True`. No existing migration uses it yet; this design's phase 6 is the first.

**Fixture rehydration.** `scripts/rehydrate_workspace.py` + `tests/fixtures/workspace_*.json` is the established path for loading scrubbed prod workspaces into a dev DB. Phase 6's dev-DB preparation uses this path.

**Pre-commit hook pipeline.** Ruff + `ty@0.0.24` + shellcheck + BATS run on every commit. The new AST guards run in the unit test lane via pytest; they do not add to the pre-commit path.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Raw-SQL Conventions + Exemplar Migration
**Goal:** Establish the raw-SQL pattern for the rest of the project by migrating one small, self-contained module end-to-end and publishing a short conventions document.

**Components:**
- `docs/architecture/raw-sql-convention.md` — new short doc covering parameter binding (`:name` placeholders + dict), result-shape choice matrix (ORM hydrate via `session.execute(stmt).scalars()` vs `NamedTuple`/TypedDict for projected shapes), UUID/datetime boundary-casting rules, file-level import discipline. Linked from `CLAUDE.md`.
- One smallest Category A module converted end-to-end as the canonical example (candidate: `src/promptgrimoire/db/roles.py` or `db/enrolment.py`, whichever has the fewest ty diagnostics at plan start).
- `tools/ty-sa-cleanup/indices-checklist.md` — new running checklist file, seeded with columns touched during the exemplar migration.

**Dependencies:** None (first phase).

**Done when:** Exemplar module's `ty@0.0.32` diagnostic count is 0. Adjacent mypy-style `# type: ignore[<mypy-code>]` comments removed where they become dead. Conventions doc committed. Indices checklist has initial entries from the exemplar.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Category A Migration in `src/promptgrimoire/db/`
**Goal:** Migrate the bulk of Category A sites — approximately 70 diagnostics across `db/acl.py` (18), `db/tags.py` (13), `db/activities.py` (12), `db/workspaces.py` (11), `db/wargames.py` (9), `db/courses.py` (8), `db/enrolment.py` (5), and the untyped tail of `db/export_jobs.py`.

**Components:**
- Each `db/*.py` module with ty-flagged Category A sites converted per the Phase 1 conventions.
- For each site: columns referenced by the **post-migration `text(...)` SQL** (not the pre-migration ORM expression) appended to `tools/ty-sa-cleanup/indices-checklist.md`. This matters when the rewrite changes the column set — e.g. an ORM `.relationship.any()` may expand into an explicit SQL JOIN that touches different columns than the original expression suggested.
- Per-file: adjacent dead `# type: ignore[<mypy-code>]` comments removed.
- Per-file: unused `select` / ORM-helper imports cleaned up.
- Per-site: integration-test coverage verified to exist (or added if absent) — mitigates DR1's column-rename trade-off.
- Any N+1 / query-in-loop shape encountered is logged in a draft follow-up issue body.

**Dependencies:** Phase 1 (convention and exemplar established).

**Done when:** `uvx ty@0.0.32 check src/promptgrimoire/db/` exits 0 for Category A. `uv run grimoire test all` green (≤ baseline). Indices checklist extended with post-migration columns. Each migrated site has integration-test coverage.

**Covers:** ty-sa-typing-cleanup.AC1.* (Category A in `db/`).
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Category A Migration in `pages/`, `scripts/`, `tests/`
**Goal:** Migrate the remaining Category A sites outside the `db/` package — roughly 100 diagnostics across `src/promptgrimoire/pages/`, `scripts/smoke_turn_cycle.py`, `scripts/incident/`, `src/promptgrimoire/cli_loadtest.py`, and the handful of test files using ORM query syntax.

**Components:**
- Per-file conversion of remaining Category A sites per Phase 1 conventions.
- Indices checklist extended — entries sourced from post-migration `text(...)` SQL, not pre-migration ORM expressions.
- Per-site: integration-test coverage verified or added (mitigates DR1 column-rename trade-off).
- Dead mypy ignores removed.
- Follow-up issue body continues to accumulate N+1 / query-in-loop observations with file:line references.

**Dependencies:** Phase 1 (convention).

**Done when:** `uvx ty@0.0.32 check` reports zero Category A diagnostics across `src/promptgrimoire/pages/`, `scripts/`, and `tests/`. `uv run grimoire test all` green. Each migrated site has integration-test coverage.

**Covers:** ty-sa-typing-cleanup.AC1.* (Category A outside `db/`).
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Categories B + D — Real Bugs and Metaclass Fixes
**Goal:** Fix the ~17 non-Category-A real issues.

**Components:**
- `scripts/incident/ingest.py`: replace `__import__("pathlib").Path` annotations (7 sites) with a proper `from pathlib import Path` + direct use.
- `scripts/incident/ingest.py`: fix `_fetch_beszel = None` shadowing by typing as `Callable[..., list[dict[str, Any]]] | None = None` and guarding call sites (3 sites, including the downstream `parse_fn` None-callable errors).
- `Result[Any].rowcount` access sites (3): change to proper `CursorResult` typing or cast at use.
- `summary_system_prompt: str | None → str` nullability in `scripts/smoke_turn_cycle.py` (1): resolve with a concrete default or tightened upstream signature.
- `docx` import in `scripts/extract_anthropic_console_to_json.py`: either install available stubs or add to `[tool.ty.src] exclude`.
- `src/promptgrimoire/pages/annotation/tags.py` (or wherever the references live): replace `TagGroup.__table__` / `Tag.__table__` with `__tablename__` or `.metadata.tables[...]` (2 sites).

**Dependencies:** None (can run parallel to Phase 5).

**Done when:** `uvx ty@0.0.32 check` reports zero diagnostics for `scripts/incident/`, `scripts/smoke_turn_cycle.py`, `scripts/extract_anthropic_console_to_json.py`, and the tag-deletion site.

**Covers:** ty-sa-typing-cleanup.AC2.* (Category B), ty-sa-typing-cleanup.AC4.* (Category D).
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Category C — Test Scaffolding Refactor
**Goal:** Eliminate the `**kwargs: object` / `dict[str, object]` patterns in two test files that account for ~51 diagnostics.

**Components:**
- `tests/unit/test_settings.py`: refactor the `original_init(self, *args, **kwargs)` monkey-patch pattern. Either (a) explicit `cast(Settings, self)` + typed args in the wrapper, or (b) restructure to use `Settings.model_validate({...})` rather than monkey-patching `__init__`. Decided per call site during phase execution.
- `tests/unit/test_word_count_models.py`: refactor `_make_activity` / `_make_course` builders from `**overrides: object` + `dict[str, object]` to explicit typed kw-only params with sensible defaults, preserving `**overrides: Any` for arbitrary per-test overrides.

**Dependencies:** None (can run parallel to Phase 4).

**Done when:** `uvx ty@0.0.32 check tests/unit/test_settings.py tests/unit/test_word_count_models.py` reports 0 diagnostics. Tests pass.

**Covers:** ty-sa-typing-cleanup.AC3.* (Category C).
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Index Audit + Alembic Migration (Effectiveness-Gated)
**Goal:** Create PostgreSQL indices on every column enumerated during phases 2–3, bounded by the effectiveness gate.

**Components:**
- Consolidated `tools/ty-sa-cleanup/indices-checklist.md` entries from phases 2–3 (sourced from post-migration `text(...)` SQL).
- **Prod-clone dev DB (required):** current `pg_restore` of grimoire.drbbs.org into the dev DB. Record the dump filename (and its capture timestamp) in the plans files. **If no prod dump is available when phase 6 begins, the phase PAUSES** until one is obtained. Do not substitute a fixture-only or synthetic dev DB without explicit documented fallback (see DoD #5).
- Per candidate index: capture BEFORE plan (`EXPLAIN (ANALYZE, BUFFERS)` × 3, record median) → apply the candidate index ad-hoc → capture AFTER plan → evaluate the effectiveness gate (index name appears in plan AND cost drops AND actual time drops).
- `tools/ty-sa-cleanup/indices-checklist.md` updated per candidate with numeric Before/After cost and actual-time measurements plus the verdict (`added` or `rejected: <reason>`).
- Single Alembic revision `alembic/versions/<rev>_ty_sa_indices.py` containing only the indices that passed the gate, using `op.create_index(..., postgresql_concurrently=True)` inside an `op.get_context().autocommit_block()`.
- BEFORE and AFTER plans committed alongside the migration (inline docstring or `alembic/versions/plans/` directory referenced from the migration).
- Integration test asserting every index named in the migration exists in `pg_indexes` AND is referenced in at least one representative EXPLAIN plan.

**Dependencies:** Phase 2 AND Phase 3 (checklist complete). A current prod `pg_restore`.

**Done when:** Migration applies cleanly to the prod-clone dev DB. Checklist has concrete Before/After numbers for every candidate; each candidate has a verdict (`added` or `rejected: <reason>`). Before/after plans committed. Integration test passes.

**Covers:** ty-sa-typing-cleanup.AC5.* (indices).
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: AST Guard Tests
**Goal:** Install the four regression guards in `tests/unit/`, each following the existing `test_run_javascript_guard.py` shape.

**Components:**
- `tests/unit/test_orm_column_predicate_guard.py` — rejects `$MODEL.$FIELD.<in_|not_in|is_|is_not|like|desc|asc>(...)` at class-level, and `$MODEL.$FIELD == $X` / `!= $X` inside `.where(...)` / `.join(...)` / `.order_by(...)` / `.group_by(...)` / `.having(...)` call arguments. Scope: `src/promptgrimoire/` + `scripts/`. Failure message points to `docs/architecture/raw-sql-convention.md`.
- `tests/unit/test_annotation_dynamic_import_guard.py` — rejects `__import__(...)` inside any `AnnAssign.annotation` / `FunctionDef.returns` / `arg.annotation`. Scope: `src/` + `scripts/` + `tests/`. Unconditional rejection (no PEP permits the pattern).
- `tests/unit/test_module_level_callable_shadow_guard.py` — two-pass AST walk: collect top-level `import $NAME` / `from X import $NAME`, then reject module-level `$NAME = None` assignments to those names. Scope: `src/` + `scripts/`.
- `tests/unit/test_sqlmodel_table_dunder_guard.py` — collects classes extending `SQLModel` (and `table=True`), rejects `Attribute(attr='__table__')` accesses to those class names. Failure message suggests `__tablename__` or `.metadata.tables[...]`. Scope: `src/` + `scripts/` + `tests/`.
- `tests/unit/test_text_sql_safety_guard.py` — walks `Call` nodes whose `func` resolves to `text` (from `sqlalchemy` or re-exported). Rejects any of: `JoinedStr` (f-string) argument, `BinOp` with `%` or `+` argument (percent-format or concatenation). Allows plain `Constant[str]` (prepared-statement template) and `Call(func=Name('tstring'))` (PEP 750 t-string, once adopted). Scope: `src/` + `scripts/` + `tests/`. Failure message: "Raw-SQL composition must use `text('... :name ...') + params` or `tstring(t'...')`; never f-string / `%` / `+` interpolation (SQL injection)."
- Each guard ships with the standard trio: main scanner test, allowlist-exact-set test, synthetic-violation test.

**Dependencies:** Phases 2, 3, 4, 5 (the guards must not fire on unmigrated anti-patterns at the moment they're enabled).

**Done when:** `pytest tests/unit/ -k "guard"` collects the 5 new guards plus their supporting tests (15 test functions total across the 5 files) and they all pass. Each synthetic-violation test exercises its scanner's failure path. `uvx ty@0.0.32 check` still passes after guards are added.

**Covers:** ty-sa-typing-cleanup.AC6.* (guards).
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Documentation
**Goal:** Satisfy the `.ed3d/design-plan-guidance.md` mandatory documentation phase and open the deferred follow-up issues.

**Components:**
- `CLAUDE.md` § Conventions — add a rule establishing `session.execute(text(...), {...})` as the canonical column-predicate idiom for queries where ORM syntax would require a `col()` wrapper, linking to this design and `docs/architecture/raw-sql-convention.md`.
- `docs/database.md` — add a section summarising the raw-SQL query pattern, the indices added by phase 6, and the guard tests that prevent regression.
- `docs/dependency-rationale.md` — update the `ty` entry to explain why the pin stays at 0.0.24 despite 0.0.32 reading clean after this work (stability vs. currency trade-off).
- Open GitHub issue for `ty-sa-tstring-adoption` with findings from phases 2–3 about t-string opportunities; label `phase:post-mvp`.
- Open GitHub issue for `ty-sa-n-plus-one-audit` with N+1 / query-in-loop observations accumulated during phases 2–3; label `phase:post-mvp`.

**Dependencies:** Phases 1–7.

**Done when:** `uv run grimoire docs build` succeeds. All doc edits visible in `git diff`. Two follow-up issues exist on GitHub and are referenced from `## Additional Considerations`.

**Covers:** ty-sa-typing-cleanup.AC7.* (documentation).
<!-- END_PHASE_8 -->

## Additional Considerations

**Baseline capture (required before Phase 1 starts).** Record `git rev-parse HEAD` and the failure/skip counts from `uv run grimoire test all` in this document before any implementation work begins. DoD #4 compares final counts against this baseline. A placeholder table follows:

| Measurement | Value | Captured at |
|---|---|---|
| Base commit | `<sha>` | `<date>` |
| `grimoire test all` passed | `<count>` | `<date>` |
| `grimoire test all` failed | `<count>` | `<date>` |
| `grimoire test all` skipped | `<count>` | `<date>` |

**Rollback story.** The migration is file-by-file; each file's changes land as a coherent commit. Rolling back a single file is `git revert <sha>`. The Alembic index migration is reversible via `alembic downgrade -1`. The AST guards live in `tests/unit/`; adding an allowlist entry unblocks any edge case discovered post-merge.

**Deferred-item follow-ups.**
- `ty-sa-tstring-adoption` — revisit when SQLAlchemy 2.1 GA ships. Current pin `sqlalchemy>=2.0` resolves to 2.0.46; 2.1 is beta-only at plan time (`2.1.0b2`). `sqlalchemy.tstring()` provides native PEP 750 t-string support per the 2.1 release notes. Finding from this design: not adoptable in production today without taking a beta-SA dependency.
- `ty-sa-n-plus-one-audit` — accumulated observations from phases 2–3 feed the issue body. Fixes are behaviour-changing and need per-site test coverage, so they ship in a separate PR rather than bundled here.

**False-positive handling for the Category A guard.** The allowlist is a frozenset of file stems, tested for exact drift. First false positive — if we ever hit one — adds the file stem to the allowlist with a comment explaining why. The guard's scope excludes `tests/` to keep test-fixture builders out of its path.

**Production index creation safety.** `postgresql_concurrently=True` avoids write locks but requires autocommit (cannot run inside an Alembic-wrapped transaction). The migration uses `op.get_context().autocommit_block()` around the index operations. Deploy path is `deploy/restart.sh`, which already handles Alembic migrations correctly.

**Phase count.** 8 phases, at the `.ed3d/design-plan-guidance.md` ≤8 ceiling. A single implementation plan covers the full design without splitting.
