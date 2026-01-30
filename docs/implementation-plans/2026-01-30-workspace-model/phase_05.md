# Workspace Model Implementation Plan - Phase 5: Teardown

**Goal:** Remove the old annotation system (`/demo/live-annotation`, `AnnotationDocumentState`). Complete migration to workspace model.

**Architecture:** Destructive changes - removes old routes, tables, and code paths. Point of no return.

**Tech Stack:** Alembic (migration), pytest

**Scope:** 5 phases from original design (this is phase 5 of 5 - FINAL)

**Codebase verified:** 2026-01-31

**Design document:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/93-workspace-model/docs/design-plans/2026-01-30-workspace-model.md`

---

## UAT: Falsifiable Statement

> The codebase has no references to `AnnotationDocumentState` or `/demo/live-annotation`. The full test suite passes. The workspace model is the only annotation system.

**How to verify:**
1. Run: `grep -r "AnnotationDocumentState" src/` returns no results
2. Run: `grep -r "live-annotation" src/` returns no results (except possibly redirects)
3. Run: `uv run pytest -v` passes
4. Navigate to `/demo/live-annotation` returns 404 or redirects to `/annotation`

---

## ⚠️ WARNING: DESTRUCTIVE PHASE

**Before proceeding, ensure:**
1. Phase 4 verification is complete (all checks passed)
2. All existing data has been migrated (if needed)
3. Stakeholders are aware old URLs will break
4. Backup of database exists

**This phase:**
- Drops the `annotation_document_state` table (DATA LOSS)
- Removes the `/demo/live-annotation` route (BREAKING CHANGE)
- Removes old persistence code paths

---

<!-- START_TASK_1 -->
## Task 1: Create Alembic migration to drop annotation_document_state table

**Files:**
- Create: `alembic/versions/XXXX_drop_annotation_document_state.py`

**Step 1: Generate migration**

```bash
uv run alembic revision -m "drop_annotation_document_state_table"
```

**Step 2: Edit migration**

```python
"""drop_annotation_document_state_table

Revision ID: <generated>
Revises: <previous_migration>
Create Date: <generated>

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "<generated>"
down_revision: str | Sequence[str] | None = "<previous>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the old annotation_document_state table."""
    op.drop_table("annotation_document_state")


def downgrade() -> None:
    """Recreate annotation_document_state table.

    WARNING: This does not restore data.
    """
    op.create_table(
        "annotation_document_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=255), nullable=False),
        sa.Column("crdt_state", sa.LargeBinary(), nullable=True),
        sa.Column("highlight_count", sa.Integer(), nullable=False),
        sa.Column("last_editor", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id"),
    )
    op.create_index(
        "ix_annotation_document_state_case_id",
        "annotation_document_state",
        ["case_id"],
    )
```

**Step 3: Verify migration (DRY RUN first)**

```bash
# Check current state
uv run alembic current

# Show SQL without executing
uv run alembic upgrade head --sql
```

**Step 4: Apply migration**

```bash
uv run alembic upgrade head
```

**Step 5: Verify table dropped**

```sql
\dt annotation_document_state
-- Should return: Did not find any relation named "annotation_document_state"
```

**Step 6: Commit**

```bash
git add alembic/versions/*drop_annotation_document_state*.py
git commit -m "migration: drop annotation_document_state table

BREAKING: Old annotation data is no longer accessible.
Workspace model is now the only persistence mechanism."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Remove db/annotation_state.py module

**Files:**
- Delete: `src/promptgrimoire/db/annotation_state.py`
- Modify: `src/promptgrimoire/db/__init__.py` (remove exports)
- Modify: `src/promptgrimoire/db/models.py` (remove AnnotationDocumentState)
- Delete/Modify: `tests/integration/test_db_async.py` (remove annotation_state tests)

**Step 1: Remove imports from db/__init__.py**

Remove these lines:
```python
from promptgrimoire.db.annotation_state import (
    get_state_by_case_id,
    save_state,
)
```

Remove from `__all__`:
```python
    "AnnotationDocumentState",
    "get_state_by_case_id",
    "save_state",
```

**Step 2: Remove AnnotationDocumentState from models.py**

Delete the `AnnotationDocumentState` class (approximately lines 83-98).

**Step 3: Delete annotation_state.py**

```bash
rm src/promptgrimoire/db/annotation_state.py
```

**Step 4: Update or delete tests**

Option A: Delete old tests
```bash
rm tests/integration/test_db_async.py  # If only annotation_state tests
```

Option B: Update tests to remove annotation_state tests
- Remove any test classes/functions that test `get_state_by_case_id` or `save_state`

**Step 5: Verify no import errors**

```bash
uv run python -c "from promptgrimoire.db import *"
```

**Step 6: Commit**

```bash
git rm src/promptgrimoire/db/annotation_state.py
git add src/promptgrimoire/db/__init__.py src/promptgrimoire/db/models.py
git add tests/  # Updated/deleted tests
git commit -m "refactor(db): remove AnnotationDocumentState

- Delete db/annotation_state.py
- Remove model from db/models.py
- Remove exports from db/__init__.py
- Update tests"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
## Task 3: Remove old CRDT persistence code paths

**Files:**
- Modify: `src/promptgrimoire/crdt/persistence.py`
- Modify: `src/promptgrimoire/crdt/annotation_doc.py`

**Step 1: Update PersistenceManager**

In `persistence.py`, remove:
- `mark_dirty(doc_id)` method (old case_id-based)
- `_schedule_debounced_save(doc_id)` method
- `_debounced_save(doc_id)` method
- `_persist(doc_id)` method
- `force_persist(doc_id)` method
- `_dirty_docs` dict
- `_pending_saves` dict
- `_last_editors` dict

Keep only workspace-aware methods:
- `mark_dirty_workspace(workspace_id, doc_id, last_editor)`
- `force_persist_workspace(workspace_id)`
- `persist_all_dirty_workspaces()`
- Related private methods

**Step 2: Update AnnotationDocumentRegistry**

In `annotation_doc.py`, remove:
- `get_or_create_with_persistence(doc_id)` method (old case_id-based)

Keep only:
- `get_or_create(doc_id)` (in-memory only)
- `get_or_create_for_workspace(workspace_id)` (workspace-based)

**Step 3: Update any callers**

Search for uses of removed methods:
```bash
grep -r "mark_dirty\|get_or_create_with_persistence" src/
```

Update any remaining callers to use workspace-aware methods.

**Step 4: Verify no references to old methods**

```bash
grep -r "case_id" src/promptgrimoire/crdt/
# Should return no results (or only in comments)
```

**Step 5: Run tests**

```bash
uv run pytest tests/unit/test_annotation_document.py tests/integration/test_workspace_persistence.py -v
```

**Step 6: Commit**

```bash
git add src/promptgrimoire/crdt/persistence.py src/promptgrimoire/crdt/annotation_doc.py
git commit -m "refactor(crdt): remove old case_id-based persistence

- Remove mark_dirty(doc_id) and related methods
- Remove get_or_create_with_persistence(doc_id)
- Workspace-aware methods are now the only persistence path"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: Remove /demo/live-annotation route

**Files:**
- Delete: `src/promptgrimoire/pages/live_annotation_demo.py`
- Modify: `src/promptgrimoire/main.py` (remove import)
- Delete/Modify: `tests/e2e/test_live_annotation.py` (if exists)

**Step 1: Remove import from main.py**

Remove:
```python
from promptgrimoire.pages import live_annotation_demo  # noqa: F401
```

**Step 2: Delete page file**

```bash
rm src/promptgrimoire/pages/live_annotation_demo.py
```

**Step 3: Optional: Add redirect**

If you want to help users find the new route, add a redirect in `main.py`:

```python
from nicegui import ui

@ui.page("/demo/live-annotation")
def old_annotation_redirect():
    ui.navigate.to("/annotation")
```

**Step 4: Delete old E2E tests**

```bash
rm tests/e2e/test_live_annotation.py  # If exists
```

Or update tests to test the redirect.

**Step 5: Verify route is gone**

```bash
uv run python -m promptgrimoire &
curl -I http://localhost:8080/demo/live-annotation
# Should return 404 or 302 redirect
```

**Step 6: Commit**

```bash
git rm src/promptgrimoire/pages/live_annotation_demo.py
git add src/promptgrimoire/main.py
git rm tests/e2e/test_live_annotation.py  # If existed
git commit -m "refactor(pages): remove /demo/live-annotation route

BREAKING: Old URL no longer works.
Use /annotation with workspace model instead."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
## Task 5: Clean up remaining references and run full verification

**Files:**
- Various (grep and clean)

**Step 1: Search for any remaining references**

```bash
# In source code
grep -r "AnnotationDocumentState" src/
grep -r "annotation_document_state" src/
grep -r "live-annotation" src/
grep -r "live_annotation" src/
grep -r "case_id" src/promptgrimoire/  # Might have valid uses elsewhere

# In tests
grep -r "AnnotationDocumentState" tests/
grep -r "annotation_document_state" tests/
grep -r "live-annotation" tests/
grep -r "live_annotation" tests/
```

**Step 2: Remove/update any found references**

For each reference found:
- If in code: Update to use workspace model
- If in tests: Update or remove test
- If in comments: Update comment or remove if obsolete
- If in docs: Update documentation

**Step 3: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests pass

**Step 4: Run type checker**

```bash
uvx ty check
```

Expected: No errors related to removed code

**Step 5: Verify grep returns nothing**

```bash
grep -r "AnnotationDocumentState\|annotation_document_state" src/ tests/
# Should return no results
```

**Step 6: Final commit**

```bash
git add -A
git commit -m "chore: clean up remaining old annotation references

Phase 5 complete. Workspace model is now the only annotation system."
```
<!-- END_TASK_5 -->

---

## Phase 5 Verification

**Automated:**
```bash
# Full test suite
uv run pytest -v

# No references to old system
grep -r "AnnotationDocumentState" src/ tests/ && echo "FAIL: Found references" || echo "PASS: No references"
grep -r "live-annotation" src/ tests/ && echo "FAIL: Found references" || echo "PASS: No references"

# Type check
uvx ty check
```

**Database:**
```sql
-- Table should not exist
\dt annotation_document_state
-- Returns: Did not find any relation
```

---

## UAT Checklist

- [ ] `annotation_document_state` table dropped (Task 1)
- [ ] `db/annotation_state.py` deleted (Task 2)
- [ ] `AnnotationDocumentState` model removed (Task 2)
- [ ] Old CRDT persistence methods removed (Task 3)
- [ ] `/demo/live-annotation` route removed (Task 4)
- [ ] No code references to old system (Task 5)
- [ ] Full test suite passes (Task 5)
- [ ] Type checker passes (Task 5)

**If all checks pass:** Phase 5 complete. Migration to workspace model is FINISHED.

---

## Post-Migration

After Phase 5 completion:

1. **Update CLAUDE.md** - Remove references to `AnnotationDocumentState`
2. **Update API docs** - If any external docs reference old system
3. **Notify stakeholders** - Old URLs no longer work
4. **Monitor logs** - Watch for 404s on old routes
5. **Consider data migration** - If any valuable data was in old system

---

## Rollback Plan

If critical issues discovered after Phase 5:

1. **Database:** Run `alembic downgrade -1` to recreate table (DATA NOT RESTORED)
2. **Code:** Revert git commits for Phase 5
3. **Data:** Restore from backup if available

Rolling back is costly. Ensure Phase 4 verification was thorough.
