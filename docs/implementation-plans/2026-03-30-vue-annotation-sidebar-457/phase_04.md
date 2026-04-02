# Vue Annotation Sidebar Implementation Plan — Phase 4

**Goal:** Full compact header rendering from items prop, with no interactivity. Items serialisation as a pure function.

**Architecture:** Pure Python serialisation function transforms CRDT highlight state + tag info + permissions into a flat `list[dict]` pushed as the `items` prop. Vue component renders compact headers from this data. No interactivity yet — Phase 6+ adds event handling.

**Tech Stack:** NiceGUI 3.9.0, Vue 3, Python 3.14, pycrdt

**Scope:** Phase 4 of 10 from original design

**Codebase verified:** 2026-03-30

**Status: COMPLETED (2026-04-02).** All unit and integration tests pass.

**Deviations from plan (2026-04-02):**

1. **`anonymise_author()` called directly instead of `anonymise_display_author()`.** Plan specified `anonymise_display_author()` from `card_shared.py`, but that function wraps `anonymise_author()` with `PageState` coupling. Since `serialise_items()` is a pure function (functional core, no `PageState`), the implementation calls `anonymise_author()` from `auth/anonymise.py` directly with explicit parameters. This is architecturally correct — the pure function should not depend on a NiceGUI-coupled wrapper.

2. **Compact header comment badge testid renamed to `comment-count-badge`.** Plan specified `data-testid="comment-count"` for both the compact header badge and the detail section count. Code review identified this as an ambiguity violation (two sibling DOM nodes with the same testid within one card). Header badge renamed to `comment-count-badge`; detail section retains `comment-count`.

3. **Integration tests validate prop data contract, not rendered DOM.** Same limitation as Phase 3: NiceGUI `user_simulation` has no Vue runtime. Tests verify that `refresh_items()` produces correct `_props["items"]` data and that the JS template structurally contains the required `data-testid` attributes. Full DOM rendering validated by Phase 10 cross-tab E2E.

4. **`expanded_ids` not pushed in `refresh_items()`.** Plan says to push `expanded_ids` prop, but `refresh_items()` has no `expanded_ids` parameter — expansion state is managed separately from highlight data. The prop is set in the constructor and updated independently. Not a defect.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### vue-annotation-sidebar-457.AC2: DOM Contract
- **vue-annotation-sidebar-457.AC2.1 Success:** Cards have `data-testid="annotation-card"`, `data-highlight-id`, `data-start-char`, `data-end-char`
- **vue-annotation-sidebar-457.AC2.2 Success:** Detail section has `data-testid` for `card-detail`, `tag-select`, `comment-input`, `post-comment-btn`, `comment-count`

Note: AC2.2 detail section `data-testid` values are placed in the template in this phase but only become visible after Phase 6 (expand/collapse). This phase validates the compact header DOM contract.

---

## Reference Files

**Read before starting:**
- `src/promptgrimoire/pages/annotation/cards.py` — current card building (`_snapshot_highlight`, `_render_compact_header_html`, `_build_compact_header`)
- `src/promptgrimoire/pages/annotation/card_shared.py` — `author_initials()`, `anonymise_display_author()`
- `src/promptgrimoire/crdt/annotation_doc.py` — `get_highlight()`, `get_all_highlights()`, `get_highlights_for_document()` return shapes
- `src/promptgrimoire/pages/annotation/__init__.py:207-345` — PageState dataclass
- `src/promptgrimoire/pages/annotation/tags.py:26-41` — TagInfo dataclass
- `src/promptgrimoire/pages/annotation/sidebar.py` — from Phase 3
- `src/promptgrimoire/static/annotation-sidebar.js` — from Phase 3
- CLAUDE.md — project conventions

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create items serialisation pure function

**Verifies:** Supports vue-annotation-sidebar-457.AC2.1 (provides data for DOM attributes)

**Files:**
- Create: `src/promptgrimoire/pages/annotation/items_serialise.py`

**Implementation:**

Create a pure function `serialise_items()` — **functional core**, no NiceGUI imports, no side effects.

**Function signature:**
```python
def serialise_items(
    highlights: list[dict[str, Any]],
    tag_info_map: dict[str, TagInfo],
    tag_colours: dict[str, str],
    user_id: str | None,
    viewer_is_privileged: bool,
    privileged_user_ids: frozenset[str],
    can_annotate: bool,
    anonymous_sharing: bool,
) -> list[dict[str, Any]]:
```

**Each returned item dict:**
```python
{
    "id": str,                    # highlight UUID
    "tag_key": str,               # raw tag UUID
    "tag_display": str,           # human-readable tag name or "⚠ recovered"
    "color": str,                 # hex colour, default "#999999"
    "start_char": int,
    "end_char": int,
    "para_ref": str,              # may be ""
    "author": str,                # raw author from CRDT
    "display_author": str,        # anonymised display name
    "initials": str,              # from author_initials(display_author)
    "user_id": str | None,
    "can_delete": bool,           # viewer can delete this highlight
    "text": str,                  # full highlighted text
    "text_preview": str,          # truncated to 80 chars with "..." if needed
    "comments": [
        {"id": str, "author": str, "text": str, "created_at": str, "can_delete": bool}
    ],
}
```

**Key logic:**
- Tag display: `tag_info_map[tag_key].name` — missing = `"⚠ recovered"`
- Colour: `tag_colours.get(tag_key, "#999999")`
- Author: `anonymise_display_author()` from `card_shared.py`
- `can_delete` (highlight): `user_id == viewer_user_id` OR `viewer_is_privileged`
- `can_delete` (comment): `comment.user_id == viewer_user_id` OR `viewer_is_privileged`
- Comments sorted by `created_at`
- Text preview: if len > 80, truncate to 80 + "..."

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/items_serialise.py`
Expected: No type errors

**Commit:** `feat(annotation): add items serialisation pure function for Vue sidebar (#457)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for items serialisation

**Verifies:** vue-annotation-sidebar-457.AC2.1

**Files:**
- Create: `tests/unit/test_items_serialise.py`

**Testing:**
Cases:
- Basic serialisation: 2 highlights → correct fields, tag_display, color
- Comment serialisation: sorted by created_at, per-comment can_delete
- Author anonymisation: display_author and initials derived correctly
- Permission can_delete (highlight): own=True, other's non-privileged=False, privileged=True
- Permission can_delete (comment): own=True, other's non-privileged=False, privileged=True
- Deleted tag: tag_key not in tag_info_map → `"⚠ recovered"`, `"#999999"`
- Empty para_ref → `""`
- Text preview: short < 80 chars, long > 80 chars truncated

**Verification:**
Run: `uv run grimoire test run tests/unit/test_items_serialise.py`
Expected: All tests pass

**Commit:** `test(annotation): add unit tests for items serialisation (#457)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Expand sidebar.py to use serialise_items and pass props

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/sidebar.py` (from Phase 3)

**Implementation:**

Extend `AnnotationSidebar` to:
- Accept data for serialisation in constructor or `refresh_items()` method
- Call `serialise_items()` to build items list
- Push as `self._props['items']` + `self.update()`
- Also push `tag_options` prop (`dict[str, str]` — `tag_key → display_name`)
- Also push `permissions` prop (`{"can_annotate": bool}`)
- Also push `expanded_ids` prop (list of expanded card IDs)

`refresh_items()` callable from broadcast handlers for prop updates after CRDT mutations.

**Verification:**
Run: `uvx ty@0.0.24 check src/promptgrimoire/pages/annotation/sidebar.py`
Expected: No type errors

**Commit:** `feat(annotation): wire items serialisation into AnnotationSidebar (#457)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Expand Vue component to render compact headers

**Verifies:** vue-annotation-sidebar-457.AC2.1, vue-annotation-sidebar-457.AC2.2

**Files:**
- Modify: `src/promptgrimoire/static/annotation-sidebar.js` (from Phase 3)

**Implementation:**

Replace minimal spike template with full compact header. Each card:

**Card wrapper:**
- `v-for="item in items" :key="item.id"`
- `data-testid="annotation-card"`, `:data-highlight-id`, `:data-start-char`, `:data-end-char`
- `style="position: absolute"` (positioning in Phase 5)

**Compact header elements:**
1. Colour dot — 8×8px circle, `:style="{ backgroundColor: item.color }"`
2. Tag label — `{{ item.tag_display }}`, colour matches dot, max-width 100px
3. Initials — `{{ item.initials }}`, grey
4. Para ref (conditional) — `v-if="item.para_ref"`
5. Comment count badge (conditional) — `v-if="item.comments.length > 0"`, `data-testid="comment-count"`
6. Spacer (flex-grow: 1)
7. Chevron button (placeholder, Phase 6)
8. Locate button (placeholder, Phase 8)
9. Delete button (conditional) — `v-if="item.can_delete"` (placeholder, Phase 7)

**Detail section (collapsed):**
- `<div data-testid="card-detail" v-show="false">` (Phase 6 wires expand)
- Placeholders: `tag-select`, `comment-input`, `post-comment-btn`, `comment-count`

**Epoch sync:**
- `watch` on `items` with `{ flush: 'post' }` (or `$nextTick` in Options API)
- Increments `window.__annotationCardsEpoch` (always)
- If `props.doc_container_id` is defined, also sets `window.__cardEpochs[props.doc_container_id]`
- Note: `doc_container_id` prop is added in Phase 5 Task 4; at this stage it may be undefined, so guard the per-doc epoch with a conditional

**Commit:** `feat(annotation): Vue compact header rendering with DOM contract (#457)`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Integration test for compact header DOM contract

**Verifies:** vue-annotation-sidebar-457.AC2.1, vue-annotation-sidebar-457.AC2.2

**Files:**
- Create: `tests/integration/test_vue_sidebar_dom_contract.py`

**Testing:**
NiceGUI integration test (`@pytest.mark.nicegui_ui`).

Cases:
- AC2.1: 3 items with different tags → each card has correct `data-testid`, `data-highlight-id`, `data-start-char`, `data-end-char`
- AC2.2: detail section elements have correct `data-testid` values (hidden but present)
- Comment badge: card with 2 comments shows badge "2"; 0 comments → no badge
- Para ref: present → shown; absent → not shown
- Tag recovery: deleted tag → "⚠ recovered"

**Verification:**
Run: `uv run grimoire test run tests/integration/test_vue_sidebar_dom_contract.py`
Expected: All tests pass

**Commit:** `test(annotation): integration test for Vue sidebar DOM contract (#457)`
<!-- END_TASK_5 -->
