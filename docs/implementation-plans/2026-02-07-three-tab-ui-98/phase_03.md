# Three-Tab Annotation Interface — Phase 3: Tag-Agnostic Interface

**Goal:** Create the `TagInfo` abstraction and wire it to Tab 2's column rendering with static (non-draggable) highlight cards.

**Architecture:** Introduce a new `pages/annotation_tags.py` module with a `TagInfo` dataclass and a mapper function that converts `BriefTag` + `TAG_COLORS` into `list[TagInfo]`. Tab 2's deferred-render handler (from Phase 1) populates columns — one per tag — showing highlight cards grouped by tag. Tab 2 reads from the CRDT `highlights` Map and `tag_order` Map (from Phase 2). No drag-and-drop yet.

**Tech Stack:** NiceGUI `ui.column`, `ui.card`, `ui.label`, `ui.row`; Python dataclasses

**Scope:** 7 phases from original design (phase 3 of 7)

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### three-tab-ui.AC2: Tab 2 organises highlights by tag
- **three-tab-ui.AC2.1 Success:** Tab 2 shows one column per tag with the tag's name and colour
- **three-tab-ui.AC2.2 Success:** Highlight cards appear in the correct tag column, showing text snippet, tag, and author
- **three-tab-ui.AC2.6 Edge:** A highlight with no tag appears in an "Untagged" section or column

---

## Codebase Verification Findings

- ✓ `BriefTag` StrEnum at `models/case.py:12-24` — 10 members (JURISDICTION through REFLECTION)
- ✓ `TAG_COLORS` dict at `models/case.py:28-39` — `dict[BriefTag, str]` with colorblind-accessible palette
- ✓ `TAG_SHORTCUTS` at `models/case.py:42-53` — keyboard shortcut mapping
- ✓ BriefTag imported in `annotation.py:43` — used for tag toolbar, highlight card dropdown, card styling
- ✓ Highlight card rendering at `annotation.py:722-859` — card with coloured left border, tag dropdown, author, text preview
- ✓ No existing `pages/annotation_tags.py` — confirmed via glob search
- ✓ No tag-agnostic abstraction exists anywhere in the codebase
- ✗ Tab container does not exist yet — Phase 1 creates it; Phase 3 populates Tab 2 panel within that container

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Create TagInfo abstraction and mapper

**Verifies:** three-tab-ui.AC2.1 (partially — provides the data structure)

**Files:**
- Create: `src/promptgrimoire/pages/annotation_tags.py`
- Test: `tests/unit/pages/test_annotation_tags.py`

**Implementation:**

Create a new module `pages/annotation_tags.py` with:

1. A `TagInfo` dataclass (or `NamedTuple`) with two fields:
   - `name: str` — the display name (e.g., "Jurisdiction", "Legal Issues")
   - `colour: str` — hex colour string (e.g., "#1f77b4")

2. A `brief_tags_to_tag_info() -> list[TagInfo]` function that:
   - Iterates `BriefTag` members
   - For each, creates a `TagInfo` with `name = tag.value.replace("_", " ").title()` and `colour = TAG_COLORS[tag]`
   - Returns the list in enum order
   - Verified: BriefTag values are all lowercase underscore-delimited at `models/case.py:15-24` (e.g., `"jurisdiction"`, `"procedural_history"`, `"legally_relevant_facts"`, `"courts_reasoning"`). The `.replace("_", " ").title()` formula produces correct display names: "Jurisdiction", "Procedural History", "Legally Relevant Facts", "Courts Reasoning", etc.

This module is the **only place** that imports `BriefTag` for Tab 2/Tab 3 purposes. The tab rendering code receives `list[TagInfo]` and never imports `BriefTag` directly.

**Testing:**
Tests must verify:
- three-tab-ui.AC2.1 (data structure): `brief_tags_to_tag_info()` returns correct number of TagInfo entries (10), each with non-empty name and valid hex colour

Write unit tests in `tests/unit/pages/test_annotation_tags.py`:
- `test_brief_tags_to_tag_info_returns_all_tags` — result has 10 entries, one per BriefTag
- `test_tag_info_names_are_title_case` — each name matches `tag.value.replace("_", " ").title()`
- `test_tag_info_colours_are_hex` — each colour starts with `#` and has 7 characters
- `test_tag_info_colours_match_tag_colors` — each colour matches `TAG_COLORS[tag]`

**Verification:**
Run: `uv run pytest tests/unit/pages/test_annotation_tags.py -v`
Expected: All tests pass

**Commit:** `feat: add TagInfo abstraction and BriefTag mapper`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Render Tab 2 columns with highlight cards

**Verifies:** three-tab-ui.AC2.1, three-tab-ui.AC2.2, three-tab-ui.AC2.6

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` (the `_on_tab_change` handler from Phase 1)
- Create: `src/promptgrimoire/pages/annotation_organise.py` (Tab 2 rendering logic)

**Implementation:**

Create a new module `pages/annotation_organise.py` with a function:

```python
def render_organise_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    state: PageState,
) -> None:
```

This function:
1. Clears the placeholder label from the panel
2. Creates a horizontally scrollable `ui.row` container
3. For each `TagInfo`, creates a `ui.column` with:
   - A coloured header showing `tag.name` with background `tag.colour`
   - Highlight cards for that tag, fetched from `crdt_doc.get_all_highlights()` filtered by tag
   - Cards ordered by `crdt_doc.get_tag_order(tag_name)` if available, with unordered highlights appended at the bottom
4. **Untagged column (AC2.6):** After iterating all TagInfo columns, check for highlights with no tag (empty string or None). If any exist, add a final "Untagged" column with a grey header (`#999999`) containing those highlight cards. This column uses the tag name `""` (empty string) for CRDT tag_order storage.
5. Each highlight card shows:
   - Text snippet (first ~100 chars, or use `_build_expandable_text` pattern)
   - Tag name (or "Untagged" for highlights with no tag)
   - Author name
   - A coloured left border matching the tag (grey for untagged)

In `annotation.py`, modify the `_on_tab_change` handler (created in Phase 1 Task 2) so that when `tab_name == "Organise"`:
1. Import and call `render_organise_tab()` with the tab panel, tag info list, CRDT doc, and page state
2. The tag info list is created once via `brief_tags_to_tag_info()` and stored on `PageState`

Add a new field to `PageState`:
```python
tag_info_list: list[Any] | None = None  # list[TagInfo] — populated on first Tab 2 visit
```

**Key design decision:** Tab 2 rendering is a **separate module** (`annotation_organise.py`) to avoid further bloating `annotation.py` (already ~2302 lines). The module imports `TagInfo` but NOT `BriefTag`.

**Testing:**
Tests must verify:
- three-tab-ui.AC2.1: Tab 2 shows one column per tag with name and colour
- three-tab-ui.AC2.2: Highlight cards in correct columns with text snippet, tag, author
- three-tab-ui.AC2.6: Untagged highlights appear in an "Untagged" column

Write E2E tests in `tests/e2e/test_annotation_tabs.py`:
- `test_organise_tab_shows_tag_columns` — navigate to annotation page, create a highlight, click "Organise" tab, verify tag column headers appear with correct names
- `test_organise_tab_highlight_in_correct_column` — create a highlight with specific tag, switch to Organise tab, verify the card appears in the correct column (matching tag name)
- `test_organise_tab_card_shows_author_and_text` — create a highlight, switch to Organise tab, verify card shows the author name and a text snippet
- `test_organise_tab_untagged_highlight_in_untagged_column` — create a highlight without assigning a tag, switch to Organise tab, verify the card appears in an "Untagged" column (AC2.6)

Follow existing E2E patterns from `tests/e2e/test_annotation_basics.py` — use `authenticated_page` fixture, `setup_workspace_with_content` helper.

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_organise`
Expected: All tests pass

**Commit:** `feat: render Tab 2 tag columns with highlight cards`

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run unit tests: `uv run pytest tests/unit/pages/test_annotation_tags.py -v`
2. [ ] Run E2E tests: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_organise`
3. [ ] Start the app: `uv run python -m promptgrimoire`
4. [ ] Navigate to `/annotation`, create a workspace, add content
5. [ ] Create several highlights with different tags
6. [ ] Click "Organise" tab
7. [ ] Verify: One column per tag, each with coloured header showing tag name
8. [ ] Verify: Highlight cards appear in the column matching their tag
9. [ ] Verify: Each card shows text snippet, tag name, and author
10. [ ] Go back to "Annotate" tab, create another highlight
11. [ ] Switch to "Organise" tab again — verify new highlight appears in correct column
12. [ ] Create a highlight without assigning a tag — verify it appears in an "Untagged" column

## Evidence Required
- [ ] Test output showing green for tag info unit tests
- [ ] Test output showing green for Tab 2 E2E tests
- [ ] Screenshot showing Tab 2 with tag columns and highlight cards
