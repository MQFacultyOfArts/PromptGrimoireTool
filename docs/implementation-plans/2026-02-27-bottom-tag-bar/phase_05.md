# Bottom-Anchored Tag Bar Implementation Plan — Phase 5

**Goal:** Playwright E2E test that guards against CSS regressions (Quasar overrides) and verifies layout correctness.

**Architecture:** Two test functions in a new file: structural CSS assertions (computed property checks on key elements) and behavioural assertions (toolbar visible at bottom, content not obscured, no inline title/UUID). Uses Playwright's native `to_have_css()` and `bounding_box()` APIs — no JS evaluation.

**Tech Stack:** Playwright (Python), pytest

**Scope:** 5 phases from original design (phase 5 of 5)

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### bottom-tag-bar.AC5: E2E CSS audit
- **bottom-tag-bar.AC5.1 Success:** Playwright test verifies computed CSS for toolbar, layout wrapper, sidebar, compact buttons, and annotation cards
- **bottom-tag-bar.AC5.2 Failure:** Test fails if any checked property doesn't match expected value (catches future Quasar overrides)

---

## Reference Files

The executor should read these for project context:
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/CLAUDE.md` — Project conventions and E2E test rules
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/docs/testing.md` — Test guidelines, E2E patterns
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/docs/e2e-debugging.md` — E2E infrastructure, cleanup patterns
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/tests/e2e/conftest.py` — E2E fixtures (authenticated_page, _create_workspace_via_db)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/tests/e2e/annotation_helpers.py` — Workspace creation helpers, wait_for_text_walker
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/bottom-tag-bar/tests/e2e/test_annotation_drag.py:143` — Existing `to_have_css()` example

---

<!-- START_TASK_1 -->
### Task 1: Create E2E CSS audit test file

**Verifies:** bottom-tag-bar.AC5.1, bottom-tag-bar.AC5.2

**Files:**
- Create: `tests/e2e/test_css_audit.py`

**Implementation:**

Create a new E2E test file `tests/e2e/test_css_audit.py` with two test functions:

**Test setup pattern** (matches existing E2E conventions):
- Use `authenticated_page` fixture for browser page
- Create workspace via `_create_workspace_via_db()` with simple HTML content (e.g., `<p>Test content for CSS audit</p>`)
- Navigate to annotation page: `page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")`
- Wait for render: `wait_for_text_walker(page, timeout=15000)`

**Test 1: `test_structural_css_properties`** — Quasar regression guard

Assert computed CSS properties on key elements. These catch Quasar framework updates that silently override application styles:

| Element | Locator | Property | Expected Value |
|---------|---------|----------|----------------|
| Toolbar wrapper | `#tag-toolbar-wrapper` | `position` | `fixed` |
| Toolbar wrapper | `#tag-toolbar-wrapper` | `bottom` | `0px` |
| Toolbar wrapper | `#tag-toolbar-wrapper` | `box-shadow` | `rgba(0, 0, 0, 0.1) 0px -2px 4px 0px` |
| Compact button (first) | `.q-btn.compact-btn >> nth=0` | `padding` | `0px 6px` |
| Highlight menu | `#highlight-menu` | `z-index` | `110` |

Notes:
- The toolbar wrapper ID was added in Phase 1 Task 1
- Compact button padding check catches Quasar's `.q-btn` override (the whole reason for the `.q-btn.compact-btn` specificity fix)
- Highlight menu z-index is asserted on the hidden element — `to_have_css()` uses `getComputedStyle()` which works on `display: none` elements
- Sidebar `position: relative` may also be worth asserting if a suitable locator exists — the executor should check the sidebar structure during implementation

**Test 2: `test_layout_correctness`** — Behavioural assertions

Verify the bottom toolbar layout works correctly:

1. **Toolbar at viewport bottom:** Get toolbar `bounding_box()`. Assert that `toolbar.y + toolbar.height` is approximately equal to viewport height (within 1px tolerance).

2. **Content not obscured:** Get the document container (`#doc-container` or layout wrapper) `bounding_box()`. Get toolbar `bounding_box()`. Assert that `content.y + content.height <= toolbar.y` (content bottom is at or above toolbar top). This uses Playwright's native `bounding_box()` API — no JS evaluation.

3. **No inline title:** The navigator drawer also shows "Annotation Workspace" text, so this assertion MUST be scoped to the main content area. Use:
   ```python
   expect(page.locator(".text-2xl.font-bold")).to_have_count(0)
   ```
   This checks that no element with the removed title's CSS classes (`text-2xl font-bold`) exists anywhere on the page. The title was the only element with both classes. This is more precise than text matching and avoids false positives from the navigator drawer.

4. **No UUID label:** `expect(page.locator("text=/Workspace: [0-9a-f-]+/")).not_to_be_visible()` — no UUID-format text on the page.

5. **Header row visible (AC2.3):** Verify the workspace header row renders correctly after title removal. The executor MUST inspect `render_workspace_header()` in `src/promptgrimoire/pages/annotation/header.py` to identify the correct locator. Look for a `data-testid` attribute on the header row container or a reliably-labelled button (e.g., export). Use a single committed locator — do not use `.or_()` fallbacks, as they silently degrade to a weaker check if one leg has a typo.

**Testing:**

Follow project TDD patterns. Write the test, run it against the current codebase (with Phases 1-4 applied). All assertions should pass.

**Verification:**

Run: `uv run test-e2e -k test_css_audit`
Expected: Both test functions pass

Run: `uv run test-e2e-changed`
Expected: New test runs and passes

**Commit:** `test: add E2E CSS audit test for bottom toolbar layout`
<!-- END_TASK_1 -->
