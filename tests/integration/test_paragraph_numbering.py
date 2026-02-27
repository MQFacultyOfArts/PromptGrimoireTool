"""Integration tests for paragraph numbering model columns."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlmodel import select

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import Workspace, WorkspaceDocument

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _reload_document(session: AsyncSession, doc_id: UUID) -> WorkspaceDocument:
    """Re-query a WorkspaceDocument by PK to exercise a full DB round-trip."""
    result = await session.execute(
        select(WorkspaceDocument).where(WorkspaceDocument.id == doc_id)
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def workspace_id(db_session: AsyncSession) -> UUID:
    """Create a throwaway workspace and return its ID (FK target for documents)."""
    ws = Workspace()
    db_session.add(ws)
    await db_session.flush()
    return ws.id


class TestWorkspaceDocumentParagraphFields:
    """Verify paragraph numbering columns round-trip through the database."""

    @pytest.mark.asyncio
    async def test_defaults_on_new_document(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """New doc gets auto_number_paragraphs=True and empty paragraph_map."""
        doc = WorkspaceDocument(
            workspace_id=workspace_id,
            type="source",
            content="<p><span>Hello</span></p>",
            source_type="text",
        )
        db_session.add(doc)
        await db_session.commit()

        reloaded = await _reload_document(db_session, doc.id)

        assert reloaded.auto_number_paragraphs is True
        assert reloaded.paragraph_map == {}

    @pytest.mark.asyncio
    async def test_paragraph_map_round_trip(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """paragraph_map survives JSON round-trip with string keys."""
        test_map: dict[str, int] = {"0": 1, "50": 2, "120": 3}
        doc = WorkspaceDocument(
            workspace_id=workspace_id,
            type="source",
            content="<p><span>Test</span></p>",
            source_type="text",
            paragraph_map=test_map,
        )
        db_session.add(doc)
        await db_session.commit()

        reloaded = await _reload_document(db_session, doc.id)

        assert reloaded.paragraph_map == {"0": 1, "50": 2, "120": 3}
        assert all(isinstance(k, str) for k in reloaded.paragraph_map)
        assert all(isinstance(v, int) for v in reloaded.paragraph_map.values())

    @pytest.mark.asyncio
    async def test_source_number_mode(
        self, db_session: AsyncSession, workspace_id: UUID
    ) -> None:
        """auto_number_paragraphs=False persists correctly."""
        doc = WorkspaceDocument(
            workspace_id=workspace_id,
            type="source",
            content="<p><span>AustLII doc</span></p>",
            source_type="html",
            auto_number_paragraphs=False,
        )
        db_session.add(doc)
        await db_session.commit()

        reloaded = await _reload_document(db_session, doc.id)

        assert reloaded.auto_number_paragraphs is False


class TestAddDocumentWithParagraphFields:
    """Verify add_document() persists paragraph numbering fields."""

    @pytest.mark.asyncio
    async def test_explicit_paragraph_fields_persist(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — triggers DB URL setup
    ) -> None:
        """Explicit paragraph fields persist and round-trip."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            get_document,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        test_map: dict[str, int] = {
            "0": 5,
            "42": 6,
            "110": 7,
        }

        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p><span>AustLII</span></p>",
            source_type="html",
            auto_number_paragraphs=False,
            paragraph_map=test_map,
        )

        reloaded = await get_document(doc.id)
        assert reloaded is not None
        assert reloaded.auto_number_paragraphs is False
        assert reloaded.paragraph_map == {
            "0": 5,
            "42": 6,
            "110": 7,
        }

    @pytest.mark.asyncio
    async def test_defaults_when_no_paragraph_args(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — triggers DB URL setup
    ) -> None:
        """No paragraph args gives defaults (True, {})."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            get_document,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p><span>Plain</span></p>",
            source_type="text",
        )

        reloaded = await get_document(doc.id)
        assert reloaded is not None
        assert reloaded.auto_number_paragraphs is True
        assert reloaded.paragraph_map == {}


class TestCloneParagraphFields:
    """Verify clone_workspace_from_activity propagates paragraph numbering fields."""

    @pytest.mark.asyncio
    async def test_clone_copies_auto_number_paragraphs_and_paragraph_map(
        self,
    ) -> None:
        """Cloned document inherits paragraph numbering fields from template.

        Regression test for the DBA HALT: clone function was silently dropping
        auto_number_paragraphs and paragraph_map, reverting clones to defaults.
        """
        from uuid import uuid4

        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import WorkspaceDocument
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week, publish_week
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        tag = uuid4().hex[:8]

        course = await create_course(
            code=f"C{tag[:6].upper()}", name="Para Clone Test", semester="2026-S1"
        )
        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        await publish_week(week.id)
        activity = await create_activity(week_id=week.id, title="Para Activity")

        student = await create_user(
            email=f"para-{tag}@test.local", display_name=f"Para {tag}"
        )
        await enroll_user(course_id=course.id, user_id=student.id, role="student")

        # Add a template document with non-default paragraph fields
        test_map: dict[str, int] = {"0": 1, "45": 2, "100": 3}
        async with get_session() as session:
            tmpl_doc = WorkspaceDocument(
                workspace_id=activity.template_workspace_id,
                type="source",
                content="<p><span>AustLII</span></p>",
                source_type="html",
                auto_number_paragraphs=False,
                paragraph_map=test_map,
            )
            session.add(tmpl_doc)

        # Clone the workspace
        _clone, doc_id_map = await clone_workspace_from_activity(
            activity.id, student.id
        )

        # Retrieve the cloned document and verify fields propagated
        cloned_doc_id = doc_id_map[tmpl_doc.id]
        async with get_session() as session:
            result = await session.execute(
                select(WorkspaceDocument).where(WorkspaceDocument.id == cloned_doc_id)
            )
            cloned_doc = result.scalar_one()

        assert cloned_doc.auto_number_paragraphs is False
        assert cloned_doc.paragraph_map == {"0": 1, "45": 2, "100": 3}
