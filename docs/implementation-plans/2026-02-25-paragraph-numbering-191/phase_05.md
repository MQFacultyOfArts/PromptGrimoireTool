# Paragraph Numbering Implementation Plan — Phase 5: Highlight para_ref Population

**Goal:** Annotation cards display paragraph references computed from the document's paragraph map.

**Architecture:** A pure lookup function in `paragraph_map.py` computes `para_ref` from `start_char`/`end_char` + the document's `paragraph_map`. Called during highlight creation in `highlights.py`. The map is cached in `PageState` (same pattern as `document_chars`). Card display already works — just needs non-empty data.

**Tech Stack:** Python `bisect`, NiceGUI PageState, pycrdt CRDT

**Scope:** Phase 5 of 7 from original design

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### paragraph-numbering-191.AC5: Annotation cards display para_ref
- **paragraph-numbering-191.AC5.1 Success:** Highlight on paragraph 3 shows `[3]` on the annotation card
- **paragraph-numbering-191.AC5.2 Success:** Highlight spanning paragraphs 3-5 shows `[3]-[5]`
- **paragraph-numbering-191.AC5.4 Edge:** Highlight on unnumbered block (header, empty) shows no `para_ref`

(AC5.3 — user-editable para_ref — deferred to Phase 7: Toggle UI)

---

## Reference Files

The executor MUST read these before implementing:
- `src/promptgrimoire/input_pipeline/paragraph_map.py` — Phase 2 output, where the lookup function belongs
- `src/promptgrimoire/pages/annotation/highlights.py` — `_add_highlight()` (~line 178), where para_ref is computed and passed
- `src/promptgrimoire/pages/annotation/cards.py` — `_build_annotation_card()` (~line 287), already renders `para_ref`
- `src/promptgrimoire/crdt/annotation_doc.py` — `add_highlight()` (~line 216), already accepts `para_ref` parameter
- The `PageState` class definition — where `paragraph_map` will be cached. Locate via: `grep -rn "class PageState" src/promptgrimoire/`
- `CLAUDE.md` — testing conventions

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add `lookup_para_ref()` pure function

**Verifies:** paragraph-numbering-191.AC5.1, AC5.2, AC5.4

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/paragraph_map.py`
- Modify: `src/promptgrimoire/input_pipeline/__init__.py` (export)

**Implementation:**

Add to `paragraph_map.py`:

```python
def lookup_para_ref(
    paragraph_map: dict[str, int],
    start_char: int,
    end_char: int,
) -> str:
```

Logic:
1. If `paragraph_map` is empty, return `""`
2. Sort the keys as integers: `sorted_offsets = sorted(int(k) for k in paragraph_map)`
3. Use `bisect.bisect_right(sorted_offsets, start_char) - 1` to find the largest offset `<= start_char`
4. If index < 0 (start_char before first paragraph), return `""`
5. Look up paragraph number: `start_para = paragraph_map[str(sorted_offsets[idx])]`
6. Repeat for `end_char` to find `end_para`
7. If `start_para == end_para`: return `f"[{start_para}]"`
8. If different: return `f"[{start_para}]-[{end_para}]"`

Export from `__init__.py`.

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: add lookup_para_ref() for computing paragraph references from char offsets`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for lookup_para_ref

**Verifies:** paragraph-numbering-191.AC5.1, AC5.2, AC5.4

**Files:**
- Modify: `tests/unit/input_pipeline/test_paragraph_map.py`

**Testing:**

Add test class `TestLookupParaRef`:

- AC5.1: `paragraph_map={"0": 1, "10": 2, "20": 3}`, `start_char=10, end_char=15` → `"[2]"`
- AC5.2: `start_char=10, end_char=25` → `"[2]-[3]"`
- AC5.4: `start_char=0, end_char=5` with map starting at offset 10 → check behavior (highlight before first paragraph)
- Empty map → `""`
- Single paragraph map → `"[1]"` regardless of position
- Highlight exactly at paragraph boundary → correct paragraph number

**Verification:**
```bash
uv run pytest tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef -v
```

**Commit:** `test: add tests for para_ref lookup function`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Cache paragraph_map in PageState and wire into highlight creation

**Verifies:** paragraph-numbering-191.AC5.1, AC5.2, AC5.4

**Files:**
- Modify: `PageState` class definition (locate via: `grep -rn "class PageState" src/promptgrimoire/`)
- Modify: `src/promptgrimoire/pages/annotation/highlights.py` (~line 178, `_add_highlight()`)
- Modify: wherever `PageState` is initialised with document data (same place `document_chars` is set)

**Implementation:**

1. **Add `paragraph_map` field to `PageState`:**
   Add a `paragraph_map: dict[str, int]` field alongside the existing `document_chars` field, using the same default pattern as `document_chars` (check whether `PageState` uses `dataclass`, `@dataclass`, attrs, or plain `__init__` — match whatever pattern `document_chars` uses for its default, e.g. `field(default_factory=dict)` for dataclasses). Populate it from `doc.paragraph_map` at the same point where `document_chars` is loaded from `doc.content`.

2. **Wire into `_add_highlight()`:**
   After `start_char` and `end_char` are normalised (~line 221-222), compute `para_ref`:

   ```python
   from promptgrimoire.input_pipeline.paragraph_map import lookup_para_ref

   para_ref = lookup_para_ref(state.paragraph_map, start_char, end_char)
   ```

   Then pass to the CRDT call (~line 230-238):

   ```python
   state.crdt_doc.add_highlight(
       start_char=start_char,
       end_char=end_char,
       tag=tag,
       text=text,
       author=state.user_name,
       para_ref=para_ref,  # NEW
       document_id=str(state.document_id),
       user_id=state.user_id,
   )
   ```

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: populate para_ref on highlight creation from paragraph map`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Integration test for highlight para_ref wiring

**Verifies:** paragraph-numbering-191.AC5.1, AC5.2, AC5.4

**Files:**
- Modify: `tests/integration/test_paragraph_numbering.py` (add to existing file from Phase 1/3)

**Testing:**

Add test class `TestHighlightParaRefWiring`:
- AC5.1: Create a document with a populated `paragraph_map`, create a highlight at a known char offset within paragraph 3, verify the CRDT highlight has `para_ref="[3]"`
- AC5.2: Create a highlight spanning paragraphs 2-4, verify `para_ref="[2]-[4]"`
- AC5.4: Create a highlight at a char offset before the first paragraph entry, verify `para_ref=""` (empty)

This tests the end-to-end wiring from `PageState.paragraph_map` through `_add_highlight()` to CRDT storage, rather than the pure `lookup_para_ref()` function (already unit-tested in Phase 5 Task 2).

Follow the existing integration test patterns in `tests/integration/test_paragraph_numbering.py` — class-based, `db_session` fixture, skip guard.

**Verification:**
```bash
uv run pytest tests/integration/test_paragraph_numbering.py -v
```
Expected: All tests pass (Phase 1 + Phase 3 + Phase 5 tests).

**Commit:** `test: add integration test for highlight para_ref wiring`
<!-- END_TASK_4 -->

---

## UAT Steps

1. [ ] Run unit tests: `uv run pytest tests/unit/input_pipeline/test_paragraph_map.py::TestLookupParaRef -v` — all pass
2. [ ] Run integration tests: `uv run pytest tests/integration/test_paragraph_numbering.py -v` — all pass (Phase 1 + Phase 3 + Phase 5)
3. [ ] Type check clean: `uvx ty check`
4. [ ] Start the app: `uv run python -m promptgrimoire`
5. [ ] Open a workspace with a document that has paragraph numbers visible in margin (from Phase 4)
6. [ ] Create a highlight on a paragraph — verify the annotation card shows `[N]` where N is the paragraph number (AC5.1)
7. [ ] Create a highlight spanning multiple paragraphs — verify the card shows `[N]-[M]` (AC5.2)
8. [ ] Create a highlight on a header (no paragraph number) — verify the card shows no para_ref (AC5.4)

## Evidence Required
- [ ] Unit test output for TestLookupParaRef all green
- [ ] Integration test output all green
- [ ] Screenshot showing annotation card with `[N]` para_ref
