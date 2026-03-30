# Lazy Card Rendering Implementation Plan

**Goal:** Reduce annotation card build time from ~450ms to ~70ms by deferring detail section construction and converting header to raw HTML.

**Architecture:** Two-pass card rendering — compact header rendered on build, detail section constructed lazily on first expand. Header static elements rendered as single `ui.html()` call.

**Tech Stack:** NiceGUI (ui.html, ui.card, ui.element), Python 3.14

**Scope:** 3 phases from design (all 3)

**Codebase verified:** 2026-03-30

---

## Acceptance Criteria Coverage

This phase implements and tests:

### lazy-card-rendering-457.AC1: Lazy Detail Section
- **lazy-card-rendering-457.AC1.1 Success:** Detail section not built for collapsed cards on initial load
- **lazy-card-rendering-457.AC1.2 Success:** Detail section built on first expand click
- **lazy-card-rendering-457.AC1.3 Success:** Previously-expanded cards (`expanded_cards`) build detail eagerly
- **lazy-card-rendering-457.AC1.4 Success:** Card diff/rebuild handles lazy detail correctly

---

## Rebuild Path Analysis

The lazy detail design must be correct across ALL paths that create or rebuild cards. This matrix was constructed from codebase investigation:

| # | Path | Trigger | Code path | Cards affected | Lazy detail contract |
|---|------|---------|-----------|---------------|---------------------|
| 1 | Initial load | `document.py:422` | `_refresh_annotation_cards` → `_diff_annotation_cards` (annotation_cards is `{}` from `_init_document_state` at `document.py:233`) | All 190 (diff-add, all "added") | Build detail ONLY for IDs in `expanded_cards`; all others get empty hidden div |
| 2 | Incremental diff | `cards.py:789` triggered by comment add/delete, highlight add/delete, tag apply, CRDT broadcast, tab switch | `_diff_annotation_cards` → `_diff_add_one_card` (new), `_diff_remove_cards` (removed), `_diff_update_changed_cards` (changed) | Only changed/added/removed | New cards: lazy. Changed cards: delete old, build new — if in `expanded_cards`, detail built eagerly. Removed cards: clean up `detail_built_cards`. |
| 3 | Full rebuild | `invalidate_card_cache` (`__init__.py:340`, sets `annotation_cards=None` at line 349) triggered by tag rename/recolour/create/delete | Next `_refresh_annotation_cards` → full build path (`cards.py:793`, clears container, creates all from scratch) | All | `detail_built_cards` MUST be cleared in `invalidate_card_cache`. Full build calls `_build_annotation_card` per highlight — same lazy logic applies. |
| 4 | Tab switch restore | `tab_bar.py:429` restores `annotation_cards` from `DocumentTabState` | `_restore_source_tab_state` restores cards dict; may set `annotation_cards = None` (`tab_bar.py:433`) if tab was never rendered | Varies | If restored from cache: cards already built (detail state preserved in DOM). If set to None: next refresh does full build (same as path 3). |

**Critical E2E contract (from `tests/e2e/card_helpers.py:112-117`):**
After ANY rebuild that triggers epoch advance, the `card-detail` div must exist AND be visible AND contain content for cards in `expanded_cards`. The `add_comment_to_highlight` helper waits for `card-detail` visibility after epoch change, then searches for comment text inside the detail. An empty visible div would cause the text search to fail.

**Design invariant:** The `card-detail` div container is ALWAYS created (empty, hidden) for every card. Only its CONTENTS (from `_build_detail_section`) are deferred. This preserves the `get_by_test_id("card-detail")` locator and `is_visible()` checks in `card_helpers.py:31-32`.

---

## Phase 1: Lazy Detail Section

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add `detail_built_cards` field to PageState and clear in invalidate_card_cache

**Verifies:** None (infrastructure)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/__init__.py` (PageState dataclass, ~line 249; `invalidate_card_cache` method, ~line 340)

**Implementation:**

1. Add `detail_built_cards: set[str]` to PageState after `expanded_cards`:

```python
detail_built_cards: set[str] = field(default_factory=set)  # highlight IDs with detail section built
```

This field is workspace-global (same as `expanded_cards`) because highlight IDs are UUIDs, globally unique within a workspace. No changes to `tab_bar.py` or `DocumentTabState` are needed — `expanded_cards` is also workspace-global and does not appear in tab state save/restore.

2. Clear `detail_built_cards` in `invalidate_card_cache` (rebuild path 3):

```python
def invalidate_card_cache(self) -> None:
    self.annotation_cards = None
    self.card_snapshots = {}
    self.detail_built_cards.clear()  # Add this — lazy detail tracking must reset on full rebuild
    for doc_tab in self.document_tabs.values():
        doc_tab.annotation_cards = {}
        doc_tab.card_snapshots = {}
        if doc_tab.rendered:
            doc_tab.rendered = False
```

**Verification:**
Run: `uv run grimoire test all -x`
Expected: All tests pass (no behavioural change yet)

**Commit:** `refactor: add detail_built_cards tracking field to PageState`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Refactor `_build_annotation_card` to defer detail section

**Verifies:** lazy-card-rendering-457.AC1.1, lazy-card-rendering-457.AC1.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (~lines 446-555)

**Implementation:**

Refactor `_build_annotation_card` to:

1. **Create the detail container div but skip `_build_detail_section`:**
   - Keep the `detail = ui.element("div")...` wrapper creation (preserves `data-testid="card-detail"` locator)
   - Remove the `with detail: _build_detail_section(...)` block
   - The detail div is created empty and hidden — `get_by_test_id("card-detail")` still finds it, `is_visible()` returns False

2. **Extract a helper `_ensure_detail_built`** that:
   - Checks `highlight_id in state.detail_built_cards` — if yes, return immediately (idempotent)
   - Otherwise, builds the detail section inside the detail container using `with detail:`
   - Adds `highlight_id` to `state.detail_built_cards`
   - **Must use `with detail:` context** — `_build_detail_section` and `build_expandable_text` create NiceGUI elements that must attach to the correct container

3. **For pre-expanded cards** (the `if highlight_id in state.expanded_cards:` check at line 524):
   - Call `_ensure_detail_built(state, detail, highlight, card)` BEFORE `detail.set_visibility(True)`
   - This handles AC1.3 and satisfies the E2E contract: visible card-detail must contain content

4. **Modify `toggle_detail`** to call `_ensure_detail_built` before showing:
   - On expand (the `else` branch): call `_ensure_detail_built` before `d.set_visibility(True)`
   - This handles AC1.2

The `_ensure_detail_built` function signature:

```python
def _ensure_detail_built(
    state: PageState,
    detail: ui.element,
    highlight: dict[str, Any],
    card: ui.card,
) -> None:
    """Build the detail section lazily on first expand.

    Idempotent — returns immediately if already built. Must be called
    within the card's NiceGUI slot context (the caller's ``with card:``
    is sufficient; this function uses ``with detail:`` internally).
    """
    highlight_id = highlight.get("id", "")
    if highlight_id in state.detail_built_cards:
        return
    # Derive display values needed by _build_detail_section
    tag_str = highlight.get("tag", "highlight")
    author = highlight.get("author", "Unknown")
    full_text = highlight.get("text", "")
    para_ref = highlight.get("para_ref", "")
    comments: list[dict[str, Any]] = highlight.get("comments", [])
    tag_colours = state.tag_colours()
    color = tag_colours.get(tag_str, "#999999")
    hl_user_id = highlight.get("user_id")
    display_author = anonymise_display_author(author, hl_user_id, state)

    with detail:
        _build_detail_section(
            state,
            highlight_id=highlight_id,
            tag_str=tag_str,
            color=color,
            display_author=display_author,
            para_ref=para_ref,
            full_text=full_text,
            comments=comments,
            card=card,
        )
    state.detail_built_cards.add(highlight_id)
```

**Approach for highlight data in toggle closure:**
Capture the highlight dict in the toggle closure's default args:

```python
def toggle_detail(
    d: ui.element = detail,
    ch: ui.button = chevron,
    hid: str = highlight_id,
    hl: dict[str, Any] = highlight,
    crd: ui.card = card,
) -> None:
    if d.visible:
        d.set_visibility(False)
        ch.props('icon="expand_more"')
        state.expanded_cards.discard(hid)
    else:
        _ensure_detail_built(state, d, hl, crd)
        d.set_visibility(True)
        ch.props('icon="expand_less"')
        state.expanded_cards.add(hid)
    ui.run_javascript(
        "if (window._positionCards)"
        " requestAnimationFrame(window._positionCards)"
    )
```

**Verification:**
Run: `uv run grimoire test all -x`
Expected: All tests pass

**Commit:** `perf: defer detail section build to first expand (#457)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Handle lazy detail across all rebuild paths

**Verifies:** lazy-card-rendering-457.AC1.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (3 functions: `_diff_remove_cards`, `_diff_update_changed_cards`, `_refresh_annotation_cards` full-build path)

**Implementation:**

Three rebuild paths need `detail_built_cards` maintenance:

**Path 2 — `_diff_remove_cards` (cards.py ~line 630):**
Clean up `detail_built_cards` when removing cards:

```python
def _diff_remove_cards(state: PageState, removed_ids: set[str]) -> bool:
    cards = state.annotation_cards
    if cards is None:
        return False
    changed = False
    for removed_id in removed_ids:
        card = cards.pop(removed_id)
        card.delete()
        state.expanded_cards.discard(removed_id)
        state.detail_built_cards.discard(removed_id)  # Add this line
        state.card_snapshots.pop(removed_id, None)
        changed = True
    return changed
```

**Path 2/4 — `_diff_update_changed_cards` (cards.py ~line 667):**
When a card is rebuilt due to snapshot change, reset its detail tracking:

```python
if old_snap != new_snap:
    old_card = cards[hl_id]
    old_card.delete()
    state.detail_built_cards.discard(hl_id)  # Reset lazy-build tracking
    new_card = _build_annotation_card(state, hl)
    # ... rest unchanged
```

The rebuilt card's `_build_annotation_card` will call `_ensure_detail_built` eagerly if `hl_id in state.expanded_cards` (from Task 2's AC1.3 handling). This satisfies the E2E contract: after rebuild, expanded cards have populated detail sections.

**Path 3 — `_refresh_annotation_cards` full-build path (cards.py ~line 793):**
The full-build path clears `annotation_cards` and rebuilds all cards via `container.clear()`. Add `detail_built_cards.clear()` before the rebuild:

```python
# First render — full build
state.annotation_cards = {}
state.detail_built_cards.clear()  # Add this — full rebuild resets all lazy tracking

# Wrap the entire rebuild in ``with container`` ...
with state.annotations_container:
    state.annotations_container.clear()
    # ... existing full-build code ...
```

Note: `invalidate_card_cache` (Task 1) already clears `detail_built_cards`, but the full-build path should also clear it defensively — the full-build can also be reached on first render when `annotation_cards` starts as `None` (e.g., from `tab_bar.py:461`).

**Testing:**

Write a NiceGUI UI integration test in `tests/integration/test_lazy_card_detail.py` with marker `@pytest.mark.nicegui_ui`. Use `tests/integration/test_event_loop_render_lag.py` as the model for fixture imports and the `nicegui_user` fixture pattern:

Tests must verify across rebuild paths:
- **AC1.1 (initial load):** Load page with 2 highlights. Verify `card-detail` div exists but detail-specific children (`tag-select`, `comment-input`) do NOT exist on either card.
- **AC1.2 (first expand):** Expand card 0. Verify `tag-select` and/or `comment-input` now exist inside card 0's detail. Card 1's detail still has no children.
- **AC1.3 (pre-expanded restore):** Add card 0's ID to `expanded_cards` before page load. Verify card 0's detail is visible AND populated on load.
- **AC1.4 (diff rebuild):** With card 0 expanded, modify its tag via CRDT (triggers snapshot change → `_diff_update_changed_cards`). Verify: rebuilt card 0 still has detail visible and populated. Card 1 still has empty detail.
- **AC1.4 (full rebuild):** Call `invalidate_card_cache` then `refresh_annotations`. Verify: previously-expanded card's detail is rebuilt and visible. Collapsed card's detail is empty.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_lazy_card_detail.py -s`
Run: `uv run grimoire test all -x`
Expected: All tests pass

**Implementation note:** As part of this task, `_diff_annotation_cards` was structurally decomposed into the `_CardDiff` dataclass plus four focused helpers: `_compute_card_diff`, `_diff_remove_cards`, `_diff_add_one_card`, and `_diff_update_changed_cards`. This decomposition was not in the original plan but emerged naturally from the refactor — the helpers made it straightforward to maintain `detail_built_cards` in each rebuild path without entangling the logic.

**Commit:** `perf: handle lazy detail across all rebuild paths (#457)`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->
