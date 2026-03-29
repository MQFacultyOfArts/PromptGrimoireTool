# Eliminate Awaited JavaScript Calls — Phase 3: Guard Test and Cleanup

**Goal:** Prevent regression with an AST guard test and clean up dead code from the old awaited patterns.

**Architecture:** AST-scanning unit test following the existing `test_value_capture_guard.py` pattern. Allowlist scoped to 3 spike/demo pages. Dead code removal for unused helpers, constants, and imports from Phases 1-2.

**Tech Stack:** Python ast module, pytest

**Scope:** 3 phases from original design (phase 3 of 3)

**Codebase verified:** 2026-03-29

---

## Acceptance Criteria Coverage

This phase implements and tests:

### eliminate-js-await-454.AC6: Guard test prevents regression
- **eliminate-js-await-454.AC6.1 Success:** A test scans `src/promptgrimoire/` for `await ...run_javascript()` and fails if any are found outside the allowlist
- **eliminate-js-await-454.AC6.2 Success:** Allowlist covers only spike/demo pages (`milkdown_spike.py`, `text_selection.py`, `highlight_api_demo.py`)
- **eliminate-js-await-454.AC6.3 Failure:** Adding a new `await ui.run_javascript()` in production code causes the guard test to fail

---

<!-- START_TASK_1 -->
### Task 1: Add AST guard test for `await run_javascript()`

**Verifies:** eliminate-js-await-454.AC6.1, eliminate-js-await-454.AC6.2, eliminate-js-await-454.AC6.3

**Files:**
- Create: `tests/unit/test_run_javascript_guard.py` (unit)

**Implementation:**

Create an AST-scanning guard test following the pattern from `tests/unit/test_value_capture_guard.py`. The test:

1. Collects all `.py` files under `src/promptgrimoire/` via `rglob("*.py")`
2. Skips files in the allowlist (file-level exclusion by stem name)
3. Parses each file with `ast.parse()`
4. Walks the AST looking for `ast.Await` nodes
5. For each `Await`, checks if the inner `value` is a `Call` whose function name contains `run_javascript`
   - Handle both `ui.run_javascript(...)` (attribute access: `ast.Attribute` with `attr == "run_javascript"`) and bare `run_javascript(...)` (name access: `ast.Name` with `id == "run_javascript"`)
   - Handle chained access like `client.run_javascript(...)` and `presence.nicegui_client.run_javascript(...)`
6. Collects violations with file path, line number, and the calling expression
7. Fails with a descriptive message pointing at the design document if any violations exist

**Allowlist:**
```python
_ALLOWLIST: set[str] = {
    "milkdown_spike",
    "text_selection",
    "highlight_api_demo",
}
```

File-level exclusion by stem (not per-function) because these are demo/spike pages behind feature flags (`FEATURES__ENABLE_DEMO_PAGES`).

**Failure message template:**
```
Found {count} `await ...run_javascript()` call(s) in production code.
These block the asyncio event loop. See docs/design-plans/2026-03-29-eliminate-js-await-454.md.

Violations:
  {path}:{lineno} — await ...run_javascript(...)

If this is a spike/demo page, add its stem to _ALLOWLIST in this test.
```

**Testing:**
- eliminate-js-await-454.AC6.1: The test itself IS the guard — verify it passes on the post-Phase-2 codebase
- eliminate-js-await-454.AC6.2: Verify the allowlist contains exactly the 3 demo pages
- eliminate-js-await-454.AC6.3: Temporarily add `await ui.run_javascript("test")` to a production file, verify the test catches it, then revert

**Verification:**
Run: `uv run grimoire test run tests/unit/test_run_javascript_guard.py`
Expected: Test passes (0 violations outside allowlist)

**Commit:** `test: add AST guard test preventing await run_javascript() regression (#454)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Remove dead code from old awaited patterns

**Verifies:** None (cleanup — no functional change)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tab_bar.py` — remove `_SCROLL_SAVE_JS` constant (lines 161-166) if dead after Phase 1 scroll conversion
- Modify: `src/promptgrimoire/pages/annotation/respond.py` — remove `_sync_markdown_to_crdt` function if eliminated in Phase 2
- Modify: `src/promptgrimoire/pages/restart.py` — remove `_flush_single_client` function if eliminated in Phase 2
- Modify: various files — remove unused `timeout=` parameters, unused imports (e.g., `TimeoutError`, `OSError` if no longer caught)

**Implementation:**

Scan all files modified in Phases 1-2 for:

1. **Dead functions:** `_sync_markdown_to_crdt`, `_flush_single_client`, `_rebuild_organise_with_scroll` (if fully replaced)
2. **Dead constants:** `_SCROLL_SAVE_JS` in `tab_bar.py:161-166`
3. **Dead imports:** `TimeoutError`, `OSError` if no longer caught in `respond.py` or `pdf_export.py`; unused `contextlib` if suppress blocks were removed
4. **Dead parameters:** `sync_respond_markdown` on `PageState` (line 310) if removed in Phase 2

Run `vulture` to confirm:
```bash
uv run vulture src/promptgrimoire/ --min-confidence 80
```

Remove all confirmed dead code. Do NOT remove code that is still referenced.

**Retention notes (from vulture + manual review):**
- `_rebuild_organise_with_scroll` — **retained**, live code. Called at `tab_bar.py:275` (assigned to `state.refresh_organise_with_scroll`) and invoked at `tab_bar.py:346`. Phase 1 replaced `_SCROLL_SAVE_JS` but not this function.
- `_sync_markdown_to_crdt` — removed in Phase 2
- `_flush_single_client` — removed in Phase 2
- `_SCROLL_SAVE_JS` — removed in this phase
- `sync_respond_markdown` on `PageState` — removed in Phase 2
- `vulture --min-confidence 80` reports no dead code

**Verification:**
Run: `uv run grimoire test all`
Run: `uv run vulture src/promptgrimoire/ --min-confidence 80`
Expected: Tests pass, vulture reports no new dead code from this change

**Commit:** `refactor: remove dead code from old awaited JS patterns (#454)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Link #454 to epic #142

**Verifies:** None (project management)

**Files:**
- None (GitHub API only)

**Implementation:**

Add #454 as a tracked item under epic #142 (Annotation page performance):

```bash
gh issue comment 142 --body "Tracking #454 (Eliminate awaited JavaScript calls) — removes all \`await run_javascript()\` from production code, converting to fire-and-forget and event-driven patterns."
```

Also add a reference in #454 pointing to this implementation plan:

```bash
gh issue comment 454 --body "Implementation plan: \`docs/implementation-plans/2026-03-29-eliminate-js-await-454/\`"
```

**Verification:**
Check both issues show the cross-references.

**Note:** This task can be done at any point — it is order-independent and does not block any other task.

**Commit:** No commit (GitHub comments only)
<!-- END_TASK_3 -->

---

## UAT Steps

1. [ ] Temporarily add `await ui.run_javascript("test")` to a production file (e.g., `respond.py`)
2. [ ] Run: `uv run grimoire test run tests/unit/test_run_javascript_guard.py`
3. [ ] Verify: the test fails and names the offending file and line
4. [ ] Remove the test line
5. [ ] Run the guard test again — it should pass
6. [ ] Run: `uv run vulture src/promptgrimoire/ --min-confidence 80` — verify no dead code from old patterns

## Evidence Required
- [ ] Test output showing green for `uv run grimoire test all`
- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] `uvx ty@0.0.24 check` passes
- [ ] Guard test output showing 0 violations
- [ ] Complexipy results: `uv run complexipy src/promptgrimoire/pages/annotation/tab_bar.py src/promptgrimoire/pages/annotation/respond.py src/promptgrimoire/pages/restart.py`
