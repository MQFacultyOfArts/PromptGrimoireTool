## Phase 4: Extract Shared Utilities from respond.py (Design Phase 3b)

### Acceptance Criteria Coverage

This phase is a refactoring phase — no new ACs are implemented. It consolidates duplicated anonymisation logic into `card_shared.py` to reduce maintenance burden and prepare for multi-document card rendering contexts. The Phase 1 characterisation tests serve as the regression safety net.

**Design plan note:** Phase 2 must also add `anonymise_author()` to respond.py's comment rendering (lines 158-170), not just the highlight author at line 155. The investigation found comments are also displayed with raw author names.

---

<!-- START_TASK_1 -->
### Task 1: Migrate respond.py to import from card_shared

**Verifies:** None (refactoring — characterisation tests verify no regression)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (update imports)

**Implementation:**
Replace the Phase 2 temporary import:
```python
# REPLACE: from .cards import _build_expandable_text
# WITH:
from .card_shared import build_expandable_text
```

Update call sites: `_build_expandable_text(...)` → `build_expandable_text(...)`

This completes the design Phase 3b migration — respond.py now uses the shared module, separated from the cards.py extraction (Phase 3) to reduce blast radius.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_respond_charac.py`
Expected: All characterisation tests pass

Run: `uv run grimoire test all`
Expected: Full test suite passes, no regressions

**Commit:** `refactor: respond.py imports from card_shared`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Extract anonymise_display_author() to card_shared.py

**Verifies:** None (refactoring — characterisation tests verify no regression)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/card_shared.py` (add helper)
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (replace inline calls)
- Modify: `src/promptgrimoire/pages/annotation/organise.py` (replace inline calls)

**Implementation:**
Add a helper to `card_shared.py` that wraps the 8-line `anonymise_author()` call pattern duplicated across all three card modules:

```python
from promptgrimoire.auth.anonymise import anonymise_author

def anonymise_display_author(
    raw_author: str,
    user_id: str | None,
    state: PageState,
) -> str:
    """Resolve display name for a highlight or comment author.

    Wraps the full anonymise_author() call with PageState fields.
    """
    return anonymise_author(
        author=raw_author,
        user_id=user_id,
        viewing_user_id=state.user_id,
        anonymous_sharing=state.is_anonymous,
        viewer_is_privileged=state.viewer_is_privileged,
        author_is_privileged=(
            user_id is not None and user_id in state.privileged_user_ids
        ),
    )
```

**Note on PageState import:** `card_shared.py` will need to import `PageState`. Use `TYPE_CHECKING` guard if needed to avoid circular imports (cards.py already imports PageState at module level, so this pattern is established).

Then replace all inline `anonymise_author()` calls in:

**cards.py** — two call sites:
- Highlight author (lines 475-484): replace with `anonymise_display_author(author, hl_user_id, state)`
- Comment author in `_build_single_comment()` (lines 132-141): replace with `anonymise_display_author(c_author_raw, c_user_id, state)`

**organise.py** — two call sites:
- Highlight author (lines 110-119): replace with `anonymise_display_author(raw_author, hl_user_id, state)`
- Comment author (lines 129-138): replace with `anonymise_display_author(raw_c_author, c_uid, state)`

Update imports in both files: remove direct `anonymise_author` import if no longer used, add `from .card_shared import anonymise_display_author`.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass (characterisation tests catch any regression in author display)

**Commit:** `refactor: extract anonymise_display_author to card_shared.py`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update respond.py to use anonymise_display_author()

**Verifies:** None (refactoring — consolidates Phase 2's anonymisation fix)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (replace direct calls)

**Implementation:**
After Phase 2 adds `anonymise_author()` calls to respond.py for both highlight and comment authors, replace them with the shared helper:

```python
from .card_shared import anonymise_display_author
```

Replace:
- Highlight author anonymisation (Phase 2 adds this at line 155 area): use `anonymise_display_author(author, hl_user_id, state)`
- Comment author anonymisation (Phase 2 adds this in lines 158-170 area): use `anonymise_display_author(comment_author, c_user_id, state)`

Remove direct `anonymise_author` import from respond.py if no longer needed.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

Run: `uv run complexipy src/promptgrimoire/pages/annotation/card_shared.py src/promptgrimoire/pages/annotation/cards.py src/promptgrimoire/pages/annotation/organise.py src/promptgrimoire/pages/annotation/respond.py`
Expected: All files within complexity limits

**Post-phase check:** Grep for direct `anonymise_author(` calls in the annotation package. Should appear ONLY in `card_shared.py`. If any direct call remains, the extraction is incomplete.

**Commit:** `refactor: respond.py uses shared anonymise_display_author`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

### Plan gap identified during Phase 3 review: `_matches_filter()` uses raw author names

**Problem:** `_matches_filter()` in `respond.py` (line ~194) searches `highlight["author"]` and `comment["author"]` directly — the raw CRDT values. When `anonymous_sharing=True`, the UI renders pseudonyms via `anonymise_display_author()`, but the filter searches against hidden real names. This means:
- Filtering by the pseudonym shown in the UI **will not match**
- Filtering by the hidden real name **will match** (information leak)

**Required fix (as part of this phase):**
1. `_matches_filter()` must accept `state: PageState` and use `anonymise_display_author()` on author fields before matching
2. Update `filter_highlights()` to pass `state` through to `_matches_filter()`
3. Update the caller in respond.py to pass `state` when calling `filter_highlights()`
4. Add/update characterisation tests at `test_annotation_respond.py` to verify:
   - Filter by pseudonym matches when `anonymous_sharing=True`
   - Filter by real name does NOT match when `anonymous_sharing=True`
   - Filter by real name still works when `anonymous_sharing=False`

**Why this belongs in Phase 4:** This phase consolidates all anonymisation into `anonymise_display_author()`. The filter path is an anonymisation consumer that was missed in the original plan. Fixing it here keeps all anonymisation work in one phase.
