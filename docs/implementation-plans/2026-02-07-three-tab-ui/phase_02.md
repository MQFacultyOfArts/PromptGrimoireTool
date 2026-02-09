# Three-Tab Annotation Interface — Phase 2: CRDT Extension

**Goal:** Add `tag_order`, `response_draft`, and `response_draft_markdown` fields to `AnnotationDocument` so later phases have the shared data structures they need.

**Architecture:** Extend the existing `AnnotationDocument.__init__` to register three new root-level shared types on the pycrdt `Doc`: a `Map` for `tag_order` (mapping tag names to ordered Arrays of highlight IDs), an `XmlFragment` for `response_draft` (Milkdown/ProseMirror document), and a `Text` for `response_draft_markdown` (plain markdown mirror of response_draft, readable server-side for PDF export). Add properties, helper methods, and unit tests. No UI changes.

**Tech Stack:** pycrdt (`Map`, `Array`, `Text`, `XmlFragment`), pytest

**Scope:** 7 phases from original design (phase 2 of 7)

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### three-tab-ui.AC3: CRDT extended with new shared types
- **three-tab-ui.AC3.1 Success:** `tag_order` Map stores ordered highlight IDs per tag; survives server restart via persistence
- **three-tab-ui.AC3.2 Success:** `response_draft` XmlFragment coexists with existing highlights/client_meta/general_notes in the same Doc
- **three-tab-ui.AC3.3 Failure:** Adding new fields does not break existing highlight operations or broadcast

---

## Codebase Verification Findings

- ✓ `AnnotationDocument.__init__` at `crdt/annotation_doc.py:52-75` — registers `highlights` Map (line 62), `client_meta` Map (line 63), `general_notes` Text (line 64)
- ✓ Current imports at line 16: `from pycrdt import Awareness, Doc, Map, Text, TransactionEvent`
- ✓ Properties at lines 77-90: `highlights`, `client_meta`, `general_notes`
- ✓ Existing unit tests at `tests/unit/test_annotation_doc.py` — `TestGeneralNotes`, `TestHighlights` classes
- ✓ Echo prevention via `_origin_var: ContextVar[str | None]` at line 25
- ✓ `AnnotationDocumentRegistry.get_or_create_for_workspace` at line 509 loads/saves CRDT state via `Workspace.crdt_state`
- ✓ pycrdt `Array` supports `append()`, `insert()`, `extend()`, `clear()`, indexing, `del`, iteration
- ✓ pycrdt `XmlFragment` is a root-level shared type registered via `doc["name"] = XmlFragment()`
- ✓ pycrdt `Map` can store `Array` values — set via `map[key] = Array(items)`. To update the contents, create a new `Array` with the desired items and re-assign it to the Map key (the implementation in Task 2 uses this pattern)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add tag_order and response_draft to AnnotationDocument

**Verifies:** three-tab-ui.AC3.1, three-tab-ui.AC3.2

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:16` (imports)
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:52-75` (`__init__`)
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:77-90` (properties section)

**Implementation:**

1. Update the import line at `annotation_doc.py:16`:
```python
from pycrdt import Array, Awareness, Doc, Map, Text, TransactionEvent, XmlFragment
```

2. Add three new root-level shared types in `__init__`, after line 64:
```python
self.doc["tag_order"] = Map()  # {tag_name: Array([highlight_id, ...])}
self.doc["response_draft"] = XmlFragment()  # Milkdown/ProseMirror document
self.doc["response_draft_markdown"] = Text()  # Plain markdown mirror of response_draft
```

3. Add properties after the existing `general_notes` property (after line 90):
```python
@property
def tag_order(self) -> Map:
    """Get the tag_order Map."""
    return self.doc["tag_order"]

@property
def response_draft(self) -> XmlFragment:
    """Get the response_draft XmlFragment."""
    return self.doc["response_draft"]

@property
def response_draft_markdown(self) -> Text:
    """Get the response_draft_markdown Text."""
    return self.doc["response_draft_markdown"]
```

4. Add a helper method:
```python
def get_response_draft_markdown(self) -> str:
    """Get the current response draft markdown content."""
    return str(self.response_draft_markdown)
```

The `response_draft_markdown` Text field is a server-readable mirror of the `response_draft` XmlFragment. It is updated from the browser whenever the Milkdown editor content changes (Phase 7 Task 2). The field can be read from Python without needing to deserialise ProseMirror XML. `str()` on a pycrdt `Text` returns the text content.

**Testing:**
No separate tests for this task — tested via Task 2.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v`
Expected: All existing tests still pass (no regression from adding new fields)

**Commit:** `feat: add tag_order Map, response_draft XmlFragment, and response_draft_markdown Text to AnnotationDocument`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add tag_order helper methods

**Verifies:** three-tab-ui.AC3.1

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (new methods after highlight operations section, before comment operations)

**Implementation:**

Add helper methods for manipulating the `tag_order` Map. These methods manage ordered Arrays of highlight IDs per tag:

1. `get_tag_order(tag: str) -> list[str]` — Returns the ordered list of highlight IDs for a given tag. Returns empty list if tag has no explicit ordering.

2. `set_tag_order(tag: str, highlight_ids: list[str], origin_client_id: str | None = None) -> None` — Replaces the ordered list of highlight IDs for a tag. Uses the `_origin_var` pattern for echo prevention. Must create an `Array` within the Map entry.

3. `move_highlight_to_tag(highlight_id: str, from_tag: str | None, to_tag: str, position: int = -1, origin_client_id: str | None = None) -> bool` — Removes `highlight_id` from `from_tag`'s order (if present and `from_tag` is not None), then inserts it into `to_tag`'s order at `position` (-1 means append). Also calls `update_highlight_tag` to change the highlight's tag field. Returns `True` if the highlight exists.

Key implementation details:
- pycrdt `Map` values that are `Array` must be set as a whole (`self.tag_order[tag] = Array(items)`) — you cannot mutate a nested Array in-place after initial assignment without re-setting it.
- All mutations must use the `_origin_var` echo prevention pattern (token = set, try/finally reset).

**Testing:**
Tests must verify each AC listed above:
- three-tab-ui.AC3.1: `tag_order` stores and retrieves ordered highlight IDs per tag

Write unit tests in `tests/unit/test_annotation_doc.py` in a new `TestTagOrder` class:
- `test_get_tag_order_empty_tag` — returns empty list for unknown tag
- `test_set_and_get_tag_order` — set a list of IDs, retrieve same list
- `test_set_tag_order_replaces_existing` — setting again replaces previous order
- `test_move_highlight_to_tag_appends` — move from one tag to another, verify removed from source and appended to target
- `test_move_highlight_to_tag_at_position` — move with specific position, verify insertion index
- `test_move_highlight_to_tag_updates_highlight_tag` — verify the highlight's `tag` field is updated
- `test_move_highlight_to_tag_nonexistent_highlight` — returns False for nonexistent highlight
- `test_tag_order_syncs_between_docs` — create two AnnotationDocuments, set tag_order in one, apply update to other, verify order matches

Follow existing test patterns: sync `AnnotationDocument("test-doc")` instances, use `doc.get_update()` and `apply_update()` for CRDT sync verification.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py::TestTagOrder -v`
Expected: All tests pass

**Commit:** `feat: add tag_order helper methods to AnnotationDocument`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify response_draft and existing functionality coexistence

**Verifies:** three-tab-ui.AC3.2, three-tab-ui.AC3.3

**Files:**
- Test: `tests/unit/test_annotation_doc.py`

**Implementation:**

No production code changes — this task adds tests verifying that the new CRDT fields coexist with existing ones and that existing operations are unaffected.

**Testing:**
Tests must verify:
- three-tab-ui.AC3.2: `response_draft` XmlFragment coexists with existing fields
- three-tab-ui.AC3.3: Adding new fields does not break existing operations

Write unit tests in `tests/unit/test_annotation_doc.py`:

In a new `TestResponseDraft` class:
- `test_response_draft_property_returns_xml_fragment` — verify `doc.response_draft` returns an `XmlFragment` instance
- `test_response_draft_coexists_with_other_fields` — create doc, add a highlight, set general notes, access response_draft — all three operations succeed on same doc
- `test_response_draft_survives_full_state_sync` — get full state from doc1, apply to doc2, verify doc2 has a valid response_draft XmlFragment

In a new `TestResponseDraftMarkdown` class:
- `test_response_draft_markdown_property` — verify `doc.response_draft_markdown` returns a `Text` instance
- `test_get_response_draft_markdown_empty` — verify `get_response_draft_markdown()` returns empty string for new doc
- `test_response_draft_markdown_round_trip` — set markdown content on doc1's `response_draft_markdown` Text, sync to doc2 via CRDT update, verify doc2 reads same markdown via `get_response_draft_markdown()`
- `test_response_draft_markdown_coexists` — verify it doesn't break existing fields (highlights, general_notes, response_draft)

In a new `TestCrdtCoexistence` class:
- `test_existing_highlights_unaffected` — create doc with new fields, add/get/remove highlights — identical behaviour to before
- `test_existing_general_notes_unaffected` — create doc with new fields, set/get general notes — identical behaviour
- `test_broadcast_fires_for_all_field_types` — register a broadcast callback, modify highlights, tag_order, and general_notes — verify callback fires for each
- `test_full_state_includes_all_fields` — create doc, add highlight, set tag_order, set general_notes, get full state, apply to new doc — all data present in new doc

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v`
Expected: All tests pass (new + existing)

**Commit:** `test: verify CRDT extension coexistence with existing fields`

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run full unit test suite: `uv run pytest tests/unit/test_annotation_doc.py -v`
2. [ ] Verify all existing tests in `TestGeneralNotes` and `TestHighlights` pass unchanged
3. [ ] Verify new `TestTagOrder` tests pass — tag ordering, moving highlights, CRDT sync
4. [ ] Verify new `TestResponseDraft` tests pass — XmlFragment creation, coexistence, sync
5. [ ] Verify new `TestCrdtCoexistence` tests pass — all field types work together
6. [ ] Start the app: `uv run python -m promptgrimoire`
7. [ ] Navigate to `/annotation`, create a workspace, add content
8. [ ] Verify existing annotation functionality works (highlighting, editing, deleting) — no regressions from CRDT changes

## Evidence Required
- [ ] Test output showing green for all `test_annotation_doc.py` tests
- [ ] Screenshot or confirmation that annotation page loads and works normally
