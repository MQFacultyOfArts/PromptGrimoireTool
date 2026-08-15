# Export Table Cell Normaliser Design

**GitHub Issue:** None

## Summary

<!-- TO BE GENERATED after body is written -->

## Definition of Done

1. **Health Domain workspace exports successfully.** The malformed prod artefact (rehydrated from fixture into a dev DB) compiles to a non-empty PDF through `convert_html_with_annotations` end-to-end, without raising `subprocess.CalledProcessError` and without the lualatex error `! LaTeX Error: There's no line here to end.`
2. **Runaway table cells are hoisted before pandoc.** Any `<td>`/`<th>` containing a nested `<table>` or ≥ 2 immediate block-level children (`<p>`, `<ul>`, `<ol>`, `<hr>`, `<h1>`–`<h6>`) is rewritten so its children become siblings of the enclosing `<table>`, before the HTML reaches the pandoc subprocess.
3. **Hoisting is observable.** Each hoist emits an `export.table_cell_hoisted` warning-level structlog event with `cell_size_bytes`, `block_child_count`, `has_nested_table`, `iteration`, `enclosing_table_path`, and `workspace_id`. Iteration cap (8) emits an error-level event.
4. **Property-based discovery runs in CI.** Hypothesis property tests for the new normaliser execute in the unit lane on every PR (~50 examples) and in the nightly slow workflow (~1000 examples). A failing example is shrunk and reported.
5. **Health Domain regression fixture is committed and rehydratable.** `tests/fixtures/health_domain_workspace_scrubbed.json` is PII-scrubbed and committed; `scripts/scrub_health_domain.py` regenerates it from a fresh prod extract; `ensure_health_domain_workspace()` rehydrates idempotently into a test DB.
6. **Reusable HTML strategy + property catalog exists.** `tests/strategies/html.py` and `tests/strategies/properties.py` provide HTML element strategies and reusable invariants usable by all current and future HTML normalisers.
7. **Existing normalisers gain shared-catalog property coverage.** `strip_scripts_and_styles`, `normalise_styled_paragraphs`, and `fix_midword_font_splits` each get idempotency / text-preservation / well-formedness property tests. Real bugs surfaced by Hypothesis are `@pytest.mark.xfail(strict=True)` with a referenced GitHub issue, not fixed in this PR.

## Acceptance Criteria

### export-table-cell-normaliser.AC1: Health Domain workspace exports successfully
- **export-table-cell-normaliser.AC1.1 Success:** Rehydrated Health Domain workspace exports to a non-empty PDF (>1 KB) via `convert_html_with_annotations` end-to-end
- **export-table-cell-normaliser.AC1.2 Success:** Export completes without raising `subprocess.CalledProcessError` from lualatex on the Health Domain fixture input
- **export-table-cell-normaliser.AC1.3 Failure:** The lualatex error `! LaTeX Error: There's no line here to end.` never appears in compilation logs for the Health Domain fixture
- **export-table-cell-normaliser.AC1.4 Edge:** If the fixture JSON is missing (e.g. fresh checkout without the file), the end-to-end smoke test `pytest.skip`s rather than failing CI

### export-table-cell-normaliser.AC2: Runaway table cells are hoisted before pandoc
- **export-table-cell-normaliser.AC2.1 Success:** A `<td>` or `<th>` containing any descendant `<table>` triggers hoisting
- **export-table-cell-normaliser.AC2.2 Success:** A cell with ≥ 2 immediate block-level children (any of `<p>`, `<ul>`, `<ol>`, `<hr>`, `<h1>`–`<h6>`) triggers hoisting
- **export-table-cell-normaliser.AC2.3 Success:** A cell with exactly 1 immediate block-level child and no nested table does **not** trigger hoisting
- **export-table-cell-normaliser.AC2.4 Success:** A cell with 0 block children and no nested table does **not** trigger hoisting
- **export-table-cell-normaliser.AC2.5 Success:** After running `hoist_runaway_table_cells`, the post-transform HTML contains zero triggering cells (verified by `assert_no_runaway_cells_remain`)
- **export-table-cell-normaliser.AC2.6 Success:** Hoisted children become siblings of the enclosing `<table>`, inserted immediately after it in document order, preserving original child order
- **export-table-cell-normaliser.AC2.7 Edge:** Empty `<tr>` and empty `<table>` elements resulting from hoisting are removed
- **export-table-cell-normaliser.AC2.8 Edge:** Cells nested inside a hoisted cell (e.g. Health Domain Table 2 at depth 6) are correctly handled by fixed-point iteration in subsequent passes

### export-table-cell-normaliser.AC3: Hoisting is observable via structlog
- **export-table-cell-normaliser.AC3.1 Success:** Each hoist emits one `export.table_cell_hoisted` warning event containing all six fields: `cell_size_bytes`, `block_child_count`, `has_nested_table`, `iteration`, `enclosing_table_path`, `workspace_id`
- **export-table-cell-normaliser.AC3.2 Success:** `workspace_id` is `None` when the function is called without one (unit tests) and the actual workspace UUID when called via the export pipeline
- **export-table-cell-normaliser.AC3.3 Success:** Reaching the 8-iteration cap emits `export.table_cell_hoist_iteration_cap_reached` at error level with `iterations_attempted` and `cells_remaining` fields
- **export-table-cell-normaliser.AC3.4 Failure:** lxml parse failure on input emits `export.table_cell_hoist_parse_failed` at warning level and returns the input unchanged

### export-table-cell-normaliser.AC4: Property-based discovery runs in CI
- **export-table-cell-normaliser.AC4.1 Success:** Unit lane (`grimoire test all`) runs property tests with the `ci` profile (50 examples, 2 s deadline)
- **export-table-cell-normaliser.AC4.2 Success:** Nightly slow workflow (`nightly-e2e-slow.yml`) runs property tests with the `nightly` profile (1000 examples, 30 s deadline)
- **export-table-cell-normaliser.AC4.3 Failure:** A failing property example is shrunk by Hypothesis and the minimal HTML appears in the test output for triage
- **export-table-cell-normaliser.AC4.4 Edge:** CI profile is selected automatically based on `CI` environment variable; nightly profile is selected by an explicit env var the workflow sets

### export-table-cell-normaliser.AC5: Health Domain fixture is committed and rehydratable
- **export-table-cell-normaliser.AC5.1 Success:** `tests/fixtures/health_domain_workspace_scrubbed.json` is committed to git
- **export-table-cell-normaliser.AC5.2 Success:** `scripts/scrub_health_domain.py` regenerates the fixture deterministically (re-running on the same raw extract produces byte-identical output)
- **export-table-cell-normaliser.AC5.3 Success:** `ensure_health_domain_workspace()` is idempotent — calling twice in the same test does not error
- **export-table-cell-normaliser.AC5.4 Success:** `load_health_domain_html()` returns a non-empty string on which the trigger predicates from AC2.1 / AC2.2 fire
- **export-table-cell-normaliser.AC5.5 Failure:** Author name, user IDs, document IDs, workspace ID, activity ID, and course ID in the committed fixture contain no real PII — all are deterministic test placeholders
- **export-table-cell-normaliser.AC5.6 Edge:** The HTML body in the committed fixture is byte-identical to the original prod extract (the structural malformation survives scrubbing — required for the regression test to be meaningful)

### export-table-cell-normaliser.AC6: Reusable HTML strategy + property catalog exists
- **export-table-cell-normaliser.AC6.1 Success:** `tests/strategies/html.py` exposes `text_strategy`, `inline_element_strategy`, `block_element_strategy`, `table_strategy`, `document_strategy`
- **export-table-cell-normaliser.AC6.2 Success:** `tests/strategies/properties.py` exposes `assert_idempotent`, `assert_text_preserved`, `assert_well_formed_html`, `assert_no_runaway_cells_remain`
- **export-table-cell-normaliser.AC6.3 Success:** Hypothesis profiles `ci`, `default`, and `nightly` are registered at import time of `tests/strategies/__init__.py`
- **export-table-cell-normaliser.AC6.4 Success:** `table_strategy(malformations=True)` can produce cells with up to 500 immediate block children and nested tables up to depth 5 (parameter bounds documented in the docstring)

### export-table-cell-normaliser.AC7: Existing normalisers covered by shared catalog
- **export-table-cell-normaliser.AC7.1 Success:** `strip_scripts_and_styles` has property tests for `_idempotent`, `_preserves_visible_text`, `_well_formed`
- **export-table-cell-normaliser.AC7.2 Success:** `normalise_styled_paragraphs` has the same three property tests
- **export-table-cell-normaliser.AC7.3 Success:** `fix_midword_font_splits` has the same three property tests
- **export-table-cell-normaliser.AC7.4 Failure:** Any property test that fails under Hypothesis is marked `@pytest.mark.xfail(strict=True, reason="found by hypothesis, see #N")` with N referencing an open GitHub issue containing the shrunk minimal example

## Glossary

<!-- TO BE GENERATED after body is written -->

## Architecture

The defence is a single new pure function, `hoist_runaway_table_cells(html_content: str, *, workspace_id: str | None = None) -> str`, added to `src/promptgrimoire/export/html_normaliser.py` alongside the three existing pre-pandoc normalisers. The function uses lxml to round-trip the HTML, identify malformed cells via two predicates, mutate the tree to hoist their contents, and serialise back. Parse failure falls back to returning the input unchanged with a structlog warning, mirroring `normalise_styled_paragraphs`.

The pipeline integration point is `src/promptgrimoire/export/pandoc.py::convert_html_to_latex`. The new normaliser is called immediately after `normalise_styled_paragraphs` and before the pandoc subprocess. This ordering matters: the block-child counting predicate must observe the post-styled-paragraph DOM shape, since `normalise_styled_paragraphs` wraps `<p style>` in `<div style><p></p></div>` and that wrapping changes immediate-child counts.

The data flow for a malformed input is:

```
prod HTML
  ↓ strip_scripts_and_styles
  ↓ normalise_styled_paragraphs        (existing)
  ↓ hoist_runaway_table_cells          (NEW — fixes the row that breaks lualatex)
  ↓ pandoc subprocess                  (now produces compilable LaTeX)
  ↓ post-process (control chars, newline fixes, foreignlanguage strip, textquotesingle fix)
  ↓ LaTeX body → latexmk → PDF
```

Test infrastructure is layered. A new `tests/strategies/` package holds reusable Hypothesis strategies for HTML (`html.py`) and property assertions (`properties.py`). Property tests for the new normaliser live in `tests/unit/test_html_normaliser_hoist.py`; property tests against the three existing normalisers live in `tests/unit/test_existing_normalisers_properties.py`. A regression test loads the Health Domain fixture; a fast pandoc-integration test asserts no malformed `\newline` patterns in the LaTeX output; a slow smoke test compiles the LaTeX to PDF; an end-to-end smoke test runs the full export pipeline against the rehydrated workspace and asserts a non-empty PDF.

The Health Domain fixture follows the existing Pabai pattern: a PII-scrubbed JSON file at `tests/fixtures/health_domain_workspace_scrubbed.json`, regenerable via a committed scrubber script, with a two-tier helper layout — a flat `tests/fixtures/health_domain.py::load_health_domain_html()` for unit/property tests that need only the HTML string, and `ensure_health_domain_workspace()` in `tests/e2e/card_helpers.py` for integration tests that need the full workspace inserted into a test DB.

## Decision Record

### DR1: Pre-pandoc HTML rewrite over post-pandoc LaTeX repair
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If pandoc's `longtable` writer changes its row-terminator emission such that the `\newline`-after-`\\` pattern is no longer the dominant failure mode; if a class of malformed Word HTML emerges that survives the predicates.

**Decision:** We chose to defend against malformed table cells by rewriting the HTML before pandoc sees it, rather than parsing pandoc's LaTeX output and repairing the row terminators downstream.

**Consequences:**
- **Enables:** A defence aligned with the failure's source (HTML malformation from Word). The fix lives next to other pre-pandoc normalisers, sharing their idiom and failure-handling pattern. lxml is already a dependency.
- **Prevents:** Any post-pandoc LaTeX-AST parsing infrastructure that could be reused for other LaTeX-level fixes. We accept that future LaTeX-level defences would need their own scaffolding.

**Alternatives considered:**
- **Post-pandoc LaTeX repair (regex on output):** Rejected — the problematic `\newline` after `\\` pattern is fragile to detect once buried in pandoc's longtable structure, and a successful repair on this case wouldn't generalise to other table-cell-runaway shapes.
- **Cell-content streaming (incremental parse):** Rejected — overkill for the size of the malformations observed (Health Domain's worst cell is 56 KB, well within full-tree lxml budget).

### DR2: Detection by structural predicates over content size
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If a real-world malformation surfaces that contains a nested table or many block children but is *legitimate* (e.g. an intentional layout table that should not be hoisted).

**Decision:** A cell triggers hoisting iff it contains any descendant `<table>` OR has ≥ 2 immediate block-level children (`<p>`, `<ul>`, `<ol>`, `<hr>`, `<h1>`–`<h6>`). Size-based thresholds (e.g. "cell > 10 KB") were not used.

**Consequences:**
- **Enables:** A precise rule grounded in structure rather than arbitrary thresholds. The Health Domain failure case fires both predicates (387 block children, 1 nested table), giving redundant evidence. Property tests can target the boundary directly.
- **Prevents:** Catching malformations whose structure is benign but content is huge (e.g. a single 100 KB paragraph in a cell). We accept this — pandoc handles those cases without lualatex aborting.

**Alternatives considered:**
- **Cell serialised size > N KB:** Rejected — arbitrary, and the actual lualatex failure mode is structural (multiple block elements forcing pandoc's longtable writer into invalid `\newline` emission), not size-based.
- **Block-child count threshold > 1 only (no nested-table predicate):** Rejected — would miss the case of a cell with a single nested `<table>` and no other block children, which the lualatex failure mode could still trigger via the inner table's row terminators.

### DR3: Iterate to fixed point with safety cap
**Status:** Accepted
**Confidence:** Medium
**Reevaluation triggers:** If the 8-iteration cap is reached in production logs, indicating real-world malformations deeper than the design accounts for.

**Decision:** Run hoisting in a loop until no triggering cell remains, capped at 8 iterations. On cap-reached, emit an error-level structlog event and return the partial result.

**Consequences:**
- **Enables:** Correct handling of the Health Domain case, where Table 2 is nested 6 levels deep inside a runaway cell — surfacing it as a sibling on the first pass requires re-evaluation on the second pass.
- **Prevents:** Pathological infinite loops on adversarial input (the cap is the safety mechanism). 8 iterations is enough headroom for any real-world Word output observed; if production hits it, we have a logged signal to act on rather than a silent hang.

**Alternatives considered:**
- **Single pass:** Rejected — Health Domain fixture has depth-6 nested table; single pass would leave the inner table's runaway cell unhoisted.
- **Unbounded iteration:** Rejected — no safety mechanism against pathological inputs from adversarial users or future Word output bugs.

### DR4: Hypothesis as a project dependency
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If property tests prove unreliable (excessive flakes, slow CI) such that they degrade the lane's signal.

**Decision:** Add `hypothesis` to `pyproject.toml` dev dependencies and build a shared strategy/property catalog under `tests/strategies/` that this PR and all future HTML-normaliser work can reuse.

**Consequences:**
- **Enables:** Discovery-oriented testing — Hypothesis explores the predicate boundary with hundreds of generated inputs and shrinks failures to minimal structural cases. The catalog pays dividends across all current and future HTML normalisers.
- **Prevents:** Hand-built test-input generators for each normaliser (a known-bad pattern that yields shallow coverage).

**Alternatives considered:**
- **Hand-rolled fuzz harnesses per normaliser:** Rejected — duplicates effort, lacks Hypothesis's shrinking and statistics infrastructure.
- **Fixture-only testing (no property tests):** Rejected — explicitly contrary to user intent that the test infrastructure discover edge cases we haven't thought of.

### DR5: Two-tier fixture helpers
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If a third tier emerges (e.g. property tests that need workspace metadata but no DB).

**Decision:** Provide `tests/fixtures/health_domain.py::load_health_domain_html() -> str` for unit/property tests, and `tests/e2e/card_helpers.py::ensure_health_domain_workspace() -> str` for integration tests, both backed by the same JSON fixture.

**Consequences:**
- **Enables:** Property tests run in the unit lane without DB or pytest skip overhead; integration tests use the established Pabai pattern. Each tier costs only what it needs.
- **Prevents:** A single locator forcing unit tests to skip when no DB is configured (current Pabai pattern).

**Alternatives considered:**
- **Single `ensure_*` helper:** Rejected — forces unit-lane property tests to either spin up a DB or skip, both bad.
- **HTML-only fixture (no full workspace JSON):** Rejected — the integration smoke test (#9) needs the full workspace shape, and a single source-of-truth JSON is cheaper than maintaining two fixtures.

### DR6: Apply existing-normaliser property coverage now, xfail any real bugs
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If Hypothesis surfaces > 3 real bugs in existing normalisers, scope may need re-evaluation.

**Decision:** Apply the new shared property catalog to the three existing normalisers in this PR. Any failure surfaced by Hypothesis is `@pytest.mark.xfail(strict=True)` with a linked GitHub issue; the bug is not fixed in this PR.

**Consequences:**
- **Enables:** Free regression coverage on production-critical functions; latent bugs surface with shrunk minimal repros attached to issues for follow-up.
- **Prevents:** Scope creep into existing-normaliser bugfixes. `xfail(strict=True)` ensures that if someone later fixes the bug without removing the marker, the test fails loudly.

**Alternatives considered:**
- **Defer to a separate PR:** Rejected — the catalog exists in this PR anyway, the wrapper tests are 3 lines each, and deferring loses signal.
- **Fix any surfaced bugs in this PR:** Rejected — unbounded scope, breaks branch contract.

## Existing Patterns

Investigation surfaced three patterns this design follows.

**Pre-pandoc normaliser idiom (`src/promptgrimoire/export/html_normaliser.py`).** The existing `normalise_styled_paragraphs` is the model: a public pure function, a private mutator helper, lxml round-trip with parse-fail fallback that returns the input unchanged after a structlog warning. `hoist_runaway_table_cells` follows this exactly — public pure function, private `_hoist_cell_contents` helper, identical fallback shape.

**PII-scrubbed workspace fixture (`tests/fixtures/pabai_workspace_scrubbed.json` + `tests/e2e/card_helpers.py::ensure_pabai_workspace`).** The Pabai fixture defines the JSON shape (`{workspace, documents, tag_groups, tags, extracted_at, source_db}`), the rehydration mechanism (delegates to `scripts.rehydrate_workspace.rehydrate`), and the helper convention (module-level workspace ID constant, fixture path constant, `pytest.skip` on missing fixture). The Health Domain helper mirrors this exactly.

**Workspace extraction tooling (`scripts/extract_workspace.py`, `scripts/rehydrate_workspace.py`).** The existing CLI extracts a workspace from PostgreSQL as JSON with base64-encoded binary fields. This PR adds `scripts/scrub_health_domain.py` as a thin downstream consumer: read the raw extract, redact, write the scrubbed fixture. Both the extraction and rehydration tools already exist; this PR only adds the redaction layer.

No divergence from existing patterns. No new patterns introduced beyond `tests/strategies/` (a new test-infrastructure package — orthogonal to production code patterns).

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Hypothesis dependency + shared strategy/property scaffolding
**Goal:** Add `hypothesis` to project dev dependencies; create the reusable strategy and property modules so subsequent phases can import them.

**Components:**
- `pyproject.toml` — add `hypothesis` to dev dependencies; document choice in `docs/dependency-rationale.md`.
- `tests/strategies/__init__.py` — register Hypothesis profiles `ci` (50 examples, 2 s deadline), `default` (200 examples, 5 s), `nightly` (1000 examples, 30 s).
- `tests/strategies/html.py` — strategies: `text_strategy()` (unicode + BLNS subset imported from `tests/fixtures/blns.json`), `inline_element_strategy()`, `block_element_strategy(max_depth)`, `table_strategy(*, max_rows, max_cols, max_cell_blocks, allow_nested_tables, malformations)`, `document_strategy()`.
- `tests/strategies/properties.py` — assertions: `assert_idempotent(transform)`, `assert_text_preserved(before, after)`, `assert_well_formed_html(html)`, `assert_no_runaway_cells_remain(html)`.

**Dependencies:** None.

**Done when:** `uv sync` succeeds; `uv run pytest --collect-only tests/strategies/` shows the modules import cleanly; `uvx ty@0.0.24 check tests/strategies/` is clean; `docs/dependency-rationale.md` has a `hypothesis` entry.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Health Domain fixture and helpers
**Goal:** Commit the PII-scrubbed Health Domain fixture, the regenerable scrubber script, and the two-tier helpers.

**Components:**
- `scripts/scrub_health_domain.py` — reads `/tmp/workspace_<uuid>.json` (raw extract; never committed), applies the redactions documented in the design (author name → "Test Student", user_id → fixed test UUID, workspace/document/activity/course IDs → fixed mapping, highlight `comments` → cycled placeholders, HTML body kept verbatim, tags kept), writes `tests/fixtures/health_domain_workspace_scrubbed.json`. Idempotent and type-checked.
- `tests/fixtures/health_domain_workspace_scrubbed.json` — committed scrubbed fixture, structurally compatible with `scripts.rehydrate_workspace.rehydrate`.
- `tests/fixtures/health_domain.py` — `load_health_domain_html() -> str`; reads JSON, returns malformed HTML.
- `tests/e2e/card_helpers.py` — append `HEALTH_DOMAIN_WORKSPACE_ID` constant, `HEALTH_DOMAIN_FIXTURE_JSON` path, `ensure_health_domain_workspace() -> str` mirroring `ensure_pabai_workspace`.

**Dependencies:** Phase 1 (no — Phase 2 is independent of strategies; can run in parallel with Phase 1).

**Done when:** Scrubber runs cleanly against `/tmp/workspace_<uuid>.json` and produces a deterministic output; fixture file commits to git; `load_health_domain_html()` returns a non-empty string containing the structural malformation; `ensure_health_domain_workspace()` round-trips into a test DB without raising. Unit tests verify each of these.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Implement `hoist_runaway_table_cells` (TDD)
**Goal:** Implement the new normaliser using TDD against the property catalog and the Health Domain fixture. RED → GREEN → REFACTOR within the phase; all property tests and the regression test pass at phase end.

**Components:**
- `src/promptgrimoire/export/html_normaliser.py` — public `hoist_runaway_table_cells(html_content, *, workspace_id=None) -> str`; private `_hoist_cell_contents(cell)` mutator helper; structlog events `export.table_cell_hoisted` (warning) and `export.table_cell_hoist_iteration_cap_reached` (error) and `export.table_cell_hoist_parse_failed` (warning fallback).
- `tests/unit/test_html_normaliser_hoist.py` — property tests: `test_hoist_idempotent`, `test_hoist_preserves_visible_text`, `test_hoist_output_well_formed`, `test_hoist_eliminates_runaway_cells_under_fuzz` (the discovery test, using `table_strategy(malformations=enabled, max_cell_blocks=500, allow_nested_tables=True)`), `test_hoist_noop_on_clean_input`. Deterministic tests: `test_hoist_iteration_cap_emits_error_log` (synthetic deep-nested input), `test_health_domain_fixture_no_runaway_cells_after_hoist` (regression on fixture).

**Dependencies:** Phase 1 (strategies/properties), Phase 2 (Health Domain fixture).

**Done when:** All 7 tests in `test_html_normaliser_hoist.py` pass; `uv run grimoire test run tests/unit/test_html_normaliser_hoist.py` is green; `uv run ruff check . && uvx ty@0.0.24 check` clean.

**Acceptance criteria covered:** AC2 (hoisting algorithm), AC3 (logging contract — partial; full coverage with workspace_id requires Phase 4 wire-up).
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Pipeline integration + fast integration test
**Goal:** Wire `hoist_runaway_table_cells` into the export pipeline and prove the integration with a fast pandoc-only test.

**Components:**
- `src/promptgrimoire/export/pandoc.py::convert_html_to_latex` — call `hoist_runaway_table_cells(normalised_html, workspace_id=...)` between line 328 (`normalised_html = normalise_styled_paragraphs(html)`) and line 343 (pandoc subprocess); thread `workspace_id` through from the calling context.
- `tests/integration/test_pandoc_hoist_integration.py::test_runaway_cell_produces_valid_latex_output` — small synthetic malformed HTML → `convert_html_to_latex` → assert no `\newline` adjacent to `\\` row terminator in the output. Behavioural; no internals mocked.

**Dependencies:** Phase 3 (the function must exist and pass tests).

**Done when:** The integration test passes; existing pandoc tests still green; `workspace_id` propagates from the export entry point through to the structlog event.

**Acceptance criteria covered:** AC1 (Health Domain compiles — partial; the LaTeX-level test confirms the broken pattern is gone), AC2 (full integration), AC3 (workspace_id now logged correctly end-to-end).
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Property coverage for existing normalisers
**Goal:** Apply the shared property catalog to `strip_scripts_and_styles`, `normalise_styled_paragraphs`, and `fix_midword_font_splits`; xfail+issue any real bugs surfaced.

**Components:**
- `tests/unit/test_existing_normalisers_properties.py` — for each of the three existing normalisers, assert `_idempotent`, `_preserves_visible_text`, `_well_formed`. 9 tests total.
- For each Hypothesis-surfaced failure: `@pytest.mark.xfail(strict=True, reason="found by hypothesis, see #N")` with the shrunk minimal example; open a GitHub issue containing the minimal HTML + expected vs actual behaviour.

**Dependencies:** Phase 1 (strategies/properties).

**Done when:** All 9 property tests either pass cleanly or are `xfail(strict=True)` with a linked open issue; `uv run grimoire test run tests/unit/test_existing_normalisers_properties.py` is green (or xfail-green); a follow-up issue exists for each xfail.

**Acceptance criteria covered:** AC4 (property tests run in CI), AC7 (existing normalisers covered).
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: End-to-end smoke (lualatex compile + Health Domain export)
**Goal:** Close the loop with two slow-lane tests: synthetic-input PDF compile, and full-pipeline Health Domain workspace export.

**Components:**
- `tests/e2e/test_pandoc_hoist_compiles.py::test_runaway_cell_input_compiles_to_pdf` with `@requires_full_latexmk` — synthetic malformed HTML → `convert_html_to_latex` → write `.tex` → `lualatex` → assert non-empty PDF.
- `tests/e2e/test_health_domain_export.py::test_health_domain_workspace_exports_pdf` with `@requires_full_latexmk` — `ensure_health_domain_workspace()` → trigger full export through `convert_html_with_annotations` → assert PDF written and `> 1 KB`.

**Dependencies:** Phase 4 (pipeline integration), Phase 2 (Health Domain fixture).

**Done when:** Both smoke tests pass under `uv run grimoire e2e slow`; tests are correctly excluded from default CI by the `smoke` marker auto-applied by `requires_full_latexmk`; nightly `nightly-e2e-slow.yml` workflow runs them.

**Acceptance criteria covered:** AC1 (Health Domain compiles end-to-end), AC4 (nightly profile coverage), AC5 (fixture rehydration end-to-end).
<!-- END_PHASE_6 -->

## Additional Considerations

**Error handling.** Three failure modes are explicit. (1) lxml parse failure on the input — log `export.table_cell_hoist_parse_failed` warning, return input unchanged, mirroring `normalise_styled_paragraphs`. (2) Iteration cap reached — log `export.table_cell_hoist_iteration_cap_reached` error, return partial result. (3) Mutation raises (e.g. lxml internal error during sibling insertion) — let it propagate; the export pipeline already converts subprocess failures to structured errors at a higher layer.

**Performance.** The lxml round-trip and per-cell predicate evaluation is bounded by document size. The Health Domain fixture (112 KB, 387 block children in the worst cell) round-trips in ~50 ms locally; the iteration loop adds at most 8× that worst case. No evidence of a hot path concern — this fires only on malformed input, and the lualatex failure it prevents is far costlier (export aborts entirely).

**Future extensibility.** The shared `tests/strategies/` package is designed for reuse. Future HTML-touching code (input pipeline normalisers, export filters) can import the same strategies and properties. The decision-record protocol for handling Hypothesis-surfaced bugs (xfail+issue, never silently delete) generalises cleanly.

**Out of scope (deferred).** (1) Default project log level change from `DEBUG` to `WARNING` — user is handling in a separate worktree. (2) Fixing any real bugs Hypothesis surfaces in the three existing normalisers — `xfail`'d here, addressed in follow-up PRs. (3) Post-pandoc LaTeX-level repairs for table-cell malformations that survive the predicates — no evidence such cases exist; revisit if production logs show them.
