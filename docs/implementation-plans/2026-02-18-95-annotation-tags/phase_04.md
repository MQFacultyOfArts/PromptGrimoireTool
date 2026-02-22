# Annotation Tag Configuration — Phase 4: Annotation Page Integration

**Goal:** Replace `BriefTag` enum throughout the annotation page with DB-backed dynamic tags using the existing `TagInfo` abstraction.

**Architecture:** The three-tab-ui design introduced `TagInfo` as a deliberate seam point. `organise.py` and `respond.py` already use `TagInfo` exclusively (never `BriefTag`). This phase replaces the single coupling point (`brief_tags_to_tag_info()` in `tags.py`) with a DB query, then migrates the remaining BriefTag consumers (`css.py`, `document.py`, `highlights.py`, `cards.py`, `pdf_export.py`) to use `TagInfo`/colour dict lookups. Finally, `BriefTag`, `TAG_COLORS`, and `TAG_SHORTCUTS` are deleted from the codebase.

**Tech Stack:** SQLModel, NiceGUI, pycrdt

**Scope:** Phase 4 of 6 from original design

**Codebase verified:** 2026-02-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 95-annotation-tags.AC5: Annotation page integration
- **95-annotation-tags.AC5.1 Success:** Tag toolbar renders from DB-backed tag list, not BriefTag enum
- **95-annotation-tags.AC5.2 Success:** Keyboard shortcuts 1-0 map positionally to the first 10 tags in order
- **95-annotation-tags.AC5.3 Success:** Highlight cards display color from DB-backed tag data
- **95-annotation-tags.AC5.4 Success:** Tag dropdown on highlight cards lists all workspace tags
- **95-annotation-tags.AC5.5 Success:** Organise tab renders one column per tag (no untagged column)
- **95-annotation-tags.AC5.6 Success:** Respond tab renders tag-grouped highlights from DB-backed tags
- **95-annotation-tags.AC5.7 Success:** PDF export uses tag colors from DB
- **95-annotation-tags.AC5.8 Success:** Creating a highlight requires selecting a tag (no untagged highlights)
- **95-annotation-tags.AC5.9 Success:** Tag buttons truncate with ellipsis; full name shown on hover tooltip
- **95-annotation-tags.AC5.10 Success:** Tag toolbar wraps to two rows when needed (no horizontal scroll)
- **95-annotation-tags.AC5.11 Success:** `BriefTag`, `TAG_COLORS`, `TAG_SHORTCUTS` are deleted from codebase

---

## Key Files Reference

These files contain patterns to follow. Read them before implementing:

- `src/promptgrimoire/pages/annotation/tags.py` — `TagInfo` dataclass and `brief_tags_to_tag_info()` (the function to replace)
- `src/promptgrimoire/pages/annotation/__init__.py:165-214` — `PageState` dataclass with `tag_info_list` field
- `src/promptgrimoire/pages/annotation/workspace.py:537-559` — the two call sites for `brief_tags_to_tag_info()`
- `src/promptgrimoire/pages/annotation/css.py:216-318` — `_get_tag_color()`, `_build_highlight_pseudo_css()`, `_setup_page_styles()`, `_build_tag_toolbar()`
- `src/promptgrimoire/pages/annotation/document.py:66-134` — keyboard handler, `handle_tag_click`, toolbar wiring
- `src/promptgrimoire/pages/annotation/highlights.py:139-154` — `_update_highlight_css()` (calls `_build_highlight_pseudo_css`)
- `src/promptgrimoire/pages/annotation/highlights.py:187-246` — `_add_highlight()` (currently takes `BriefTag | None`)
- `src/promptgrimoire/pages/annotation/cards.py:140-199` — colour lookup and tag dropdown from `BriefTag`
- `src/promptgrimoire/pages/annotation/pdf_export.py:47-48` — `tag_colours` dict from `TAG_COLORS`
- `src/promptgrimoire/models/case.py:12-53` — `BriefTag`, `TAG_COLORS`, `TAG_SHORTCUTS` (to delete)
- `src/promptgrimoire/models/__init__.py` — exports `BriefTag`, `TAG_COLORS`, `TAG_SHORTCUTS` (to clean up)
- `tests/integration/conftest.py:34-46` — hardcoded `TAG_COLOURS` dict (to update)
- `docs/testing.md` — testing guidelines
- `CLAUDE.md` — async fixture rule, project conventions

---

**Note on legacy CRDT data:** Existing workspaces created before this phase may have CRDT highlights referencing BriefTag value strings (e.g. `"jurisdiction"`) rather than Tag UUID strings. After this phase, the CSS `::highlight()` rules are generated from workspace tags only (UUID-keyed). Highlights with legacy BriefTag strings will render as plain text (no highlight styling) until re-tagged. This is acceptable for the Session 1 2026 deployment timeline — no pre-existing student workspaces need preservation.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Replace brief_tags_to_tag_info() with async workspace_tags() DB query

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tags.py`

**Implementation:**

Replace the entire body of `tags.py`. The module retains its role as the single coupling point between the DB-backed tag system and the annotation page rendering code.

1. Remove the `from promptgrimoire.models.case import TAG_COLORS, BriefTag` import.

2. Add import: `from uuid import UUID`

3. Keep the `TagInfo` dataclass unchanged (frozen, slots, same three fields: `name`, `colour`, `raw_key`).

4. Replace `brief_tags_to_tag_info()` with:
   ```python
   async def workspace_tags(workspace_id: UUID) -> list[TagInfo]:
       """Load tags for a workspace from the database.

       Returns TagInfo instances ordered by order_index, with raw_key set to
       the Tag UUID string for use as CRDT highlight tag identifiers.
       """
       from promptgrimoire.db.tags import list_tags_for_workspace

       tags = await list_tags_for_workspace(workspace_id)
       return [
           TagInfo(
               name=tag.name,
               colour=tag.color,
               raw_key=str(tag.id),
           )
           for tag in tags
       ]
   ```

   Uses a lazy import from `db.tags` (same pattern as `crdt/annotation_doc.py:571` — lazy import to avoid circular dependency between `pages/annotation/` and `db/`).

5. Update the module docstring to reflect the change — no longer references BriefTag, now references DB-backed tag query.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: replace brief_tags_to_tag_info() with async workspace_tags() DB query`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Populate PageState.tag_info_list from DB at workspace load

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py`

**Implementation:**

1. Update the import at line 53: change `from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info` to `from promptgrimoire.pages.annotation.tags import workspace_tags`.

2. At line 537-538, the `_render_organise_now()` function currently does:
   ```python
   if state.tag_info_list is None:
       state.tag_info_list = brief_tags_to_tag_info()
   ```
   Change to:
   ```python
   if state.tag_info_list is None:
       return  # Tags not loaded yet — skip render
   ```
   The `tag_info_list` should already be populated by the workspace load path (see step 3 below). If it's still None, the organise tab simply doesn't render yet.

3. At line 559, the respond tab init does:
   ```python
   tags = state.tag_info_list or brief_tags_to_tag_info()
   ```
   Change to:
   ```python
   tags = state.tag_info_list or []
   ```
   If tags aren't loaded yet, the respond tab gets an empty list (graceful degradation).

4. Find the workspace loading path — the function that sets up `PageState` for a workspace. `state.tag_info_list` must be populated early, before any tab rendering. Add:
   ```python
   state.tag_info_list = await workspace_tags(workspace_id)
   ```
   This goes in the workspace initialization code, after the workspace is loaded but before tabs are built. Look for where `PageState(workspace_id=...)` is constructed and the document is loaded — add the `workspace_tags()` call there.

5. Remove the `brief_tags_to_tag_info` import (no longer used in this file).

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: populate tag_info_list from DB at workspace load`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Update CSS infrastructure to use tag colour dict

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/css.py`
- Modify: `src/promptgrimoire/pages/annotation/highlights.py`

**Implementation:**

**In `css.py`:**

1. Remove the import at line 13: `from promptgrimoire.models.case import TAG_COLORS, TAG_SHORTCUTS, BriefTag`. Replace with: `from promptgrimoire.pages.annotation.tags import TagInfo` (needed for `_build_tag_toolbar` in Task 4, but add it now).

2. Replace `_get_tag_color()` (lines 216-222) with a version that takes a colour dict:
   ```python
   def _get_tag_color(tag_str: str, tag_colours: dict[str, str]) -> str:
       """Get hex color for a tag string from the workspace colour mapping."""
       return tag_colours.get(tag_str, "#999999")
   ```

3. Update `_build_highlight_pseudo_css()` (lines 225-272) signature:
   - Change from `def _build_highlight_pseudo_css(tags: set[str] | None = None) -> str:` to `def _build_highlight_pseudo_css(tag_colours: dict[str, str]) -> str:`
   - Replace the body: instead of iterating BriefTag or a `tags` set and calling `_get_tag_color(tag_str)`, iterate `tag_colours.items()` directly:
     ```python
     css_rules: list[str] = []
     for tag_str, hex_color in tag_colours.items():
         r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
         bg_rgba = f"rgba({r}, {g}, {b}, 0.4)"
         css_rules.append(
             f"::highlight(hl-{tag_str}) {{\n"
             f"    background-color: {bg_rgba};\n"
             f"    text-decoration: underline;\n"
             f"    text-decoration-color: {hex_color};\n"
             f"}}"
         )
     ```
   - Keep the hover and throb highlight rules at the end (they're tag-independent).

4. Update `_setup_page_styles()` (lines 275-283):
   - Remove the `TAG_COLORS`-based custom color registration (the `ui.colors(...)` calls that registered named colors from BriefTag). Keep the signature as `def _setup_page_styles() -> None:` — no `tag_info_list` parameter needed. Task 4 will use inline styles on toolbar buttons instead of NiceGUI named colors, so custom color registration is unnecessary.
   - The function should reduce to just `ui.add_css(_PAGE_CSS)` (the static page-level CSS rules).

**In `highlights.py`:**

5. Remove the `TYPE_CHECKING` block (lines 24-25) that imports `BriefTag` — it's no longer used.

6. Update `_update_highlight_css()` (lines 139-158) to build a colour dict from `state.tag_info_list` and pass it to `_build_highlight_pseudo_css()`:
   ```python
   def _update_highlight_css(state: PageState) -> None:
       if state.highlight_style is None or state.crdt_doc is None:
           return

       tag_colours = {ti.raw_key: ti.colour for ti in (state.tag_info_list or [])}
       css = _build_highlight_pseudo_css(tag_colours)
       state.highlight_style._props["innerHTML"] = css
       state.highlight_style.update()

       _push_highlights_to_client(state)
   ```

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `refactor: CSS infrastructure uses tag colour dict instead of BriefTag`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update toolbar, keyboard handler, and highlight creation

**Verifies:** 95-annotation-tags.AC5.1, 95-annotation-tags.AC5.2, 95-annotation-tags.AC5.8, 95-annotation-tags.AC5.9, 95-annotation-tags.AC5.10

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/css.py`
- Modify: `src/promptgrimoire/pages/annotation/document.py`
- Modify: `src/promptgrimoire/pages/annotation/highlights.py`

**Implementation:**

**In `__init__.py` — add toolbar container to PageState:**

0. Add `toolbar_container: Any = None` field to `PageState` (after `tag_info_list`, line ~200). This stores a reference to the toolbar `ui.row()` element so Phase 5 can clear and rebuild the toolbar after tag management changes.

**In `css.py` — update `_build_tag_toolbar()` (lines 286-317):**

1. Change the signature from `def _build_tag_toolbar(on_tag_click: Any) -> None:` to `def _build_tag_toolbar(tag_info_list: list[TagInfo], on_tag_click: Any) -> Any:`. The function must return the toolbar `ui.row()` element (for storing in `state.toolbar_container` — used by Phase 5 for toolbar rebuild). Add `return` for the outer `ui.row()` element at the end of the function.

2. Replace the `for i, tag in enumerate(BriefTag):` loop (lines 304-317) with iteration over `tag_info_list`:
   ```python
   for i, ti in enumerate(tag_info_list):
       shortcut = str((i + 1) % 10) if i < 10 else ""  # 1-9, 0 for 10th
       label = f"[{shortcut}] {ti.name}" if shortcut else ti.name

       async def apply_tag(tag_key: str = ti.raw_key) -> None:
           await on_tag_click(tag_key)

       btn = ui.button(label, on_click=apply_tag).classes("text-xs compact-btn")
       btn.style(f"background-color: {ti.colour}; color: white; max-width: 160px; "
                 "overflow: hidden; text-overflow: ellipsis; white-space: nowrap;")
       btn.tooltip(ti.name)
   ```
   - AC5.9: `max-width` + `text-overflow: ellipsis` for truncation, `.tooltip()` for full name on hover.
   - AC5.10: The existing `tag-toolbar-compact` CSS class with `flex-wrap: wrap` handles wrapping (verify this class exists in `_PAGE_CSS`; if not, add `flex-wrap: wrap` to the toolbar row).
   - Note: Remove the `color_name = tag.value.replace("_", "-")` and NiceGUI named-color approach. Instead, use inline `style` for the button background colour directly from `ti.colour`. Task 3 already simplified `_setup_page_styles()` to just `ui.add_css(_PAGE_CSS)` — no changes to that function needed here.

**In `document.py` — update keyboard handler and toolbar wiring (lines 1-134):**

4. Remove the import at line 14: `from promptgrimoire.models.case import TAG_SHORTCUTS, BriefTag`.

5. Update the keyboard handler `on_keydown` (lines 67-73):
   ```python
   async def on_keydown(e: Any) -> None:
       key = e.args.get("key")
       if key and state.tag_info_list:
           # Positional mapping: "1"→index 0, "2"→1, ..., "9"→8, "0"→9
           key_to_index = {str((i + 1) % 10): i for i in range(min(10, len(state.tag_info_list)))}
           if key in key_to_index:
               ti = state.tag_info_list[key_to_index[key]]
               await _add_highlight(state, ti.raw_key)
   ```
   The `state` variable must be in scope — it's captured in the closure from the enclosing function. Check that `_setup_document_events` (the enclosing function) has `state` as a parameter.

6. Update `handle_tag_click` (line 130):
   - Change from `async def handle_tag_click(tag: BriefTag) -> None:` to `async def handle_tag_click(tag_key: str) -> None:`
   - Change the body from `await _add_highlight(state, tag)` to `await _add_highlight(state, tag_key)`.

7. Update the `_build_tag_toolbar` call (line 134):
   - Change from `_build_tag_toolbar(handle_tag_click)` to `state.toolbar_container = _build_tag_toolbar(state.tag_info_list or [], handle_tag_click)`. Store the returned toolbar container element in PageState for Phase 5 rebuild.

8. Update the initial CSS call at line 123:
   - Change from `initial_css = _build_highlight_pseudo_css()` to:
     ```python
     tag_colours = {ti.raw_key: ti.colour for ti in (state.tag_info_list or [])}
     initial_css = _build_highlight_pseudo_css(tag_colours)
     ```

**In `highlights.py` — update `_add_highlight()` (lines 187-246):**

9. Change signature from `async def _add_highlight(state: PageState, tag: BriefTag | None = None) -> None:` to `async def _add_highlight(state: PageState, tag: str) -> None:`.

10. Remove the default fallback at line 234: `tag_value = tag.value if tag else "highlight"`. Replace with `tag_value = tag` (the tag parameter is already a UUID string).

11. Update the `state.crdt_doc.add_highlight(...)` call to pass `tag=tag_value` (no change needed if already doing this).

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: toolbar, keyboard, and highlights use DB-backed TagInfo`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update cards and PDF export to use TagInfo colour data

**Verifies:** 95-annotation-tags.AC5.3, 95-annotation-tags.AC5.4, 95-annotation-tags.AC5.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py`
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py`

**Implementation:**

**In `cards.py`:**

1. Remove the import at line 15: `from promptgrimoire.models.case import TAG_COLORS, BriefTag`. No replacement needed — colour data comes from `state.tag_info_list`.

2. Update the colour lookup (lines 146-150). Currently:
   ```python
   try:
       tag = BriefTag(tag_str)
       color = TAG_COLORS.get(tag, "#666")
   except ValueError:
       color = "#666"
   ```
   Replace with:
   ```python
   tag_colours = {ti.raw_key: ti.colour for ti in (state.tag_info_list or [])}
   color = tag_colours.get(tag_str, "#999999")
   ```

3. Update the tag dropdown (line 167). Currently:
   ```python
   tag_options = {t.value: t.value.replace("_", " ").title() for t in BriefTag}
   ```
   Replace with:
   ```python
   tag_options = {ti.raw_key: ti.name for ti in (state.tag_info_list or [])}
   ```

4. Update the `on_tag_change` handler's colour update (line 188). Currently:
   ```python
   new_color = TAG_COLORS.get(BriefTag(new_tag), "#666")
   ```
   Replace with:
   ```python
   new_color = tag_colours.get(new_tag, "#999999")
   ```
   Note: `tag_colours` must be in scope. Either rebuild the dict inside the handler or capture it from the closure. The simplest approach: rebuild inside `on_tag_change` from `state.tag_info_list`.

**In `pdf_export.py`:**

5. Remove the import at line 20: `from promptgrimoire.models.case import TAG_COLORS`.

6. Add `PageState` to the TYPE_CHECKING imports if not already there.

7. Update the tag colour dict at line 48. Currently:
   ```python
   tag_colours = {tag.value: colour for tag, colour in TAG_COLORS.items()}
   ```
   Replace with:
   ```python
   tag_colours = {ti.raw_key: ti.colour for ti in (state.tag_info_list or [])}
   ```
   Note: `_handle_pdf_export()` receives `state: PageState` as its first parameter (line 30), so `state.tag_info_list` is available. The `tag_colours` dict is then passed to `export_annotation_pdf(tag_colours=tag_colours, ...)` — the downstream `export/pdf_export.py` function signature is unchanged.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: cards and PDF export use DB-backed tag colours`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->
<!-- START_TASK_6 -->
### Task 6: Delete BriefTag, TAG_COLORS, TAG_SHORTCUTS from codebase

**Verifies:** 95-annotation-tags.AC5.11

**Files:**
- Modify: `src/promptgrimoire/models/case.py`
- Modify: `src/promptgrimoire/models/__init__.py`
- Modify: `tests/integration/conftest.py`

**Implementation:**

1. In `models/case.py` (lines 1-53): Delete the `BriefTag` class (lines 12-24), `TAG_COLORS` dict (lines 27-39), and `TAG_SHORTCUTS` dict (lines 42-53). Also remove the `from enum import StrEnum` import (line 9) if no longer used. Keep `ParsedRTF` and any other classes in the file.

2. In `models/__init__.py` (lines 1-27): Remove `TAG_COLORS`, `TAG_SHORTCUTS`, and `BriefTag` from the imports (lines 3-6) and from the `__all__` list (lines 17-20). Keep `ParsedRTF` and other exports.

3. In `tests/integration/conftest.py` (lines 34-46): Delete the hardcoded `TAG_COLOURS` dict. Update the `build_pdf_export` fixture's inner `_export()` function (line 122-129) to build `tag_colours` from the workspace's tags instead of the deleted constant:
   ```python
   from promptgrimoire.db.tags import list_tags_for_workspace
   tags = await list_tags_for_workspace(workspace_id)
   tag_colours = {str(tag.id): tag.color for tag in tags}
   ```
   The `workspace_id` needs to be passed into the `_export()` callable. Update the fixture's return type from `Callable[..., Awaitable[PdfExportResult]]` to accept `workspace_id: UUID` as a parameter (before `html`, `highlights`, etc.), and pass it through. Alternatively, keep the `tag_colours` parameter explicit and have test call sites build the dict themselves. The simplest approach: add `tag_colours: dict[str, str]` as a required parameter of `_export()`, replacing the hardcoded `TAG_COLOURS`. Test call sites build the dict from their test data.

4. Run a grep to confirm no remaining references:
   ```
   grep -r "BriefTag\|TAG_COLORS\|TAG_SHORTCUTS" src/ tests/
   ```
   Expected: No matches (other than this implementation plan if it's under docs/).

**Verification:**
Run: `uvx ty check`
Expected: No type errors

Run: `uv run test-debug`
Expected: All tests pass (unit tests that referenced BriefTag should have no remaining references; integration tests that used TAG_COLOURS should be updated)

**Commit:** `refactor: delete BriefTag, TAG_COLORS, TAG_SHORTCUTS from codebase`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Integration test for workspace_tags() and verification

**Verifies:** 95-annotation-tags.AC5.1, 95-annotation-tags.AC5.5, 95-annotation-tags.AC5.6

**Files:**
- Create: `tests/integration/test_workspace_tags.py`

**Implementation:**

Follow the pattern from `tests/integration/test_workspace_cloning.py`:
- Module-level `pytestmark` skip guard
- Async test methods

**Testing:**

`TestWorkspaceTags`:
- AC5.1: Create a workspace with 3 tags (via direct `session.add()` or Phase 2 CRUD). Call `workspace_tags(workspace_id)`. Verify returns 3 `TagInfo` instances with correct `name`, `colour`, and `raw_key` (UUID string). Verify order matches `order_index`.
- AC5.1: Create a workspace with 0 tags. Call `workspace_tags(workspace_id)`. Verify returns empty list.
- AC5.5/AC5.6: These are satisfied by `organise.py` and `respond.py` being tag-agnostic — they already use `list[TagInfo]`. Verify by confirming `workspace_tags()` returns `TagInfo` instances that match the expected interface (name, colour, raw_key fields populated).

`TestWorkspaceTagsOrdering`:
- Create a workspace with 3 tags at order_index 2, 0, 1. Call `workspace_tags(workspace_id)`. Verify returned list is ordered by order_index (0, 1, 2), not insertion order.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

Run: `uvx ty check`
Expected: No type errors

**Commit:** `test: add integration tests for workspace_tags() DB query`
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->
