# Word Count with Configurable Limits Implementation Plan

**Goal:** Word count badge appears in the annotation header and updates live as students type.

**Architecture:** Word limit values cached on PageState from PlacementContext during init. Badge rendered in header row alongside save_status and user_count_badge. word_count() called in Yjs handler after _sync_markdown_to_crdt(), badge text and colour updated via server-push.

**Tech Stack:** NiceGUI (ui.label, server-push), word_count module from Phase 1

**Scope:** 6 phases from original design (phase 4 of 6)

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### word-count-limits-47.AC4: Header badge display
- **word-count-limits-47.AC4.1 Success:** Badge visible in header bar on all tabs when limits configured
- **word-count-limits-47.AC4.2 Success:** Badge hidden when no limits configured on the activity
- **word-count-limits-47.AC4.3 Success:** Badge shows neutral style: "Words: 1,234 / 1,500"
- **word-count-limits-47.AC4.4 Success:** Badge shows amber at 90%+ of max: "Words: 1,380 / 1,500 (approaching limit)"
- **word-count-limits-47.AC4.5 Success:** Badge shows red at 100%+ of max: "Words: 1,567 / 1,500 (over limit)"
- **word-count-limits-47.AC4.6 Success:** Badge shows red below minimum: "Words: 234 / 500 minimum (below minimum)"
- **word-count-limits-47.AC4.7 Success:** Badge updates live as student types (after Yjs sync)
- **word-count-limits-47.AC4.8 Edge:** Min-only activity shows "Words: 612 / 500 minimum" in neutral when met

---

<!-- START_TASK_1 -->
### Task 1: Add word count fields to PageState

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/__init__.py` (PageState dataclass, lines 178-252)

**Implementation:**

Add to PageState (after existing UI element fields around line 211):

```python
# Word count limits (populated from PlacementContext during init)
word_minimum: int | None = None
word_limit: int | None = None
word_limit_enforcement: bool = False
word_count_badge: ui.label | None = None
```

These fields are populated from PlacementContext during workspace initialisation, matching the existing pattern where `can_annotate`, `can_upload`, etc. are resolved once.

**Testing:**

Unit test verifying PageState accepts the new fields with defaults.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add word count fields to PageState`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Populate PageState word fields from PlacementContext

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (around line 327-347, _resolve_workspace_context)

**Implementation:**

In `_resolve_workspace_context()`, after resolving PlacementContext (line 327), populate PageState with word limit values:

```python
ctx = await get_placement_context(workspace_id)
# ... existing permission resolution ...
state = PageState(
    # ... existing fields ...
    word_minimum=ctx.word_minimum,
    word_limit=ctx.word_limit,
    word_limit_enforcement=ctx.word_limit_enforcement,
)
```

**Testing:**

Integration test (requires DB): create Activity with word_limit=500, resolve workspace context, verify PageState has word_limit=500.

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass.

**Commit:** `feat: populate PageState word fields from PlacementContext`
<!-- END_TASK_2 -->

<!-- START_SUBCOMPONENT_A (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Create word count badge formatting helper

**Verifies:** word-count-limits-47.AC4.3, word-count-limits-47.AC4.4, word-count-limits-47.AC4.5, word-count-limits-47.AC4.6, word-count-limits-47.AC4.8

**Files:**
- Create: `src/promptgrimoire/pages/annotation/word_count_badge.py`
- Test: `tests/unit/test_word_count_badge.py` (unit)

**Implementation:**

Pure function module for badge text and style computation:

```python
@dataclass(frozen=True)
class BadgeState:
    text: str
    css_classes: str
```

`format_word_count_badge(count: int, word_minimum: int | None, word_limit: int | None) -> BadgeState`:

Logic:
1. Build display text with comma-formatted count: `f"Words: {count:,}"`
2. If word_limit is set:
   - Append ` / {word_limit:,}`
   - If count >= word_limit: append ` (over limit)`, red styling
   - Elif count >= word_limit * 0.9: append ` (approaching limit)`, amber styling
   - Else: neutral styling
3. If word_minimum is set and word_limit is not:
   - Append ` / {word_minimum:,} minimum`
   - If count < word_minimum: append ` (below minimum)`, red styling
   - Else: neutral styling
4. If both word_minimum and word_limit:
   - Append ` / {word_limit:,}`
   - Red if count >= word_limit or count < word_minimum
   - Amber if count >= word_limit * 0.9
   - Else neutral
   - Adjust text suffix accordingly

CSS classes:
- Neutral: `text-sm text-gray-600 bg-gray-100 px-2 py-0.5 rounded`
- Amber: `text-sm text-amber-800 bg-amber-100 px-2 py-0.5 rounded`
- Red: `text-sm text-red-800 bg-red-100 px-2 py-0.5 rounded`

**Testing:**

Tests must verify each AC case:
- AC4.3: count=1234, limit=1500 → text="Words: 1,234 / 1,500", neutral classes
- AC4.4: count=1380, limit=1500 → text includes "(approaching limit)", amber classes
- AC4.5: count=1567, limit=1500 → text includes "(over limit)", red classes
- AC4.6: count=234, minimum=500 → text includes "(below minimum)", red classes
- AC4.8: count=612, minimum=500, no limit → text="Words: 612 / 500 minimum", neutral classes

Use `@pytest.mark.parametrize` for all cases. This is a pure function — no async, no DB.

**Verification:**

Run: `uv run pytest tests/unit/test_word_count_badge.py -v`
Expected: All tests pass.

**Commit:** `feat: add word count badge formatting with colour thresholds`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Tests for badge edge cases

**Verifies:** word-count-limits-47.AC4.2, word-count-limits-47.AC4.8

**Files:**
- Modify: `tests/unit/test_word_count_badge.py`

**Testing:**

Additional parametrised cases:
- count=0, limit=1500 → "Words: 0 / 1,500 (below minimum)" if minimum also set, or just "Words: 0 / 1,500" if no minimum
- count=0, no limits → should not be called (badge hidden), but handle gracefully
- count=1500, limit=1500 → "(over limit)" — exactly at limit counts as over
- count=1350, limit=1500 → exactly at 90% threshold → amber
- count=1349, limit=1500 → just below 90% → neutral
- Both min and max violated simultaneously: count=50, minimum=100, limit=500

**Verification:**

Run: `uv run pytest tests/unit/test_word_count_badge.py -v`
Expected: All tests pass.

**Commit:** `test: add word count badge edge cases`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Tests for badge with both min and max limits

**Verifies:** word-count-limits-47.AC4.3, word-count-limits-47.AC4.6

**Files:**
- Modify: `tests/unit/test_word_count_badge.py`

**Testing:**

Cases where both word_minimum and word_limit are set:
- count=50, min=100, limit=500 → below minimum, red
- count=150, min=100, limit=500 → within range, neutral
- count=460, min=100, limit=500 → approaching limit (90%+), amber
- count=550, min=100, limit=500 → over limit, red

**Verification:**

Run: `uv run pytest tests/unit/test_word_count_badge.py -v`
Expected: All tests pass.

**Commit:** `test: add badge tests for combined min+max limits`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_6 -->
### Task 6: Render word count badge in header

**Verifies:** word-count-limits-47.AC4.1, word-count-limits-47.AC4.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/header.py` (lines 164-179, badge area)

**Implementation:**

In `render_workspace_header()`, after creating `user_count_badge` and before the export button, conditionally create the word count badge:

```python
# Only show badge when limits are configured
if state.word_minimum is not None or state.word_limit is not None:
    badge_state = format_word_count_badge(0, state.word_minimum, state.word_limit)
    state.word_count_badge = (
        ui.label(badge_state.text)
        .classes(badge_state.css_classes)
        .props('data-testid="word-count-badge"')
    )
```

The badge starts at count=0 and will be updated by the Yjs handler.

Import `format_word_count_badge` from `promptgrimoire.pages.annotation.word_count_badge`.

**Testing:**

AC4.1 and AC4.2 verified in Phase 6 E2E.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: render word count badge in annotation header`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Wire word count update into Yjs handler

**Verifies:** word-count-limits-47.AC4.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (lines 350-396, _setup_yjs_event_handler)

**Implementation:**

Add `state: PageState` parameter to `_setup_yjs_event_handler()`.

In the `on_yjs_update` async closure, after `_sync_markdown_to_crdt()` at line 387 and before `mark_dirty_workspace()`:

First, add module-level imports at the top of `respond.py` (do NOT use lazy imports inside the handler — this callback runs on every keystroke):

```python
from promptgrimoire.word_count import word_count
from promptgrimoire.pages.annotation.word_count_badge import format_word_count_badge
```

Then in the handler, after `_sync_markdown_to_crdt()`:

```python
await _sync_markdown_to_crdt(crdt_doc, workspace_key, client_id)

# Update word count badge if limits configured
if state.word_count_badge is not None:
    markdown = str(crdt_doc.response_draft_markdown)
    count = word_count(markdown)
    badge_state = format_word_count_badge(count, state.word_minimum, state.word_limit)
    state.word_count_badge.set_text(badge_state.text)
    state.word_count_badge.classes(badge_state.css_classes, replace="text-sm *")
```

Update the call site that invokes `_setup_yjs_event_handler()` to pass `state`.

**Testing:**

AC4.7 verified in Phase 6 E2E. For unit testing, the badge formatting is already tested in task 3-5. The wiring is tested by verifying the handler has the right signature.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

Run: `uv run test-changed`
Expected: All tests pass.

**Commit:** `feat: wire word count update into Yjs event handler`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Final verification

**Files:**
- All files from this phase

**Step 1: Run full test suite**

Run: `uv run test-changed`
Expected: All tests pass, no regressions.

**Step 2: Run linting and type checking**

Run: `uv run ruff check src/promptgrimoire/pages/annotation/`
Expected: No lint errors.

Run: `uvx ty check`
Expected: No type errors.

**Step 3: Verify commit history**

Run: `git log --oneline -8`
Expected: Clean commit history with conventional prefixes.
<!-- END_TASK_8 -->
