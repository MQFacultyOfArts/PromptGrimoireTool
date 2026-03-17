# Business Exception Handling Implementation Plan

**Goal:** Establish `BusinessLogicError` exception taxonomy, reparent all domain exceptions, replace bare `PermissionError` raises, and update all callers.

**Architecture:** All domain exceptions consolidated in `db/exceptions.py` under `BusinessLogicError(Exception)`. Bare `PermissionError` raises replaced with named subclasses. UI callers and tests updated to catch specific subclasses. ast-grep (`sg`) used for structural rewrites.

**Tech Stack:** Python 3.14, structlog, pytest, ast-grep (sg)

**Scope:** 4 phases from original design (phases 1-4). This is Phase 1.

**Codebase verified:** 2026-03-16

**Design divergence:** Design said "exceptions stay where they're defined, just gain a shared parent." This implementation consolidates all domain exceptions into `db/exceptions.py` for a cleaner taxonomy. Approved by human reviewer during planning.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### business-exception-handling-363.AC1: Exception Taxonomy
- **business-exception-handling-363.AC1.1 Success:** All 10 domain exceptions (`DuplicateNameError`, `DeletionBlockedError`, `DuplicateCodenameError`, `ZeroEditorError`, `ProtectedDocumentError`, `DuplicateEnrollmentError`, `StudentIdConflictError`, `SharePermissionError`, `OwnershipError`, `TagCreationDeniedError`) are `isinstance(exc, BusinessLogicError)`
- **business-exception-handling-363.AC1.2 Success:** `SharePermissionError` replaces bare `PermissionError` at `acl.py:417`, `acl.py:453`, `acl.py:456`, `acl.py:475`
- **business-exception-handling-363.AC1.3 Success:** `OwnershipError` replaces bare `PermissionError` at `workspaces.py:443`, `workspace_documents.py:259`
- **business-exception-handling-363.AC1.4 Success:** `TagCreationDeniedError` replaces bare `PermissionError` at `tags.py:53`, `tags.py:716`
- **business-exception-handling-363.AC1.5 Success:** `str(SharePermissionError("msg"))` == `"msg"` (user-facing message preservation for `sharing.py:199`)
- **business-exception-handling-363.AC1.6 Success (intentional breaking change):** `DuplicateNameError` is NOT `isinstance(exc, ValueError)`. Deliberate reparenting — callers already catch by class name, not via `ValueError`.
- **business-exception-handling-363.AC1.7 Success:** `BusinessLogicError`, `SharePermissionError`, `OwnershipError`, `TagCreationDeniedError` exported in `db/__init__.py.__all__`. All existing exception exports preserved.
- **business-exception-handling-363.AC1.8 Success:** No bare `PermissionError` raises remain in `src/promptgrimoire/db/`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create BusinessLogicError base and 3 new exception classes in db/exceptions.py

**Files:**
- Modify: `src/promptgrimoire/db/exceptions.py` (currently lines 1-45)

**Implementation:**

Add `BusinessLogicError(Exception)` as the base class. Add three new subclasses: `SharePermissionError`, `OwnershipError`, `TagCreationDeniedError`. Reparent existing `DeletionBlockedError` and `ProtectedDocumentError` from `Exception` to `BusinessLogicError`.

At the top of `db/exceptions.py`, before existing classes:

```python
class BusinessLogicError(Exception):
    """Base class for expected business logic rejections in the DB layer.

    Raised for anticipated user-facing error conditions (duplicate names,
    permission violations, protected resources). Distinguished from
    unexpected failures by get_session() for log-level triage.
    """


class SharePermissionError(BusinessLogicError):
    """Sharing policy violation (non-owner share attempt, sharing disabled, or owner-grant attempt)."""


class OwnershipError(BusinessLogicError):
    """Non-owner attempted an owner-only operation (e.g. workspace/document deletion)."""


class TagCreationDeniedError(BusinessLogicError):
    """Tag creation denied by placement context policy."""
```

Then change existing classes:
- `DeletionBlockedError(Exception)` → `DeletionBlockedError(BusinessLogicError)`
- `ProtectedDocumentError(Exception)` → `ProtectedDocumentError(BusinessLogicError)`

**Verification:**

```bash
uv run python -c "
from promptgrimoire.db.exceptions import (
    BusinessLogicError, SharePermissionError, OwnershipError,
    TagCreationDeniedError, DeletionBlockedError, ProtectedDocumentError,
)
assert issubclass(SharePermissionError, BusinessLogicError)
assert issubclass(OwnershipError, BusinessLogicError)
assert issubclass(TagCreationDeniedError, BusinessLogicError)
assert issubclass(DeletionBlockedError, BusinessLogicError)
assert issubclass(ProtectedDocumentError, BusinessLogicError)
assert str(SharePermissionError('test msg')) == 'test msg'
print('OK')
"
```

**Commit:** `feat: add BusinessLogicError base class and new exception subclasses`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Move scattered exceptions into db/exceptions.py and update internal imports

**Verifies:** business-exception-handling-363.AC1.1, business-exception-handling-363.AC1.6

**Files:**
- Modify: `src/promptgrimoire/db/exceptions.py` — add moved exception classes
- Modify: `src/promptgrimoire/db/tags.py` — remove `DuplicateNameError` definition, add import
- Modify: `src/promptgrimoire/db/wargames.py` — remove `DuplicateCodenameError` and `ZeroEditorError` definitions, add imports
- Modify: `src/promptgrimoire/db/courses.py` — remove `DuplicateEnrollmentError` definition, add import
- Modify: `src/promptgrimoire/db/enrolment.py` — remove `StudentIdConflictError` definition, add import

**Implementation:**

Move these 5 exception classes to `db/exceptions.py`, reparenting to `BusinessLogicError`:

1. **`DuplicateNameError`** from `tags.py:24` — change base from `ValueError` to `BusinessLogicError`. This is an intentional breaking change (AC1.6): callers already catch by class name.

2. **`DuplicateCodenameError`** from `wargames.py:73` — change base from `Exception` to `BusinessLogicError`. Preserve the custom `__init__` signature: `(self, activity_id: UUID, codename: str)`.

3. **`ZeroEditorError`** from `wargames.py:84` — change base from `Exception` to `BusinessLogicError`. Preserve the custom `__init__` signature: `(self, team_id: UUID, user_id: UUID, current_permission: str | None, attempted_permission: str | None)`.

4. **`DuplicateEnrollmentError`** from `courses.py:275` — change base from `Exception` to `BusinessLogicError`. Preserve the custom `__init__` signature: `(self, course_id: UUID, user_id: UUID)`.

5. **`StudentIdConflictError`** from `enrolment.py:31` — change base from `Exception` to `BusinessLogicError`. Preserve the custom `__init__` signature: `(self, conflicts: list[tuple[str, str, str]])`.

In each source module, replace the class definition with an import:
```python
from promptgrimoire.db.exceptions import DuplicateNameError  # etc.
```

**Verification:**

```bash
# Verify all 10 exceptions are BusinessLogicError subclasses
uv run python -c "
from promptgrimoire.db.exceptions import (
    BusinessLogicError, SharePermissionError, OwnershipError,
    TagCreationDeniedError, DeletionBlockedError, ProtectedDocumentError,
    DuplicateNameError, DuplicateCodenameError, ZeroEditorError,
    DuplicateEnrollmentError, StudentIdConflictError,
)
for cls in [SharePermissionError, OwnershipError, TagCreationDeniedError,
            DeletionBlockedError, ProtectedDocumentError, DuplicateNameError,
            DuplicateCodenameError, ZeroEditorError, DuplicateEnrollmentError,
            StudentIdConflictError]:
    assert issubclass(cls, BusinessLogicError), f'{cls.__name__} not subclass'
# AC1.6: DuplicateNameError is no longer a ValueError
assert not issubclass(DuplicateNameError, ValueError)
print('All 10 exceptions verified as BusinessLogicError subclasses')
"

# Verify original modules still work (import from exceptions.py)
uv run python -c "from promptgrimoire.db.tags import DuplicateNameError; print('tags OK')"
uv run python -c "from promptgrimoire.db.wargames import DuplicateCodenameError, ZeroEditorError; print('wargames OK')"
uv run python -c "from promptgrimoire.db.courses import DuplicateEnrollmentError; print('courses OK')"
uv run python -c "from promptgrimoire.db.enrolment import StudentIdConflictError; print('enrolment OK')"

# Run existing tests to check nothing broke
uv run grimoire test all
```

**Commit:** `refactor: consolidate domain exceptions into db/exceptions.py under BusinessLogicError`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Replace bare PermissionError raises in db/ with named subclasses

**Verifies:** business-exception-handling-363.AC1.2, business-exception-handling-363.AC1.3, business-exception-handling-363.AC1.4, business-exception-handling-363.AC1.8

**Files:**
- Modify: `src/promptgrimoire/db/acl.py` — lines 417, 453, 456, 475
- Modify: `src/promptgrimoire/db/workspaces.py` — line 443
- Modify: `src/promptgrimoire/db/workspace_documents.py` — line 259
- Modify: `src/promptgrimoire/db/tags.py` — lines 53, 716

**Implementation:**

Add imports to each file:
- `acl.py`: `from promptgrimoire.db.exceptions import SharePermissionError`
- `workspaces.py`: `from promptgrimoire.db.exceptions import OwnershipError`
- `workspace_documents.py`: `from promptgrimoire.db.exceptions import OwnershipError`
- `tags.py`: `from promptgrimoire.db.exceptions import TagCreationDeniedError` (if not already imported from Task 2's refactor)

Replace raise statements (preserve existing error messages):
- `acl.py:417`: `raise PermissionError(...)` → `raise SharePermissionError(...)`
- `acl.py:453`: `raise PermissionError(...)` → `raise SharePermissionError(...)`
- `acl.py:456`: `raise PermissionError(...)` → `raise SharePermissionError(...)`
- `acl.py:475`: `raise PermissionError(...)` → `raise SharePermissionError(...)`
- `workspaces.py:443`: `raise PermissionError(...)` → `raise OwnershipError(...)`
- `workspace_documents.py:259`: `raise PermissionError(...)` → `raise OwnershipError(...)`
- `tags.py:53`: `raise PermissionError(...)` → `raise TagCreationDeniedError(...)`
- `tags.py:716`: `raise PermissionError(...)` → `raise TagCreationDeniedError(...)`

Use ast-grep to verify completeness after replacement:

```bash
# Must return zero matches after replacement
sg run -p 'raise PermissionError($$$)' -l py src/promptgrimoire/db/
```

**Verification:**

```bash
# Verify no bare PermissionError raises remain in db/
sg run -p 'raise PermissionError($$$)' -l py src/promptgrimoire/db/
# Expected: no output (zero matches)

# Verify new raises exist
sg run -p 'raise SharePermissionError($$$)' -l py src/promptgrimoire/db/
# Expected: 4 matches in acl.py

sg run -p 'raise OwnershipError($$$)' -l py src/promptgrimoire/db/
# Expected: 2 matches (workspaces.py, workspace_documents.py)

sg run -p 'raise TagCreationDeniedError($$$)' -l py src/promptgrimoire/db/
# Expected: 2 matches in tags.py
```

**Commit:** `refactor: replace bare PermissionError raises with named subclasses`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update UI callers and tests to catch specific exception subclasses

**Verifies:** business-exception-handling-363.AC1.5, business-exception-handling-363.AC1.7

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py` — add imports and `__all__` entries
- Modify: `src/promptgrimoire/pages/annotation/sharing.py` — line 198
- Modify: `src/promptgrimoire/pages/navigator/_cards.py` — line 223
- Modify: `src/promptgrimoire/pages/annotation/document_management.py` — line 315
- Modify: `src/promptgrimoire/pages/courses.py` — line 319
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py` — line 412
- Modify: `src/promptgrimoire/pages/annotation/tag_management_save.py` — line 137
- Modify: `src/promptgrimoire/pages/annotation/tag_import.py` — line 113
- Modify: `tests/unit/test_sharing_controls.py` — 5 sites (lines 196, 214, 232, 252, 269)
- Modify: `tests/unit/test_delete_guards.py` — 1 site (line 346)
- Modify: `tests/unit/test_tag_crud.py` — 3 sites (lines 499, 545, 2123)
- Modify: `tests/unit/test_tag_management.py` — 1 site (line 130)

**Implementation:**

**Step 1: Update `db/__init__.py` exports**

After Task 2 consolidated all exceptions into `db/exceptions.py`, the existing imports of `DuplicateCodenameError` (from `db.wargames`), `DuplicateEnrollmentError` (from `db.courses`), `StudentIdConflictError` (from `db.enrolment`), and `ZeroEditorError` (from `db.wargames`) must be updated to import from `db.exceptions` instead.

Replace all exception imports with a single consolidated import block:
```python
from promptgrimoire.db.exceptions import (
    BusinessLogicError,
    DeletionBlockedError,
    DuplicateCodenameError,
    DuplicateEnrollmentError,
    DuplicateNameError,
    OwnershipError,
    ProtectedDocumentError,
    SharePermissionError,
    StudentIdConflictError,
    TagCreationDeniedError,
    ZeroEditorError,
)
```

Remove the old individual imports of these 4 exceptions from their source modules (`db.wargames`, `db.courses`, `db.enrolment`).

Add ALL 11 exceptions to `__all__` (7 new + 4 existing that need path update):
```python
"BusinessLogicError",
"DeletionBlockedError",
"DuplicateCodenameError",
"DuplicateEnrollmentError",
"DuplicateNameError",
"OwnershipError",
"ProtectedDocumentError",
"SharePermissionError",
"StudentIdConflictError",
"TagCreationDeniedError",
"ZeroEditorError",
```

The 4 previously-exported exceptions (`DuplicateCodenameError`, `DuplicateEnrollmentError`, `StudentIdConflictError`, `ZeroEditorError`) keep their `__all__` entries — only the import source changes.

**Step 2: Update UI callers**

Each UI caller currently catches `PermissionError`. Replace with the appropriate specific subclass:

| File | Line | Calling function | Replace `PermissionError` with |
|------|------|-----------------|-------------------------------|
| `sharing.py` | 198 | `grant_share()` | `SharePermissionError` |
| `navigator/_cards.py` | 223 | `delete_workspace()` | `OwnershipError` |
| `document_management.py` | 315 | `delete_document()` | `OwnershipError` |
| `courses.py` | 319 | `delete_workspace()` | `OwnershipError` |
| `tag_management.py` | 412 | `create_tag_group()` | `TagCreationDeniedError` |
| `tag_management_save.py` | 137 | `create_tag()` | `TagCreationDeniedError` |
| `tag_import.py` | 113 | `import_tags_from_workspace()` | `TagCreationDeniedError` |

Each file needs an import: `from promptgrimoire.db import SharePermissionError` (or `OwnershipError`, `TagCreationDeniedError`).

**Step 3: Update test assertions**

| File | Line | Replace `PermissionError` with |
|------|------|-----------------------------|
| `test_sharing_controls.py` | 196, 214, 232, 252, 269 | `SharePermissionError` |
| `test_delete_guards.py` | 346 | `OwnershipError` |
| `test_tag_crud.py` | 499, 545, 2123 | `TagCreationDeniedError` |
| `test_tag_management.py` | 130 | `TagCreationDeniedError` |

Each test file needs an import from `promptgrimoire.db`.

**Testing:**

Tests must verify each AC listed above:
- business-exception-handling-363.AC1.5: `str(SharePermissionError("msg")) == "msg"` — existing tests already verify this via `match=` patterns; add explicit `str()` assertion
- business-exception-handling-363.AC1.7: All new exceptions importable from `db` package

**Verification:**

```bash
# Run full test suite — all existing tests should pass with new exception classes
uv run grimoire test all

# Verify AC1.8: no bare PermissionError in db/
sg run -p 'raise PermissionError($$$)' -l py src/promptgrimoire/db/

# Verify exports work
uv run python -c "
from promptgrimoire.db import (
    BusinessLogicError, SharePermissionError, OwnershipError,
    TagCreationDeniedError, DeletionBlockedError, ProtectedDocumentError,
    DuplicateNameError, DuplicateCodenameError, ZeroEditorError,
    DuplicateEnrollmentError, StudentIdConflictError,
)
print('All 11 exceptions importable from db package')
"
```

**Commit:** `feat: update UI callers, tests, and db exports for new exception taxonomy`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Add isinstance and taxonomy tests

**Verifies:** business-exception-handling-363.AC1.1, business-exception-handling-363.AC1.5, business-exception-handling-363.AC1.6

**Files:**
- Create: `tests/unit/test_exception_taxonomy.py`

**Testing:**

Tests must verify:
- business-exception-handling-363.AC1.1: All 10 domain exceptions are `isinstance(exc, BusinessLogicError)` — instantiate each with valid args, assert isinstance
- business-exception-handling-363.AC1.5: `str(SharePermissionError("user-facing message"))` == `"user-facing message"` — message preservation for UI display
- business-exception-handling-363.AC1.6: `DuplicateNameError` is NOT `isinstance(exc, ValueError)` — intentional reparenting

**Verification:**

```bash
uv run grimoire test run tests/unit/test_exception_taxonomy.py
uv run grimoire test all
```

**Commit:** `test: add exception taxonomy isinstance and message preservation tests`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Run complexipy on all modified files

**Files:** None (diagnostic only)

**Verification:**

```bash
uv run complexipy src/promptgrimoire/db/exceptions.py src/promptgrimoire/db/acl.py src/promptgrimoire/db/tags.py src/promptgrimoire/db/wargames.py src/promptgrimoire/db/workspaces.py src/promptgrimoire/db/workspace_documents.py src/promptgrimoire/db/courses.py src/promptgrimoire/db/enrolment.py src/promptgrimoire/db/__init__.py --max-complexity-allowed 15
```

If any function exceeds complexity 15, refactor it before proceeding. If any file's total complexity exceeds 100 or any function is in the 10-15 range, note it as at-risk.

No commit needed for this task.
<!-- END_TASK_6 -->

## UAT Steps

1. [ ] Run: `uv run python -c "from promptgrimoire.db import BusinessLogicError, SharePermissionError, OwnershipError, TagCreationDeniedError; print('imports OK')"`
2. [ ] Verify: All four new exceptions import without error
3. [ ] Run: `sg run -p 'raise PermissionError($$$)' -l py src/promptgrimoire/db/`
4. [ ] Verify: Zero matches (no bare PermissionError in db/)
5. [ ] Run: `uv run grimoire test all`
6. [ ] Verify: All tests pass (3100+ tests, 0 failures)

## Evidence Required
- [ ] Test output showing green
- [ ] ast-grep verification showing zero bare PermissionError
