"""Tests for workspace cloning (clone_workspace_from_activity).

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.

Tests verify document cloning: field preservation, UUID independence,
template immutability, and edge cases.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from promptgrimoire.db.models import Activity, Course, Week

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


async def _make_activity_with_docs(
    num_docs: int = 2,
) -> tuple[Course, Week, Activity]:
    """Create a Course -> Week -> Activity with template documents."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspace_documents import add_document

    code = f"C{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Clone Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Cloneable Activity")
    for i in range(num_docs):
        await add_document(
            workspace_id=activity.template_workspace_id,
            type="source",
            content=f"<p>Document {i} content</p>",
            source_type="html",
            title=f"Document {i}",
        )
    return course, week, activity


class TestCloneDocuments:
    """Tests for clone_workspace_from_activity."""

    @pytest.mark.asyncio
    async def test_clone_creates_workspace_with_activity_id_and_draft_flag(
        self,
    ) -> None:
        """Clone creates workspace with activity_id set and enable_save_as_draft copied.

        Verifies AC4.1.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity_with_docs(num_docs=1)

        # Set enable_save_as_draft=True on the template workspace
        async with get_session() as session:
            template = await session.get(Workspace, activity.template_workspace_id)
            assert template is not None
            template.enable_save_as_draft = True
            session.add(template)
            await session.flush()

        clone, _doc_map = await clone_workspace_from_activity(activity.id)

        assert clone.activity_id == activity.id
        assert clone.enable_save_as_draft is True
        assert clone.id != activity.template_workspace_id

    @pytest.mark.asyncio
    async def test_cloned_docs_preserve_fields(self) -> None:
        """Cloned documents preserve content, type, source_type, title, order_index.

        Verifies AC4.2.
        """
        from promptgrimoire.db.workspace_documents import add_document, list_documents
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity_with_docs(num_docs=0)

        # Add 2 documents with distinct field values
        await add_document(
            workspace_id=activity.template_workspace_id,
            type="source",
            content="<p>Source content alpha</p>",
            source_type="html",
            title="Alpha Source",
        )
        await add_document(
            workspace_id=activity.template_workspace_id,
            type="draft",
            content="<p>Draft content beta</p>",
            source_type="text",
            title="Beta Draft",
        )

        clone, _doc_map = await clone_workspace_from_activity(activity.id)
        cloned_docs = await list_documents(clone.id)

        assert len(cloned_docs) == 2

        # First doc
        assert cloned_docs[0].type == "source"
        assert cloned_docs[0].content == "<p>Source content alpha</p>"
        assert cloned_docs[0].source_type == "html"
        assert cloned_docs[0].title == "Alpha Source"
        assert cloned_docs[0].order_index == 0

        # Second doc
        assert cloned_docs[1].type == "draft"
        assert cloned_docs[1].content == "<p>Draft content beta</p>"
        assert cloned_docs[1].source_type == "text"
        assert cloned_docs[1].title == "Beta Draft"
        assert cloned_docs[1].order_index == 1

    @pytest.mark.asyncio
    async def test_cloned_docs_have_new_uuids(self) -> None:
        """Cloned documents have new UUIDs; doc_id_map tracks the mapping.

        Verifies AC4.3.
        """
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity_with_docs(num_docs=2)

        template_docs = await list_documents(activity.template_workspace_id)
        clone, doc_id_map = await clone_workspace_from_activity(activity.id)
        cloned_docs = await list_documents(clone.id)

        # All cloned doc IDs differ from template doc IDs
        template_ids = {d.id for d in template_docs}
        cloned_ids = {d.id for d in cloned_docs}
        assert template_ids.isdisjoint(cloned_ids)

        # doc_id_map has correct key-value pairs
        assert len(doc_id_map) == len(template_docs)
        for tmpl_doc in template_docs:
            assert tmpl_doc.id in doc_id_map
            assert doc_id_map[tmpl_doc.id] in cloned_ids

    @pytest.mark.asyncio
    async def test_original_template_unmodified(self) -> None:
        """Template workspace and documents are unchanged after clone.

        Verifies AC4.4.
        """
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            get_workspace,
        )

        _, _, activity = await _make_activity_with_docs(num_docs=2)

        # Record pre-clone state
        template_before = await get_workspace(activity.template_workspace_id)
        assert template_before is not None
        docs_before = await list_documents(activity.template_workspace_id)
        doc_count_before = len(docs_before)
        doc_fields_before = [
            (d.id, d.content, d.type, d.source_type, d.title, d.order_index)
            for d in docs_before
        ]

        # Clone
        await clone_workspace_from_activity(activity.id)

        # Verify template workspace unchanged
        template_after = await get_workspace(activity.template_workspace_id)
        assert template_after is not None
        assert template_after.crdt_state == template_before.crdt_state
        assert (
            template_after.enable_save_as_draft == template_before.enable_save_as_draft
        )

        # Verify template documents unchanged
        docs_after = await list_documents(activity.template_workspace_id)
        assert len(docs_after) == doc_count_before
        doc_fields_after = [
            (d.id, d.content, d.type, d.source_type, d.title, d.order_index)
            for d in docs_after
        ]
        assert doc_fields_after == doc_fields_before

    @pytest.mark.asyncio
    async def test_empty_template_produces_empty_workspace(self) -> None:
        """Cloning empty template creates workspace with activity_id, zero documents.

        Verifies AC4.5.
        """
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity_with_docs(num_docs=0)

        clone, doc_id_map = await clone_workspace_from_activity(activity.id)

        assert clone.activity_id == activity.id
        assert doc_id_map == {}
        cloned_docs = await list_documents(clone.id)
        assert cloned_docs == []

    @pytest.mark.asyncio
    async def test_clone_nonexistent_activity_raises(self) -> None:
        """Cloning a non-existent activity raises ValueError."""
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        with pytest.raises(ValueError, match="not found"):
            await clone_workspace_from_activity(uuid4())
