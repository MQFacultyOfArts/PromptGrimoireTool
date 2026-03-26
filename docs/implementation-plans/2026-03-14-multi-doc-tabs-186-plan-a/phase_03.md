## Phase 3: Extract Shared Utilities from cards.py

### Acceptance Criteria Coverage

This phase is a refactoring phase — no new ACs are implemented. It restructures code to reduce duplication and prepare for diff-based card updates (Phase 5). The Phase 1 characterisation tests serve as the regression safety net.

---

<!-- START_TASK_1 -->
### Task 1: Create card_shared.py with extracted functions

**Verifies:** None (refactoring — characterisation tests verify no regression)

**Files:**
- Create: `src/promptgrimoire/pages/annotation/card_shared.py`
- Modify: `src/promptgrimoire/pages/annotation/cards.py:34-74` (remove extracted functions)

**Implementation:**
Create `card_shared.py` containing two functions extracted from `cards.py`:

1. `author_initials(name: str) -> str` (from cards.py lines 34-41) — pure function, derives compact initials from display name. Only dependency: `re` (stdlib).

2. `build_expandable_text(full_text: str) -> None` (from cards.py lines 44-74) — pure UI builder, 80-char threshold with toggle between truncated and full views. Only dependency: `nicegui.ui`.

Both functions are renamed to drop the leading underscore — they're public within the annotation package but not exported from `__init__.py`.

Remove both functions from `cards.py`. Add import in `cards.py`:
```python
from .card_shared import author_initials, build_expandable_text
```

Update all call sites in `cards.py`:
- `_author_initials(...)` → `author_initials(...)`
- `_build_expandable_text(...)` → `build_expandable_text(...)`

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass (Phase 1 characterisation tests catch any regression)

Run: `uv run complexipy src/promptgrimoire/pages/annotation/card_shared.py`
Expected: All functions within complexity limits

**Commit:** `refactor: extract shared card utilities to card_shared.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update organise.py to import from card_shared

**Verifies:** None (refactoring — characterisation tests verify no regression)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/organise.py` (update imports)

**Implementation:**
Replace the Phase 2 temporary import:
```python
# REPLACE: from .cards import _build_expandable_text
# WITH:
from .card_shared import build_expandable_text
```

Update call sites: `_build_expandable_text(...)` → `build_expandable_text(...)`

If `author_initials` is used in organise.py (check — organise.py may use `anonymise_author` directly instead), import from `card_shared` too.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_organise_charac.py`
Expected: All characterisation tests pass

**Commit:** `refactor: organise.py imports from card_shared`
<!-- END_TASK_2 -->

**Note:** respond.py migration to `card_shared` is deferred to Phase 4 (design Phase 3b) per the design's sequential isolation rationale — stabilise cards.py extraction before touching respond.py.
