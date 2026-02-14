# Annotation Module Split — Phase 3: git mv Satellite Modules

**Goal:** Move three satellite modules into the annotation package, preserving git rename detection.

**Architecture:** Use `git mv` to relocate `annotation_organise.py`, `annotation_respond.py`, and `annotation_tags.py` from `pages/` into `pages/annotation/`. Update all 13 import paths across 7 files.

**Tech Stack:** Python 3.14, git

**Scope:** 4 phases from original design (phase 3 of 4)

**Codebase verified:** 2026-02-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 120-annotation-split.AC1: Package replaces monolith (AC1.4, AC1.5)
- **120-annotation-split.AC1.4 Success:** Satellite modules exist inside package as `organise.py`, `respond.py`, `tags.py`
- **120-annotation-split.AC1.5 Success:** No `annotation_organise.py`, `annotation_respond.py`, or `annotation_tags.py` at the `pages/` level

### 120-annotation-split.AC3: Direct submodule imports (continuation)
- **120-annotation-split.AC3.1 Success:** All inter-module imports use direct paths (e.g., `from promptgrimoire.pages.annotation.organise import render_organise_tab`)

### 120-annotation-split.AC4: No logic changes
- **120-annotation-split.AC4.1 Success:** All existing tests pass (`uv run test-all`)
- **120-annotation-split.AC4.3 Edge:** Test import paths updated but test logic unchanged

---

<!-- START_TASK_1 -->
### Task 1: git mv satellite modules into package

**Verifies:** 120-annotation-split.AC1.4, 120-annotation-split.AC1.5

**Files:**
- Move: `src/promptgrimoire/pages/annotation_organise.py` → `src/promptgrimoire/pages/annotation/organise.py`
- Move: `src/promptgrimoire/pages/annotation_respond.py` → `src/promptgrimoire/pages/annotation/respond.py`
- Move: `src/promptgrimoire/pages/annotation_tags.py` → `src/promptgrimoire/pages/annotation/tags.py`

**Implementation:**

Use `git mv` (not `mv`) to preserve rename detection in git history:

```bash
git mv src/promptgrimoire/pages/annotation_organise.py src/promptgrimoire/pages/annotation/organise.py
git mv src/promptgrimoire/pages/annotation_respond.py src/promptgrimoire/pages/annotation/respond.py
git mv src/promptgrimoire/pages/annotation_tags.py src/promptgrimoire/pages/annotation/tags.py
```

**Do NOT commit yet** — import paths must be updated first (Task 2).

**Verification:**

```bash
# Verify files moved
ls src/promptgrimoire/pages/annotation/organise.py
ls src/promptgrimoire/pages/annotation/respond.py
ls src/promptgrimoire/pages/annotation/tags.py

# Verify old files gone
! test -f src/promptgrimoire/pages/annotation_organise.py
! test -f src/promptgrimoire/pages/annotation_respond.py
! test -f src/promptgrimoire/pages/annotation_tags.py
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update all import paths

**Verifies:** 120-annotation-split.AC3.1, 120-annotation-split.AC4.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/organise.py` (internal import, line 35)
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (internal import, line 36)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (imports from satellites — will have been updated in Phase 2 to reference `annotation_organise` etc.)
- Modify: `tests/unit/pages/test_annotation_organise.py` (lines 19, 20)
- Modify: `tests/unit/pages/test_annotation_respond.py` (lines 14–19)
- Modify: `tests/unit/pages/test_annotation_tags.py` (line 16)
- Modify: `tests/unit/pages/test_annotation_warp.py` (lines 17–25)

**Implementation:**

All changes follow the same pattern: replace `promptgrimoire.pages.annotation_X` with `promptgrimoire.pages.annotation.X` (where X is `organise`, `respond`, or `tags`).

**Source files (inside the annotation package — post Phase 2 split):**

```python
# organise.py line 35 — old:
from promptgrimoire.pages.annotation_tags import TagInfo
# new:
from promptgrimoire.pages.annotation.tags import TagInfo

# respond.py line 36 — old:
from promptgrimoire.pages.annotation_tags import TagInfo
# new:
from promptgrimoire.pages.annotation.tags import TagInfo

# workspace.py (or whichever module has these after Phase 2) — old:
from promptgrimoire.pages.annotation_organise import render_organise_tab
from promptgrimoire.pages.annotation_respond import render_respond_tab
from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info
# new:
from promptgrimoire.pages.annotation.organise import render_organise_tab
from promptgrimoire.pages.annotation.respond import render_respond_tab
from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info

# Also any TYPE_CHECKING import of TagInfo — old:
from promptgrimoire.pages.annotation_tags import TagInfo
# new:
from promptgrimoire.pages.annotation.tags import TagInfo
```

**Test files:**

```python
# test_annotation_organise.py — old:
from promptgrimoire.pages.annotation_organise import _SNIPPET_MAX_CHARS
from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info
# new:
from promptgrimoire.pages.annotation.organise import _SNIPPET_MAX_CHARS
from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info

# test_annotation_respond.py — old:
from promptgrimoire.pages.annotation_respond import (
    _SNIPPET_MAX_CHARS,
    _matches_filter,
    group_highlights_by_tag,
)
from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info
# new:
from promptgrimoire.pages.annotation.respond import (
    _SNIPPET_MAX_CHARS,
    _matches_filter,
    group_highlights_by_tag,
)
from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info

# test_annotation_tags.py — old:
from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info
# new:
from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info

# test_annotation_warp.py — old:
from promptgrimoire.pages.annotation_organise import (
    _build_highlight_card,
    render_organise_tab,
)
from promptgrimoire.pages.annotation_respond import (
    _build_reference_card,
    _build_reference_panel,
    render_respond_tab,
)
# new:
from promptgrimoire.pages.annotation.organise import (
    _build_highlight_card,
    render_organise_tab,
)
from promptgrimoire.pages.annotation.respond import (
    _build_reference_card,
    _build_reference_panel,
    render_respond_tab,
)
```

**No changes needed for:**
- `src/promptgrimoire/pages/__init__.py` — this file does not import or re-export the satellite modules. `from promptgrimoire.pages import annotation` resolves to the package directory, and satellite modules are accessed via direct submodule paths (e.g., `from promptgrimoire.pages.annotation.organise import ...`).

**Verification:**

```bash
# No old import paths remain
grep -r "annotation_organise\|annotation_respond\|annotation_tags" src/ tests/ --include="*.py"
# Expected: No matches (except possibly in comments/docstrings — verify manually)

uv run test-all
# Expected: All tests pass
```

**Commit:** `refactor: git mv satellite modules into annotation package`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update guard test for satellite modules

**Verifies:** 120-annotation-split.AC1.4, 120-annotation-split.AC1.5

**Files:**
- Modify: `tests/unit/test_annotation_package_structure.py` (created in Phase 2 Task 3)

**Implementation:**

Add assertions to the existing package structure guard test:

1. `organise.py`, `respond.py`, `tags.py` exist inside `pages/annotation/`
2. No `annotation_organise.py`, `annotation_respond.py`, or `annotation_tags.py` at `pages/` level
3. No Python file in `src/promptgrimoire/` imports from the old `annotation_organise`/`annotation_respond`/`annotation_tags` paths

**Testing:**

- 120-annotation-split.AC1.4: Assert satellite modules exist in package
- 120-annotation-split.AC1.5: Assert no satellite files at pages/ level

**Verification:**

```bash
uv run pytest tests/unit/test_annotation_package_structure.py -v
# Expected: All guard tests pass including new satellite checks

uv run test-all
# Expected: All tests pass
```

**Commit:** `test: extend guard tests for satellite module migration`
<!-- END_TASK_3 -->
