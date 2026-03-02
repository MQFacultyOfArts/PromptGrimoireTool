"""Tests for document provenance tracking (source_document_id).

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify:
- AC5.1: Cloned documents have source_document_id set to template doc ID
- AC5.2: User-uploaded documents have NULL source_document_id
- AC5.3: Pre-migration documents have NULL source_document_id
- AC5.4: Deleting template source sets clones' source_document_id to NULL
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from promptgrimoire.db.models import Activity, Course, Week

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_clone_user():
    """Create a unique user for clone ownership tests."""
    from promptgrimoire.db.users import create_user

    tag = uuid4().hex[:8]
    return await create_user(
        email=f"provenance-test-{tag}@test.local",
        display_name=f"Provenance Tester {tag}",
    )


async def _make_activity_with_docs(
    num_docs: int = 2,
) -> tuple[Course, Week, Activity]:
    """Create a Course -> Week -> Activity with template documents."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspace_documents import add_document

    code = f"P{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Provenance Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Provenance Activity")
    for i in range(num_docs):
        await add_document(
            workspace_id=activity.template_workspace_id,
            type="source",
            content=f"<p>Document {i} content</p>",
            source_type="html",
            title=f"Document {i}",
        )
    return course, week, activity


class TestClonedDocumentProvenance:
    """Tests for source_document_id being set during workspace cloning."""

    @pytest.mark.asyncio
    async def test_cloned_docs_have_source_document_id_set(self) -> None:
        """Cloned docs have source_document_id set to template doc ID.

        Verifies crud-management-229.AC5.1.
        """
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity_with_docs(num_docs=2)
        user = await _make_clone_user()

        template_docs = await list_documents(activity.template_workspace_id)
        clone, doc_id_map = await clone_workspace_from_activity(activity.id, user.id)
        cloned_docs = await list_documents(clone.id)

        assert len(cloned_docs) == 2

        # Reverse the map: clone_doc_id -> template_doc_id
        reverse_map = {v: k for k, v in doc_id_map.items()}

        for cloned_doc in cloned_docs:
            expected_template_id = reverse_map[cloned_doc.id]
            assert cloned_doc.source_document_id == expected_template_id, (
                f"Cloned doc {cloned_doc.id} should have source_document_id "
                f"{expected_template_id}, got {cloned_doc.source_document_id}"
            )

        # Also verify template docs themselves have no source_document_id
        for tmpl_doc in template_docs:
            assert tmpl_doc.source_document_id is None


class TestProvenanceEdgeCases:
    """Edge case tests for source_document_id behaviour."""

    @pytest.mark.asyncio
    async def test_uploaded_document_has_null_source_document_id(
        self,
    ) -> None:
        """Documents created via add_document have NULL source_document_id.

        Verifies crud-management-229.AC5.2.
        """
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_documents,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>User uploaded content</p>",
            source_type="html",
            title="Uploaded Doc",
        )

        docs = await list_documents(workspace.id)
        assert len(docs) == 1
        assert docs[0].source_document_id is None

    @pytest.mark.asyncio
    async def test_premigration_document_has_null_source_document_id(
        self,
    ) -> None:
        """Documents without source_document_id default to NULL.

        Verifies crud-management-229.AC5.3. Same mechanism as AC5.2:
        the column is nullable with no default, so pre-migration
        rows and new rows without explicit source_document_id are NULL.
        """
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_documents,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>Pre-migration style</p>",
            source_type="html",
        )

        # Re-fetch from DB to confirm persisted value
        docs = await list_documents(workspace.id)
        fetched = next(d for d in docs if d.id == doc.id)
        assert fetched.source_document_id is None

    @pytest.mark.asyncio
    async def test_delete_template_sets_clone_source_to_null(
        self,
    ) -> None:
        """Deleting a template doc cascades SET NULL to clones.

        Verifies crud-management-229.AC5.4.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import WorkspaceDocument
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity_with_docs(num_docs=1)
        user = await _make_clone_user()

        template_docs = await list_documents(
            activity.template_workspace_id,
        )
        assert len(template_docs) == 1
        template_doc_id = template_docs[0].id

        clone, _ = await clone_workspace_from_activity(
            activity.id,
            user.id,
        )
        cloned_docs = await list_documents(clone.id)
        assert len(cloned_docs) == 1
        assert cloned_docs[0].source_document_id == template_doc_id

        # Delete the template document via session.delete()
        async with get_session() as session:
            tmpl_doc = await session.get(
                WorkspaceDocument,
                template_doc_id,
            )
            assert tmpl_doc is not None
            await session.delete(tmpl_doc)
            await session.flush()

        # Refresh the cloned doc and verify SET NULL cascade
        refreshed_docs = await list_documents(clone.id)
        assert len(refreshed_docs) == 1
        assert refreshed_docs[0].source_document_id is None
