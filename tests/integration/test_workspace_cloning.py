"""Tests for workspace cloning (clone_workspace_from_activity).

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.

Tests verify document cloning: field preservation, UUID independence,
template immutability, and edge cases. Also verifies CRDT state cloning
with document ID remapping, comment preservation, and client metadata exclusion.
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


class TestCloneCRDT:
    """Tests for CRDT state cloning in clone_workspace_from_activity.

    Verifies highlight remapping (AC4.6), field preservation (AC4.7),
    comment cloning (AC4.8), client metadata exclusion (AC4.9),
    null state handling (AC4.10), and atomicity (AC4.11).
    """

    @pytest.mark.asyncio
    async def test_cloned_highlights_reference_new_document_uuids(self) -> None:
        """Cloned highlights have document_id remapped to cloned doc UUIDs.

        Verifies AC4.6.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            save_workspace_crdt_state,
        )

        _, _, activity = await _make_activity_with_docs(num_docs=2)
        template_docs = await list_documents(activity.template_workspace_id)

        # Set up CRDT state on template with highlight referencing doc 0
        doc = AnnotationDocument("setup")
        doc.add_highlight(
            start_char=0,
            end_char=10,
            tag="jurisdiction",
            text="test text",
            author="instructor",
            document_id=str(template_docs[0].id),
        )
        await save_workspace_crdt_state(
            activity.template_workspace_id, doc.get_full_state()
        )

        # Clone
        clone, doc_id_map = await clone_workspace_from_activity(activity.id)

        # Load clone CRDT state
        assert clone.crdt_state is not None
        clone_doc = AnnotationDocument("verify")
        clone_doc.apply_update(clone.crdt_state)
        highlights = clone_doc.get_all_highlights()

        assert len(highlights) == 1
        # The highlight's document_id should be the CLONED doc UUID
        expected_doc_id = str(doc_id_map[template_docs[0].id])
        assert highlights[0]["document_id"] == expected_doc_id
        # And NOT the template doc UUID
        assert highlights[0]["document_id"] != str(template_docs[0].id)

    @pytest.mark.asyncio
    async def test_highlight_fields_preserved(self) -> None:
        """Cloned highlights preserve start_char, end_char, tag, text, author, para_ref.

        Verifies AC4.7.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            save_workspace_crdt_state,
        )

        _, _, activity = await _make_activity_with_docs(num_docs=1)
        template_docs = await list_documents(activity.template_workspace_id)

        # Add highlight with specific field values
        doc = AnnotationDocument("setup")
        doc.add_highlight(
            start_char=10,
            end_char=50,
            tag="jurisdiction",
            text="sample text",
            author="instructor",
            para_ref="[3]",
            document_id=str(template_docs[0].id),
        )
        await save_workspace_crdt_state(
            activity.template_workspace_id, doc.get_full_state()
        )

        clone, _doc_map = await clone_workspace_from_activity(activity.id)

        assert clone.crdt_state is not None
        clone_doc = AnnotationDocument("verify")
        clone_doc.apply_update(clone.crdt_state)
        highlights = clone_doc.get_all_highlights()

        assert len(highlights) == 1
        hl = highlights[0]
        assert hl["start_char"] == 10
        assert hl["end_char"] == 50
        assert hl["tag"] == "jurisdiction"
        assert hl["text"] == "sample text"
        assert hl["author"] == "instructor"
        assert hl["para_ref"] == "[3]"

    @pytest.mark.asyncio
    async def test_comments_preserved_in_clone(self) -> None:
        """Cloned highlights preserve their comments (author and text).

        Verifies AC4.8.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            save_workspace_crdt_state,
        )

        _, _, activity = await _make_activity_with_docs(num_docs=1)
        template_docs = await list_documents(activity.template_workspace_id)

        # Add highlight with 2 comments
        doc = AnnotationDocument("setup")
        hl_id = doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="legal_issues",
            text="hello",
            author="instructor",
            document_id=str(template_docs[0].id),
        )
        doc.add_comment(highlight_id=hl_id, author="student", text="First comment")
        doc.add_comment(highlight_id=hl_id, author="instructor", text="Second comment")
        await save_workspace_crdt_state(
            activity.template_workspace_id, doc.get_full_state()
        )

        clone, _doc_map = await clone_workspace_from_activity(activity.id)

        assert clone.crdt_state is not None
        clone_doc = AnnotationDocument("verify")
        clone_doc.apply_update(clone.crdt_state)
        highlights = clone_doc.get_all_highlights()

        assert len(highlights) == 1
        comments = highlights[0].get("comments", [])
        assert len(comments) == 2
        assert comments[0]["author"] == "student"
        assert comments[0]["text"] == "First comment"
        assert comments[1]["author"] == "instructor"
        assert comments[1]["text"] == "Second comment"

    @pytest.mark.asyncio
    async def test_client_metadata_not_cloned(self) -> None:
        """Clone does not include client_meta from the template.

        Verifies AC4.9.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            save_workspace_crdt_state,
        )

        _, _, activity = await _make_activity_with_docs(num_docs=1)
        template_docs = await list_documents(activity.template_workspace_id)

        # Register a client (writes to client_meta map)
        doc = AnnotationDocument("setup")
        doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="jurisdiction",
            text="test",
            author="instructor",
            document_id=str(template_docs[0].id),
        )
        doc.register_client("client-1", "Instructor Alice")
        await save_workspace_crdt_state(
            activity.template_workspace_id, doc.get_full_state()
        )

        clone, _doc_map = await clone_workspace_from_activity(activity.id)

        assert clone.crdt_state is not None
        clone_doc = AnnotationDocument("verify")
        clone_doc.apply_update(clone.crdt_state)

        # client_meta map should be empty
        assert len(dict(clone_doc.client_meta)) == 0

    @pytest.mark.asyncio
    async def test_null_crdt_state_produces_null_clone(self) -> None:
        """Template with no CRDT state produces clone with null crdt_state.

        Verifies AC4.10.
        """
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _, _, activity = await _make_activity_with_docs(num_docs=1)
        # Do NOT set any CRDT state -- template crdt_state is None

        clone, _doc_map = await clone_workspace_from_activity(activity.id)

        assert clone.crdt_state is None

    @pytest.mark.asyncio
    async def test_clone_atomicity_with_crdt(self) -> None:
        """Clone with CRDT produces workspace, docs, and CRDT all in one transaction.

        Verifies AC4.11 (implicit via single-session design).
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            get_workspace,
            save_workspace_crdt_state,
        )

        _, _, activity = await _make_activity_with_docs(num_docs=2)
        template_docs = await list_documents(activity.template_workspace_id)

        # Add 2 highlights
        doc = AnnotationDocument("setup")
        doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="jurisdiction",
            text="text1",
            author="instructor",
            document_id=str(template_docs[0].id),
        )
        doc.add_highlight(
            start_char=10,
            end_char=20,
            tag="legal_issues",
            text="text2",
            author="instructor",
            document_id=str(template_docs[1].id),
        )
        await save_workspace_crdt_state(
            activity.template_workspace_id, doc.get_full_state()
        )

        clone, _doc_id_map = await clone_workspace_from_activity(activity.id)

        # Verify all parts are present
        ws = await get_workspace(clone.id)
        assert ws is not None
        assert ws.crdt_state is not None

        cloned_docs = await list_documents(clone.id)
        assert len(cloned_docs) == 2

        clone_doc = AnnotationDocument("verify")
        clone_doc.apply_update(ws.crdt_state)
        highlights = clone_doc.get_all_highlights()
        assert len(highlights) == 2

    @pytest.mark.asyncio
    async def test_general_notes_cloned(self) -> None:
        """General notes from template are cloned to new workspace.

        Verifies general notes cloning.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            save_workspace_crdt_state,
        )

        _, _, activity = await _make_activity_with_docs(num_docs=1)

        # Set general notes on template
        doc = AnnotationDocument("setup")
        doc.set_general_notes("Instructor notes for this activity")
        await save_workspace_crdt_state(
            activity.template_workspace_id, doc.get_full_state()
        )

        clone, _doc_map = await clone_workspace_from_activity(activity.id)

        assert clone.crdt_state is not None
        clone_doc = AnnotationDocument("verify")
        clone_doc.apply_update(clone.crdt_state)
        assert clone_doc.get_general_notes() == "Instructor notes for this activity"

    @pytest.mark.asyncio
    async def test_multiple_highlights_across_documents_remapped(self) -> None:
        """Highlights referencing different docs are each remapped correctly.

        Verifies multi-document remapping.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.workspace_documents import list_documents
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            save_workspace_crdt_state,
        )

        _, _, activity = await _make_activity_with_docs(num_docs=2)
        template_docs = await list_documents(activity.template_workspace_id)

        # Add 1 highlight per document
        doc = AnnotationDocument("setup")
        doc.add_highlight(
            start_char=0,
            end_char=10,
            tag="jurisdiction",
            text="from doc 0",
            author="instructor",
            document_id=str(template_docs[0].id),
        )
        doc.add_highlight(
            start_char=5,
            end_char=15,
            tag="legal_issues",
            text="from doc 1",
            author="instructor",
            document_id=str(template_docs[1].id),
        )
        await save_workspace_crdt_state(
            activity.template_workspace_id, doc.get_full_state()
        )

        clone, doc_id_map = await clone_workspace_from_activity(activity.id)

        assert clone.crdt_state is not None
        clone_doc = AnnotationDocument("verify")
        clone_doc.apply_update(clone.crdt_state)
        highlights = clone_doc.get_all_highlights()

        assert len(highlights) == 2

        # Build a lookup by text to match highlights to their expected doc
        hl_by_text = {h["text"]: h for h in highlights}
        assert hl_by_text["from doc 0"]["document_id"] == str(
            doc_id_map[template_docs[0].id]
        )
        assert hl_by_text["from doc 1"]["document_id"] == str(
            doc_id_map[template_docs[1].id]
        )
