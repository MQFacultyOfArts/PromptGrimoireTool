# Workspace Model Implementation Plan - Phase 1: Schema & API

**Goal:** New Workspace and WorkspaceDocument tables and API exist alongside the old system.

**Architecture:** SQLModel entities with Alembic migrations, async CRUD functions following existing patterns from `db/courses.py` and `db/users.py`. UUID-based isolation for tests.

**Tech Stack:** SQLModel, Alembic, PostgreSQL, pytest-asyncio

**Scope:** 5 phases from original design (this is phase 1 of 5)

**Codebase verified:** 2026-01-31

**Design document:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/93-workspace-model/docs/design-plans/2026-01-30-workspace-model.md`

---

## UAT: Falsifiable Statement

> The new Workspace schema can be a drop-in replacement for AnnotationDocumentState's data storage role. CRDT state saved to the old system can be copied to the new system and all AnnotationDocument operations work identically.

**How to verify (Task 7):**
1. Create highlights using AnnotationDocument API
2. Save CRDT state to OLD system (AnnotationDocumentState)
3. Copy same bytes to NEW system (Workspace.crdt_state)
4. Load from NEW system into a fresh AnnotationDocument
5. **Assert:** highlights from old and new are identical

If this test passes, the tablecloth pull works. If it fails, the schema is not apt.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
## Task 1: Create Workspace and WorkspaceDocument SQLModel entities

**Files:**
- Modify: `src/promptgrimoire/db/models.py` (add after line 98, after AnnotationDocumentState)
- Create: `tests/unit/test_workspace_models.py`
- Modify: `tests/unit/conftest.py` (add fixtures)

**Step 1: Write the failing test**

Create `tests/unit/test_workspace_models.py`:

```python
"""Unit tests for Workspace and WorkspaceDocument models."""

from __future__ import annotations

from uuid import UUID

import pytest


class TestWorkspaceModel:
    """Tests for Workspace model."""

    def test_workspace_has_default_uuid(self, make_workspace) -> None:
        """Workspace gets auto-generated UUID."""
        workspace = make_workspace()
        assert workspace.id is not None
        assert isinstance(workspace.id, UUID)

    def test_workspace_requires_created_by(self, make_workspace) -> None:
        """Workspace must have created_by user reference."""
        from uuid import uuid4

        user_id = uuid4()
        workspace = make_workspace(created_by=user_id)
        assert workspace.created_by == user_id

    def test_workspace_crdt_state_is_optional(self, make_workspace) -> None:
        """crdt_state can be None for new workspaces."""
        workspace = make_workspace()
        assert workspace.crdt_state is None

    def test_workspace_has_timestamps(self, make_workspace) -> None:
        """Workspace has created_at and updated_at."""
        workspace = make_workspace()
        assert workspace.created_at is not None
        assert workspace.updated_at is not None


class TestWorkspaceDocumentModel:
    """Tests for WorkspaceDocument model."""

    def test_document_has_default_uuid(self, make_workspace_document) -> None:
        """Document gets auto-generated UUID."""
        doc = make_workspace_document()
        assert doc.id is not None
        assert isinstance(doc.id, UUID)

    def test_document_requires_workspace_id(self, make_workspace_document) -> None:
        """Document must reference a workspace."""
        from uuid import uuid4

        workspace_id = uuid4()
        doc = make_workspace_document(workspace_id=workspace_id)
        assert doc.workspace_id == workspace_id

    def test_document_type_is_string(self, make_workspace_document) -> None:
        """Document type is a string (not enum)."""
        doc = make_workspace_document(type="source")
        assert doc.type == "source"
        assert isinstance(doc.type, str)

    def test_document_has_content_and_raw_content(self, make_workspace_document) -> None:
        """Document stores both HTML content and raw content."""
        doc = make_workspace_document(
            content="<p><span>Hello</span></p>",
            raw_content="Hello",
        )
        assert doc.content == "<p><span>Hello</span></p>"
        assert doc.raw_content == "Hello"

    def test_document_has_order_index(self, make_workspace_document) -> None:
        """Document has order_index for display ordering."""
        doc = make_workspace_document(order_index=2)
        assert doc.order_index == 2

    def test_document_title_is_optional(self, make_workspace_document) -> None:
        """Document title can be None."""
        doc = make_workspace_document(title=None)
        assert doc.title is None
```

**Step 2: Add fixtures to tests/unit/conftest.py**

Add at end of file:

```python
@pytest.fixture
def make_workspace():
    """Factory for Workspace instances (not persisted)."""
    from uuid import uuid4

    from promptgrimoire.db.models import Workspace

    def _make(created_by: UUID | None = None, **kwargs):
        return Workspace(
            created_by=created_by or uuid4(),
            **kwargs,
        )

    return _make


@pytest.fixture
def make_workspace_document():
    """Factory for WorkspaceDocument instances (not persisted)."""
    from uuid import uuid4

    from promptgrimoire.db.models import WorkspaceDocument

    def _make(
        workspace_id: UUID | None = None,
        type: str = "source",
        content: str = "",
        raw_content: str = "",
        order_index: int = 0,
        title: str | None = None,
        **kwargs,
    ):
        return WorkspaceDocument(
            workspace_id=workspace_id or uuid4(),
            type=type,
            content=content,
            raw_content=raw_content,
            order_index=order_index,
            title=title,
            **kwargs,
        )

    return _make
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_workspace_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Workspace' from 'promptgrimoire.db.models'`

**Step 4: Write minimal implementation**

Add `import sqlalchemy as sa` to the imports at the top of `src/promptgrimoire/db/models.py`.

Add to `src/promptgrimoire/db/models.py` after `AnnotationDocumentState` class (after line 98):

```python
class Workspace(SQLModel, table=True):
    """Container for documents and CRDT state. Unit of collaboration.

    Permissions are handled via ACL (Seam D). created_by is for audit trail only.

    Attributes:
        id: Primary key UUID, auto-generated.
        created_by: User who created this workspace (audit, not ownership).
        crdt_state: Serialized pycrdt state bytes for all annotations.
        created_at: Timestamp when workspace was created.
        updated_at: Timestamp when workspace was last modified.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_by: UUID = Field(
        sa_column=Column(Uuid(), ForeignKey("user.id"), nullable=False)
    )
    crdt_state: bytes | None = Field(
        default=None, sa_column=Column(sa.LargeBinary(), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )


class WorkspaceDocument(SQLModel, table=True):
    """A document within a workspace (source text, draft, AI conversation, etc.).

    Attributes:
        id: Primary key UUID, auto-generated.
        workspace_id: Foreign key to Workspace (CASCADE DELETE).
        type: Domain-defined type string ("source", "draft", "ai_conversation").
        content: HTML with word-level spans for annotation.
        raw_content: Original pasted/uploaded text.
        order_index: Display order within workspace.
        title: Optional document title.
        created_at: Timestamp when document was added.
    """

    __tablename__ = "workspace_document"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(sa_column=_cascade_fk_column("workspace.id"))
    type: str = Field(max_length=50)
    content: str = Field(sa_column=Column(sa.Text(), nullable=False))
    raw_content: str = Field(sa_column=Column(sa.Text(), nullable=False))
    order_index: int = Field(default=0)
    title: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_workspace_models.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/promptgrimoire/db/models.py tests/unit/test_workspace_models.py tests/unit/conftest.py
git commit -m "feat(db): add Workspace and WorkspaceDocument models

- Workspace: container for documents and CRDT state
- WorkspaceDocument: document within workspace with type, content, ordering
- created_by is audit-only (permissions via ACL in future seam)
- CASCADE DELETE on workspace_id FK"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Create Alembic migration for workspace table

**Files:**
- Create: `alembic/versions/XXXX_add_workspace_table.py` (revision ID generated by Alembic)

**Step 1: Generate migration**

Run: `uv run alembic revision -m "add_workspace_table"`

This creates a new migration file. Edit it to contain:

```python
"""add_workspace_table

Revision ID: <generated>
Revises: 5a677de22f52
Create Date: <generated>

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "<generated>"
# NOTE: Replace with actual latest migration ID at time of implementation
# Run: uv run alembic heads
down_revision: str | Sequence[str] | None = "<current_head>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workspace",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("crdt_state", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_created_by", "workspace", ["created_by"])
    op.create_index("ix_workspace_updated_at", "workspace", ["updated_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_workspace_updated_at", table_name="workspace")
    op.drop_index("ix_workspace_created_by", table_name="workspace")
    op.drop_table("workspace")
```

**Step 2: Verify migration applies**

Run: `uv run alembic upgrade head` (requires TEST_DATABASE_URL or DATABASE_URL)
Expected: Migration applies successfully

**Step 3: Commit**

```bash
git add alembic/versions/*add_workspace_table*.py
git commit -m "migration: add workspace table

- UUID PK, created_by FK to user
- crdt_state bytes (nullable for new workspaces)
- Indexed: created_by, updated_at"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
## Task 3: Create Alembic migration for workspace_document table

**Files:**
- Create: `alembic/versions/XXXX_add_workspace_document_table.py`

**Step 1: Generate migration**

Run: `uv run alembic revision -m "add_workspace_document_table"`

Edit the generated file:

```python
"""add_workspace_document_table

Revision ID: <generated>
Revises: <previous_migration_id from task 2>
Create Date: <generated>

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "<generated>"
down_revision: str | Sequence[str] | None = "<workspace_table_migration_id>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workspace_document",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspace.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_document_workspace_id",
        "workspace_document",
        ["workspace_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_workspace_document_workspace_id", table_name="workspace_document")
    op.drop_table("workspace_document")
```

**Step 2: Verify migration applies**

Run: `uv run alembic upgrade head`
Expected: Migration applies successfully

**Step 3: Commit**

```bash
git add alembic/versions/*add_workspace_document_table*.py
git commit -m "migration: add workspace_document table

- UUID PK, workspace_id FK with CASCADE DELETE
- type, content, raw_content, order_index, title
- Indexed: workspace_id for fast listing"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-6) -->

<!-- START_TASK_4 -->
## Task 4: Implement db/workspaces.py CRUD functions

**Files:**
- Create: `src/promptgrimoire/db/workspaces.py`
- Create: `tests/integration/test_workspace_crud.py`

**Step 1: Write the failing test**

Create `tests/integration/test_workspace_crud.py`:

```python
"""Tests for workspace CRUD operations.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set - skipping database integration tests",
    ),
    pytest.mark.xdist_group("db_integration"),
]


class TestCreateWorkspace:
    """Tests for create_workspace."""

    @pytest.mark.asyncio
    async def test_creates_workspace_with_user_reference(self) -> None:
        """Workspace is created with created_by user."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )

        workspace = await create_workspace(created_by=user.id)

        assert workspace.id is not None
        assert workspace.created_by == user.id
        assert workspace.crdt_state is None
        assert workspace.created_at is not None

    @pytest.mark.asyncio
    async def test_creates_workspace_with_unique_id(self) -> None:
        """Each workspace gets a unique UUID."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )

        ws1 = await create_workspace(created_by=user.id)
        ws2 = await create_workspace(created_by=user.id)

        assert ws1.id != ws2.id


class TestGetWorkspace:
    """Tests for get_workspace."""

    @pytest.mark.asyncio
    async def test_returns_workspace_by_id(self) -> None:
        """Returns workspace when found."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        found = await get_workspace(workspace.id)

        assert found is not None
        assert found.id == workspace.id

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_id(self) -> None:
        """Returns None when workspace not found."""
        from promptgrimoire.db.workspaces import get_workspace

        found = await get_workspace(uuid4())

        assert found is None


class TestDeleteWorkspace:
    """Tests for delete_workspace."""

    @pytest.mark.asyncio
    async def test_deletes_workspace(self) -> None:
        """Workspace is deleted."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            delete_workspace,
            get_workspace,
        )

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        await delete_workspace(workspace.id)

        found = await get_workspace(workspace.id)
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_workspace_is_noop(self) -> None:
        """Deleting nonexistent workspace doesn't raise."""
        from promptgrimoire.db.workspaces import delete_workspace

        # Should not raise
        await delete_workspace(uuid4())
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_workspace_crud.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'promptgrimoire.db.workspaces'`

**Step 3: Write minimal implementation**

Create `src/promptgrimoire/db/workspaces.py`:

```python
"""CRUD operations for Workspace.

Provides async database functions for workspace management.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Workspace

if TYPE_CHECKING:
    from uuid import UUID


async def create_workspace(created_by: UUID) -> Workspace:
    """Create a new workspace.

    Args:
        created_by: UUID of the user creating this workspace.

    Returns:
        The created Workspace with generated ID.
    """
    async with get_session() as session:
        workspace = Workspace(created_by=created_by)
        session.add(workspace)
        await session.flush()
        await session.refresh(workspace)
        return workspace


async def get_workspace(workspace_id: UUID) -> Workspace | None:
    """Get a workspace by ID.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        The Workspace or None if not found.
    """
    async with get_session() as session:
        return await session.get(Workspace, workspace_id)


async def delete_workspace(workspace_id: UUID) -> None:
    """Delete a workspace and all its documents (CASCADE).

    Args:
        workspace_id: The workspace UUID.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            await session.delete(workspace)


async def save_workspace_crdt_state(workspace_id: UUID, crdt_state: bytes) -> bool:
    """Save CRDT state to a workspace.

    Args:
        workspace_id: The workspace UUID.
        crdt_state: Serialized pycrdt state bytes.

    Returns:
        True if workspace was found and updated, False otherwise.
    """
    async with get_session() as session:
        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            workspace.crdt_state = crdt_state
            workspace.updated_at = datetime.now(UTC)
            session.add(workspace)
            return True
        return False
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_workspace_crud.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/promptgrimoire/db/workspaces.py tests/integration/test_workspace_crud.py
git commit -m "feat(db): add workspace CRUD functions

- create_workspace(created_by) -> Workspace
- get_workspace(workspace_id) -> Workspace | None
- delete_workspace(workspace_id) -> None (cascades documents)
- save_workspace_crdt_state(workspace_id, crdt_state) -> bool"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
## Task 5: Implement db/workspace_documents.py CRUD functions

**Files:**
- Create: `src/promptgrimoire/db/workspace_documents.py`
- Modify: `tests/integration/test_workspace_crud.py` (add document tests)

**Step 1: Write the failing test**

Add to `tests/integration/test_workspace_crud.py`:

```python
class TestAddDocument:
    """Tests for add_document."""

    @pytest.mark.asyncio
    async def test_adds_document_to_workspace(self) -> None:
        """Document is created in workspace."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import add_document
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p><span>Hello</span></p>",
            raw_content="Hello",
            title="My Document",
        )

        assert doc.id is not None
        assert doc.workspace_id == workspace.id
        assert doc.type == "source"
        assert doc.content == "<p><span>Hello</span></p>"
        assert doc.raw_content == "Hello"
        assert doc.title == "My Document"
        assert doc.order_index == 0

    @pytest.mark.asyncio
    async def test_auto_increments_order_index(self) -> None:
        """Documents get sequential order_index."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import add_document
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        doc1 = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="Doc 1",
            raw_content="Doc 1",
        )
        doc2 = await add_document(
            workspace_id=workspace.id,
            type="draft",
            content="Doc 2",
            raw_content="Doc 2",
        )

        assert doc1.order_index == 0
        assert doc2.order_index == 1


class TestListDocuments:
    """Tests for list_documents."""

    @pytest.mark.asyncio
    async def test_returns_documents_ordered_by_order_index(self) -> None:
        """Documents returned in order_index order."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import add_document, list_documents
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        await add_document(
            workspace_id=workspace.id,
            type="source",
            content="First",
            raw_content="First",
        )
        await add_document(
            workspace_id=workspace.id,
            type="draft",
            content="Second",
            raw_content="Second",
        )

        docs = await list_documents(workspace.id)

        assert len(docs) == 2
        assert docs[0].content == "First"
        assert docs[1].content == "Second"

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_workspace(self) -> None:
        """Returns empty list when workspace has no documents."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        docs = await list_documents(workspace.id)

        assert docs == []


class TestReorderDocuments:
    """Tests for reorder_documents."""

    @pytest.mark.asyncio
    async def test_reorders_documents(self) -> None:
        """Documents are reordered to match provided order."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_documents,
            reorder_documents,
        )
        from promptgrimoire.db.workspaces import create_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)

        doc1 = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="First",
            raw_content="First",
        )
        doc2 = await add_document(
            workspace_id=workspace.id,
            type="draft",
            content="Second",
            raw_content="Second",
        )

        # Reverse order
        await reorder_documents(workspace.id, [doc2.id, doc1.id])

        docs = await list_documents(workspace.id)
        assert docs[0].id == doc2.id
        assert docs[1].id == doc1.id


class TestCascadeDelete:
    """Tests for cascade delete behavior."""

    @pytest.mark.asyncio
    async def test_deleting_workspace_deletes_documents(self) -> None:
        """Documents are deleted when workspace is deleted."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspace_documents import add_document, list_documents
        from promptgrimoire.db.workspaces import create_workspace, delete_workspace

        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)
        workspace_id = workspace.id

        await add_document(
            workspace_id=workspace.id,
            type="source",
            content="Will be deleted",
            raw_content="Will be deleted",
        )

        await delete_workspace(workspace.id)

        # Workspace is gone, so documents must be too (CASCADE)
        docs = await list_documents(workspace_id)
        assert docs == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_workspace_crud.py::TestAddDocument -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'promptgrimoire.db.workspace_documents'`

**Step 3: Write minimal implementation**

Create `src/promptgrimoire/db/workspace_documents.py`:

```python
"""CRUD operations for WorkspaceDocument.

Provides async database functions for document management within workspaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import WorkspaceDocument

if TYPE_CHECKING:
    from uuid import UUID


async def add_document(
    workspace_id: UUID,
    type: str,
    content: str,
    raw_content: str,
    title: str | None = None,
) -> WorkspaceDocument:
    """Add a document to a workspace.

    The document gets the next order_index automatically.

    Args:
        workspace_id: The workspace UUID.
        type: Document type ("source", "draft", "ai_conversation", etc.).
        content: HTML content with word-level spans.
        raw_content: Original pasted/uploaded text.
        title: Optional document title.

    Returns:
        The created WorkspaceDocument.
    """
    async with get_session() as session:
        # Get next order_index
        result = await session.exec(
            select(func.coalesce(func.max(WorkspaceDocument.order_index), -1)).where(
                WorkspaceDocument.workspace_id == workspace_id
            )
        )
        max_index = result.one()
        next_index = max_index + 1

        doc = WorkspaceDocument(
            workspace_id=workspace_id,
            type=type,
            content=content,
            raw_content=raw_content,
            title=title,
            order_index=next_index,
        )
        session.add(doc)
        await session.flush()
        await session.refresh(doc)
        return doc


async def list_documents(workspace_id: UUID) -> list[WorkspaceDocument]:
    """List all documents in a workspace, ordered by order_index.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        List of WorkspaceDocument objects ordered by order_index.
    """
    async with get_session() as session:
        result = await session.exec(
            select(WorkspaceDocument)
            .where(WorkspaceDocument.workspace_id == workspace_id)
            .order_by(WorkspaceDocument.order_index)
        )
        return list(result.all())


async def reorder_documents(workspace_id: UUID, document_ids: list[UUID]) -> None:
    """Reorder documents in a workspace.

    Args:
        workspace_id: The workspace UUID.
        document_ids: Document UUIDs in desired order.
    """
    async with get_session() as session:
        for index, doc_id in enumerate(document_ids):
            result = await session.exec(
                select(WorkspaceDocument)
                .where(WorkspaceDocument.id == doc_id)
                .where(WorkspaceDocument.workspace_id == workspace_id)
            )
            doc = result.first()
            if doc:
                doc.order_index = index
                session.add(doc)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_workspace_crud.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/promptgrimoire/db/workspace_documents.py tests/integration/test_workspace_crud.py
git commit -m "feat(db): add workspace document CRUD functions

- add_document(workspace_id, type, content, raw_content, title?) -> WorkspaceDocument
- list_documents(workspace_id) -> list[WorkspaceDocument] (ordered)
- reorder_documents(workspace_id, document_ids) -> None"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
## Task 6: Update db/__init__.py exports

**Files:**
- Modify: `src/promptgrimoire/db/__init__.py`
- Create: `tests/unit/test_db_workspace_exports.py`

**Step 1: Write the failing test**

Create `tests/unit/test_db_workspace_exports.py`:

```python
"""Tests for workspace-related db module exports."""

from __future__ import annotations


class TestWorkspaceExports:
    """Tests that workspace functions are exported."""

    def test_workspace_model_exported(self) -> None:
        """Workspace model is exported."""
        from promptgrimoire.db import Workspace

        assert Workspace is not None

    def test_workspace_document_model_exported(self) -> None:
        """WorkspaceDocument model is exported."""
        from promptgrimoire.db import WorkspaceDocument

        assert WorkspaceDocument is not None

    def test_create_workspace_exported(self) -> None:
        """create_workspace function is exported."""
        from promptgrimoire.db import create_workspace

        assert callable(create_workspace)

    def test_get_workspace_exported(self) -> None:
        """get_workspace function is exported."""
        from promptgrimoire.db import get_workspace

        assert callable(get_workspace)

    def test_delete_workspace_exported(self) -> None:
        """delete_workspace function is exported."""
        from promptgrimoire.db import delete_workspace

        assert callable(delete_workspace)

    def test_save_workspace_crdt_state_exported(self) -> None:
        """save_workspace_crdt_state function is exported."""
        from promptgrimoire.db import save_workspace_crdt_state

        assert callable(save_workspace_crdt_state)

    def test_add_document_exported(self) -> None:
        """add_document function is exported."""
        from promptgrimoire.db import add_document

        assert callable(add_document)

    def test_list_documents_exported(self) -> None:
        """list_documents function is exported."""
        from promptgrimoire.db import list_documents

        assert callable(list_documents)

    def test_reorder_documents_exported(self) -> None:
        """reorder_documents function is exported."""
        from promptgrimoire.db import reorder_documents

        assert callable(reorder_documents)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_db_workspace_exports.py -v`
Expected: FAIL with `ImportError: cannot import name 'Workspace' from 'promptgrimoire.db'`

**Step 3: Write minimal implementation**

Update `src/promptgrimoire/db/__init__.py`:

Add these imports after line 8 (after the annotation_state import):

```python
from promptgrimoire.db.workspace_documents import (
    add_document,
    list_documents,
    reorder_documents,
)
from promptgrimoire.db.workspaces import (
    create_workspace,
    delete_workspace,
    get_workspace,
    save_workspace_crdt_state,
)
```

Update the models import (around line 29) to include Workspace and WorkspaceDocument:

```python
from promptgrimoire.db.models import (
    AnnotationDocumentState,
    Course,
    CourseEnrollment,
    CourseRole,
    User,
    Week,
    Workspace,
    WorkspaceDocument,
)
```

Add to `__all__` list (keep alphabetically sorted):

```python
    "Workspace",
    "WorkspaceDocument",
    "add_document",
    "create_workspace",
    "delete_workspace",
    "get_workspace",
    "list_documents",
    "reorder_documents",
    "save_workspace_crdt_state",
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_db_workspace_exports.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/promptgrimoire/db/__init__.py tests/unit/test_db_workspace_exports.py
git commit -m "feat(db): export workspace models and functions

Exports: Workspace, WorkspaceDocument, create_workspace, get_workspace,
delete_workspace, save_workspace_crdt_state, add_document, list_documents,
reorder_documents"
```
<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_7 -->
## Task 7: Tablecloth Pull Test - CRDT state compatibility (UAT validation)

**Files:**
- Modify: `tests/integration/test_workspace_crud.py` (add compatibility test)

**Purpose:** This test validates that the NEW schema (Workspace) can be a drop-in replacement for the OLD schema (AnnotationDocumentState). CRDT state created and saved to the old system can be loaded from the new system with identical results.

**Step 1: Write the tablecloth pull test**

Add to `tests/integration/test_workspace_crud.py`:

```python
class TestTableclothPull:
    """Test that new Workspace schema can replace AnnotationDocumentState's role.

    The "tablecloth pull" test: CRDT state saved to the OLD system works
    identically when loaded from the NEW system.
    """

    @pytest.mark.asyncio
    async def test_crdt_state_from_old_system_works_in_new_system(self) -> None:
        """Data created via AnnotationDocument works identically after transfer to Workspace."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.annotation_state import save_state
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            save_workspace_crdt_state,
        )

        # 1. Create data using the existing AnnotationDocument API
        test_case_id = f"tablecloth-test-{uuid4().hex[:8]}"
        old_doc = AnnotationDocument(test_case_id)

        # Add some highlights using the real API
        hl1_id = old_doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="First highlighted text",
            author="Test Author",
            para_ref="[1]",
        )
        hl2_id = old_doc.add_highlight(
            start_word=10,
            end_word=15,
            tag="citation",
            text="Second highlighted text",
            author="Test Author",
            para_ref="[2]",
        )

        # Add a comment to the first highlight
        old_doc.add_comment(hl1_id, author="Commenter", text="This is important")

        # Get the CRDT state bytes
        old_crdt_bytes = old_doc.get_full_state()
        old_highlights = old_doc.get_all_highlights()

        # 2. Save to OLD system (AnnotationDocumentState)
        await save_state(
            case_id=test_case_id,
            crdt_state=old_crdt_bytes,
            highlight_count=len(old_highlights),
            last_editor="Test Author",
        )

        # 3. Create NEW system workspace and store the SAME bytes
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)
        await save_workspace_crdt_state(workspace.id, old_crdt_bytes)

        # 4. Load from NEW system
        loaded_workspace = await get_workspace(workspace.id)
        assert loaded_workspace is not None
        assert loaded_workspace.crdt_state is not None

        # 5. Create a fresh AnnotationDocument and apply the state from NEW system
        new_doc = AnnotationDocument("new-doc-id")
        new_doc.apply_update(loaded_workspace.crdt_state)

        # 6. TABLECLOTH PULL ASSERTION: highlights are identical
        new_highlights = new_doc.get_all_highlights()

        assert len(new_highlights) == len(old_highlights), (
            f"Highlight count mismatch: old={len(old_highlights)}, new={len(new_highlights)}"
        )

        # Compare each highlight
        for old_hl, new_hl in zip(old_highlights, new_highlights, strict=True):
            assert old_hl["id"] == new_hl["id"], "Highlight ID mismatch"
            assert old_hl["start_word"] == new_hl["start_word"], "start_word mismatch"
            assert old_hl["end_word"] == new_hl["end_word"], "end_word mismatch"
            assert old_hl["tag"] == new_hl["tag"], "tag mismatch"
            assert old_hl["text"] == new_hl["text"], "text mismatch"
            assert old_hl["author"] == new_hl["author"], "author mismatch"
            assert old_hl["para_ref"] == new_hl["para_ref"], "para_ref mismatch"

        # Verify comments survived too
        new_hl1 = new_doc.get_highlight(hl1_id)
        assert new_hl1 is not None
        assert len(new_hl1.get("comments", [])) == 1
        assert new_hl1["comments"][0]["text"] == "This is important"

    @pytest.mark.asyncio
    async def test_bytes_are_identical_roundtrip(self) -> None:
        """CRDT state bytes are byte-identical after roundtrip through Workspace."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            save_workspace_crdt_state,
        )

        # Create document with data
        doc = AnnotationDocument("byte-test")
        doc.add_highlight(
            start_word=0,
            end_word=10,
            tag="test",
            text="Test text",
            author="Author",
        )
        original_bytes = doc.get_full_state()

        # Store in Workspace
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)
        await save_workspace_crdt_state(workspace.id, original_bytes)

        # Retrieve
        loaded = await get_workspace(workspace.id)
        assert loaded is not None

        # Byte-identical
        assert loaded.crdt_state == original_bytes, (
            f"Bytes differ: original={len(original_bytes)}, loaded={len(loaded.crdt_state)}"
        )

    @pytest.mark.asyncio
    async def test_large_crdt_state_no_truncation(self) -> None:
        """Large CRDT state with many highlights is stored without truncation."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            save_workspace_crdt_state,
        )

        # Create document with many highlights
        doc = AnnotationDocument("large-test")
        for i in range(100):
            doc.add_highlight(
                start_word=i * 10,
                end_word=i * 10 + 5,
                tag="issue" if i % 2 == 0 else "citation",
                text=f"Highlight number {i} with some longer text to increase size",
                author=f"Author {i % 5}",
                para_ref=f"[{i}]",
            )
        original_bytes = doc.get_full_state()
        original_size = len(original_bytes)
        original_highlight_count = len(doc.get_all_highlights())

        # Store in Workspace
        user = await create_user(
            email=f"test-{uuid4().hex[:8]}@example.com",
            display_name="Test User",
        )
        workspace = await create_workspace(created_by=user.id)
        await save_workspace_crdt_state(workspace.id, original_bytes)

        # Retrieve and verify no truncation
        loaded = await get_workspace(workspace.id)
        assert loaded is not None
        assert len(loaded.crdt_state) == original_size, (
            f"Size mismatch: original={original_size}, loaded={len(loaded.crdt_state)}"
        )

        # Verify all highlights intact
        loaded_doc = AnnotationDocument("loaded-large")
        loaded_doc.apply_update(loaded.crdt_state)
        loaded_highlights = loaded_doc.get_all_highlights()
        assert len(loaded_highlights) == original_highlight_count, (
            f"Highlight count: original={original_highlight_count}, loaded={len(loaded_highlights)}"
        )
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_workspace_crud.py::TestTableclothPull -v`

Expected: PASS if schema is apt, FAIL if schema cannot support the design.

**What each test proves:**
- `test_crdt_state_from_old_system_works_in_new_system`: Full tablecloth pull - old API data works identically after transfer
- `test_bytes_are_identical_roundtrip`: No encoding/corruption in storage
- `test_large_crdt_state_no_truncation`: Schema handles real workloads

**Step 3: Commit**

```bash
git add tests/integration/test_workspace_crud.py
git commit -m "test: add tablecloth pull compatibility tests

Proves Workspace schema can replace AnnotationDocumentState:
- CRDT state from old system works identically in new system
- Byte-identical roundtrip storage
- No truncation for large states (100+ highlights)
- Comments and all highlight fields preserved"
```
<!-- END_TASK_7 -->

---

## Phase 1 Verification

Run all Phase 1 tests:

```bash
uv run pytest tests/unit/test_workspace*.py tests/unit/test_db_workspace_exports.py tests/integration/test_workspace_crud.py -v
```

Expected: All tests pass

---

## UAT Checklist

- [ ] `TestTableclothPull` tests all pass (proves schema is apt for the design)
- [ ] `/demo/live-annotation` still works (no regressions to existing system)
- [ ] `\dt workspace*` in psql shows both tables
- [ ] All automated tests green

**If tablecloth tests pass:** Phase 1 foundation supports the rest of the design. Proceed to Phase 2.

**If tablecloth tests fail:** Schema is not apt. Investigate and revise before proceeding.
