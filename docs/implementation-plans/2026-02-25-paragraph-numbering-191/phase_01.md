# Paragraph Numbering Implementation Plan — Phase 1: Data Model and Migration

**Goal:** Add paragraph numbering columns to `WorkspaceDocument` and migrate existing data.

**Architecture:** Two new columns on `WorkspaceDocument`: a boolean controlling numbering mode and a JSON dict storing the char-offset-to-paragraph-number mapping. Migration sets safe defaults for existing rows.

**Tech Stack:** SQLModel, Alembic, PostgreSQL JSON

**Scope:** Phase 1 of 7 from original design

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase is infrastructure — no ACs are directly tested here. The model and migration provide the foundation for all subsequent phases.

**Verifies:** None (infrastructure phase — verified operationally)

---

<!-- START_TASK_1 -->
### Task 1: Add columns to WorkspaceDocument model

**Files:**
- Modify: `src/promptgrimoire/db/models.py:372-397` (WorkspaceDocument class)

**Implementation:**

Add two fields to the `WorkspaceDocument` class, after the existing `created_at` field:

```python
auto_number_paragraphs: bool = Field(
    default=True,
    sa_column=Column(sa.Boolean(), nullable=False, server_default="true"),
)
paragraph_map: dict[str, int] = Field(
    default_factory=dict,
    sa_column=Column(sa.JSON(), nullable=False, server_default="{}"),
)
```

**Key details:**
- `auto_number_paragraphs`: `True` = auto-number mode (default for new documents), `False` = source-number mode (AustLII documents with `<li value>` attributes).
- `paragraph_map`: Maps char-offset (as string key — JSON coerces int keys to strings) to paragraph number. Empty dict `{}` is the safe default for documents without a computed map.
- The `dict[str, int]` type annotation reflects what SQLModel actually returns after JSON round-trip (string keys). Consumers use `int(key)` for lookups.
- `server_default` values ensure existing rows get valid defaults during migration without application code.
- Both fields follow the existing `search_dirty` pattern at models.py:349-354 (`server_default` string for backward compat).

**Verification:**

```bash
uvx ty check
```

Expected: No type errors related to new fields.

**Commit:** `feat: add paragraph numbering fields to WorkspaceDocument model`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Alembic migration

**Files:**
- Create: `alembic/versions/<auto>_add_paragraph_numbering_columns.py`

**Implementation:**

Generate the migration:

```bash
cd /home/brian/people/Brian/PromptGrimoireTool/.worktrees/paragraph-numbering-191
uv run alembic revision --autogenerate -m "add paragraph numbering columns"
```

Verify the generated migration contains two `op.add_column()` calls for `workspace_document`:
- `auto_number_paragraphs` — `sa.Boolean(), nullable=False, server_default=sa.text("true")`
- `paragraph_map` — `sa.JSON(), nullable=False, server_default=sa.text("'{}'")`

The `downgrade()` should contain two `op.drop_column()` calls.

**Review the generated migration** — Alembic autogenerate may need manual adjustment:
- Ensure `server_default` uses `sa.text()` wrapper (e.g., `server_default=sa.text("true")`, `server_default=sa.text("'{}'")`)
- Ensure `nullable=False` is set on both columns
- Ensure the revision chain links correctly to the current head

**Verification:**

```bash
uv run alembic upgrade head
```

Expected: Migration applies cleanly. No errors.

```bash
uv run alembic downgrade -1 && uv run alembic upgrade head
```

Expected: Downgrade and re-upgrade both succeed cleanly.

**Commit:** `feat: add Alembic migration for paragraph numbering columns`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify model round-trip

**Files:**
- Test: `tests/integration/test_paragraph_numbering.py`

**Implementation:**

Write a minimal integration test confirming the new columns survive a database round-trip via SQLModel. This test verifies the migration worked and the model is correctly wired.

```python
"""Integration tests for paragraph numbering model columns."""

from __future__ import annotations

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestWorkspaceDocumentParagraphFields:
    """Verify paragraph numbering columns round-trip through the database."""

    @pytest.mark.asyncio
    async def test_defaults_on_new_document(self, db_session: AsyncSession) -> None:
        """New WorkspaceDocument gets auto_number_paragraphs=True and empty paragraph_map."""
        # Create a WorkspaceDocument with only required fields (no paragraph args)
        # Use add_document() or direct model instantiation + session.add()
        # Flush, then reload by ID via session.get()
        # Assert: doc.auto_number_paragraphs is True
        # Assert: doc.paragraph_map == {}

    @pytest.mark.asyncio
    async def test_paragraph_map_round_trip(self, db_session: AsyncSession) -> None:
        """paragraph_map dict survives JSON serialisation round-trip with string keys."""
        # Create WorkspaceDocument with paragraph_map={"0": 1, "50": 2, "120": 3}
        # Flush, then reload by ID
        # Assert: doc.paragraph_map == {"0": 1, "50": 2, "120": 3}
        # Assert: all keys are strings (JSON coercion)
        # Assert: all values are ints

    @pytest.mark.asyncio
    async def test_source_number_mode(self, db_session: AsyncSession) -> None:
        """auto_number_paragraphs=False persists correctly."""
        # Create WorkspaceDocument with auto_number_paragraphs=False
        # Flush, then reload by ID
        # Assert: doc.auto_number_paragraphs is False
```

Follow the existing pattern from `tests/integration/test_workspace_crud.py` — class-based organisation, `db_session` fixture, skip guard.

**Verification:**

```bash
uv run pytest tests/integration/test_paragraph_numbering.py -v
```

Expected: All 3 tests pass.

**Commit:** `test: add integration tests for paragraph numbering model columns`
<!-- END_TASK_3 -->

---

## UAT Steps

1. [ ] Run migration: `uv run alembic upgrade head` — completes without errors
2. [ ] Verify downgrade/upgrade cycle: `uv run alembic downgrade -1 && uv run alembic upgrade head`
3. [ ] Run integration tests: `uv run pytest tests/integration/test_paragraph_numbering.py -v` — all 3 pass
4. [ ] Start the app: `uv run python -m promptgrimoire`
5. [ ] Open an existing workspace — no errors, no visible change (paragraph_map is empty for existing docs)

## Evidence Required
- [ ] Test output showing 3 green tests
- [ ] Migration upgrade/downgrade output clean
