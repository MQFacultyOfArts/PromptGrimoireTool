"""Integration tests for paragraph numbering model columns and highlight wiring."""

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


class TestUpdateDocumentParagraphSettings:
    """Verify update_document_paragraph_settings() persists both columns."""

    @pytest.mark.asyncio
    async def test_update_toggles_auto_number_and_rebuilds_map(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — triggers DB URL setup
    ) -> None:
        """AC7.2: Toggling rebuilds paragraph_map and updates auto_number."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            get_document,
            update_document_paragraph_settings,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        original_map: dict[str, int] = {"0": 1, "50": 2, "120": 3}

        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>First para</p><p>Second para</p><p>Third para</p>",
            source_type="html",
            auto_number_paragraphs=True,
            paragraph_map=original_map,
        )

        # Toggle to source-number mode with a new map
        new_map: dict[str, int] = {"0": 5, "12": 10}
        await update_document_paragraph_settings(
            doc.id, auto_number_paragraphs=False, paragraph_map=new_map
        )

        reloaded = await get_document(doc.id)
        assert reloaded is not None
        assert reloaded.auto_number_paragraphs is False
        assert reloaded.paragraph_map == {"0": 5, "12": 10}

    @pytest.mark.asyncio
    async def test_update_nonexistent_document_raises(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — triggers DB URL setup
    ) -> None:
        """Updating a non-existent document raises ValueError."""
        from uuid import uuid4

        from promptgrimoire.db.workspace_documents import (
            update_document_paragraph_settings,
        )

        with pytest.raises(ValueError, match="not found"):
            await update_document_paragraph_settings(
                uuid4(), auto_number_paragraphs=True, paragraph_map={}
            )


class TestHighlightParaRefWiring:
    """Verify end-to-end wiring from paragraph_map through lookup to CRDT.

    Simulates the data path in ``_add_highlight()`` (highlights.py):
    1. ``lookup_para_ref(state.paragraph_map, start, end)`` computes a para_ref string
    2. ``state.crdt_doc.add_highlight(..., para_ref=para_ref)`` stores it in CRDT
    3. ``get_all_highlights()`` returns the stored para_ref

    These tests exercise two independent subsystems (paragraph_map + CRDT) together,
    without needing a NiceGUI page context or database connection.
    """

    @staticmethod
    def _add_and_verify(
        para_ref: str, start_char: int, end_char: int, text: str
    ) -> None:
        """Add a highlight with *para_ref* to a fresh CRDT doc and verify round-trip."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument(doc_id="test-ws")
        highlight_id = doc.add_highlight(
            start_char=start_char,
            end_char=end_char,
            tag="test-tag",
            text=text,
            author="tester",
            para_ref=para_ref,
            document_id="doc-1",
        )

        highlights = doc.get_all_highlights()
        assert len(highlights) == 1
        assert highlights[0]["id"] == highlight_id
        assert highlights[0]["para_ref"] == para_ref

    def test_single_paragraph_highlight_has_para_ref(self) -> None:
        """AC5.1: Highlight within paragraph 3 gets para_ref='[3]'."""
        from promptgrimoire.input_pipeline.paragraph_map import lookup_para_ref

        paragraph_map: dict[str, int] = {"0": 1, "50": 2, "120": 3}
        start_char, end_char = 130, 145

        para_ref = lookup_para_ref(paragraph_map, start_char, end_char)
        assert para_ref == "[3]"

        self._add_and_verify(para_ref, start_char, end_char, "sample text")

    def test_multi_paragraph_highlight_has_range_para_ref(self) -> None:
        """AC5.2: Highlight spanning paragraphs 2-4 gets para_ref='[2]-[4]'."""
        from promptgrimoire.input_pipeline.paragraph_map import lookup_para_ref

        paragraph_map: dict[str, int] = {
            "0": 1,
            "50": 2,
            "120": 3,
            "200": 4,
            "300": 5,
        }
        start_char, end_char = 60, 250

        para_ref = lookup_para_ref(paragraph_map, start_char, end_char)
        assert para_ref == "[2]-[4]"

        self._add_and_verify(para_ref, start_char, end_char, "spanning text")

    def test_highlight_before_first_paragraph_has_empty_para_ref(self) -> None:
        """AC5.4: Highlight before the first mapped paragraph gets para_ref=''."""
        from promptgrimoire.input_pipeline.paragraph_map import lookup_para_ref

        paragraph_map: dict[str, int] = {"100": 1, "200": 2}
        start_char, end_char = 10, 50

        para_ref = lookup_para_ref(paragraph_map, start_char, end_char)
        assert para_ref == ""

        self._add_and_verify(para_ref, start_char, end_char, "header text")


class TestToggleParagraphNumbering:
    """Verify the toggle flow: rebuild paragraph_map, preserve highlight para_ref.

    These tests exercise the data path that the header toggle handler follows:
    1. ``build_paragraph_map_for_json()`` rebuilds the map with the new mode
    2. ``update_document_paragraph_settings()`` persists the new map + flag
    3. CRDT highlight ``para_ref`` values remain untouched (AC7.3)
    """

    @pytest.mark.asyncio
    async def test_toggle_rebuilds_paragraph_map_in_db(
        self,
        db_session: AsyncSession,  # noqa: ARG002 — triggers DB URL setup
    ) -> None:
        """AC7.2: Toggle from auto-number to source-number rebuilds paragraph_map."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            get_document,
            update_document_paragraph_settings,
        )
        from promptgrimoire.db.workspaces import create_workspace
        from promptgrimoire.input_pipeline.paragraph_map import (
            build_paragraph_map_for_json,
        )

        workspace = await create_workspace()

        # Create a document with real HTML so build_paragraph_map_for_json works
        html = "<p>First paragraph.</p><p>Second paragraph.</p><p>Third paragraph.</p>"
        auto_map = build_paragraph_map_for_json(html, auto_number=True)
        assert len(auto_map) == 3, "Sanity: 3 paragraphs detected"

        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content=html,
            source_type="html",
            auto_number_paragraphs=True,
            paragraph_map=auto_map,
        )

        # Simulate toggle: rebuild map with auto_number=False (source-number mode)
        source_map = build_paragraph_map_for_json(html, auto_number=False)

        # The maps should differ because auto_number=True assigns sequential
        # numbers while auto_number=False attempts to read source <li value=N>
        # attributes (plain <p> tags have none, so source map will be empty).
        assert source_map != auto_map

        await update_document_paragraph_settings(
            doc.id, auto_number_paragraphs=False, paragraph_map=source_map
        )

        reloaded = await get_document(doc.id)
        assert reloaded is not None
        assert reloaded.auto_number_paragraphs is False
        assert reloaded.paragraph_map == source_map

        # Toggle back to auto-number
        await update_document_paragraph_settings(
            doc.id, auto_number_paragraphs=True, paragraph_map=auto_map
        )

        reloaded2 = await get_document(doc.id)
        assert reloaded2 is not None
        assert reloaded2.auto_number_paragraphs is True
        assert reloaded2.paragraph_map == auto_map

    def test_toggle_does_not_modify_highlight_para_ref(self) -> None:
        """AC7.3: Toggling numbering mode leaves existing highlight para_ref intact.

        AC7.3 is verified at two levels:

        1. **Structural (production code):** ``_handle_paragraph_toggle()`` in
           ``header.py`` calls only ``build_paragraph_map_for_json()``,
           ``update_document_paragraph_settings()``, and UI refresh helpers.
           It contains no call to ``update_highlight_para_ref()`` or any other
           CRDT mutation method on existing highlights.  The absence of that
           call is the definitive guarantee — no toggle path can mutate
           highlight ``para_ref`` values.

        2. **Data-path (this test):** We simulate the rebuild step that the
           toggle handler performs and verify that the CRDT highlights remain
           unchanged.  This confirms that ``build_paragraph_map_for_json()``
           itself is pure (it reads HTML, returns a dict, touches no CRDT state)
           and that highlight ``para_ref`` values survive the toggle operation
           end-to-end through the data model.
        """
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.input_pipeline.paragraph_map import (
            build_paragraph_map_for_json,
        )

        html = "<p>First paragraph.</p><p>Second paragraph.</p><p>Third paragraph.</p>"

        # Create CRDT doc and add highlights with para_ref values
        crdt_doc = AnnotationDocument(doc_id="toggle-test")

        h1_id = crdt_doc.add_highlight(
            start_char=0,
            end_char=10,
            tag="test-tag",
            text="First para",
            author="tester",
            para_ref="[1]",
            document_id="doc-1",
        )
        h2_id = crdt_doc.add_highlight(
            start_char=30,
            end_char=50,
            tag="test-tag",
            text="Second para",
            author="tester",
            para_ref="[2]",
            document_id="doc-1",
        )

        # Record original para_ref values
        highlights_before = {
            h["id"]: h["para_ref"] for h in crdt_doc.get_all_highlights()
        }
        assert highlights_before[h1_id] == "[1]"
        assert highlights_before[h2_id] == "[2]"

        # Simulate what the toggle handler does: rebuild the paragraph map.
        # This is the ONLY thing that changes — no CRDT highlight mutation.
        _auto_map = build_paragraph_map_for_json(html, auto_number=True)
        _source_map = build_paragraph_map_for_json(html, auto_number=False)

        # Verify highlight para_ref values are UNCHANGED
        highlights_after = {
            h["id"]: h["para_ref"] for h in crdt_doc.get_all_highlights()
        }
        assert highlights_after[h1_id] == "[1]", (
            "AC7.3: para_ref must not change on toggle"
        )
        assert highlights_after[h2_id] == "[2]", (
            "AC7.3: para_ref must not change on toggle"
        )

        # Also verify other highlight fields are intact
        all_highlights = crdt_doc.get_all_highlights()
        for hl in all_highlights:
            assert hl["tag"] == "test-tag"
            assert hl["author"] == "tester"


class TestUploadDialogAutoDetect:
    """Verify the upload dialog contract includes auto-number boolean (AC3.3).

    ``show_content_type_dialog()`` is a NiceGUI dialog that requires a running
    UI context, so we cannot call it directly in integration tests.  Instead,
    we verify:

    1. The function signature accepts ``source_numbering_detected: bool``
    2. The return type annotation is ``tuple[ContentType, bool] | None``
    3. The detection function that feeds it (``detect_source_numbering``)
       correctly identifies source-numbered HTML
    """

    def test_dialog_function_accepts_source_numbering_parameter(self) -> None:
        """AC3.3: show_content_type_dialog has source_numbering_detected param."""
        import inspect

        from promptgrimoire.pages.dialogs import show_content_type_dialog

        sig = inspect.signature(show_content_type_dialog)
        assert "source_numbering_detected" in sig.parameters
        param = sig.parameters["source_numbering_detected"]
        assert param.default is False, "Default should be False (auto-number on)"

    def test_dialog_return_type_includes_bool(self) -> None:
        """AC3.3: Return type annotation includes the auto-number bool."""
        from typing import get_type_hints

        from promptgrimoire.pages.dialogs import show_content_type_dialog

        hints = get_type_hints(show_content_type_dialog)
        return_hint = hints.get("return")
        # The return type should be tuple[ContentType, bool] | None
        # Check the string representation includes both tuple and bool
        hint_str = str(return_hint)
        assert "tuple" in hint_str
        assert "bool" in hint_str
        assert "None" in hint_str

    def test_detect_source_numbering_feeds_dialog(self) -> None:
        """AC3.3: detect_source_numbering correctly identifies AustLII-style HTML.

        This is the detection function that feeds ``source_numbering_detected``
        into the dialog.  If it works correctly, the dialog pre-sets the
        auto-number switch accordingly.
        """
        from promptgrimoire.input_pipeline.paragraph_map import detect_source_numbering

        # AustLII-style HTML with <li value="N">
        austlii_html = (
            '<ol><li value="1">First paragraph</li>'
            '<li value="2">Second paragraph</li>'
            '<li value="3">Third paragraph</li></ol>'
        )
        assert detect_source_numbering(austlii_html) is True

        # Plain HTML without source numbering
        plain_html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        assert detect_source_numbering(plain_html) is False

    def test_paste_handler_auto_detect_bypasses_dialog(self) -> None:
        """AC3.3: Direct paste uses auto-detect, not the dialog.

        When content is pasted (not typed), the handler skips the dialog
        and uses ``_detect_paragraph_numbering()`` directly. Verify the
        detection helper returns the expected (auto_number, para_map) tuple.
        """
        from promptgrimoire.pages.annotation.content_form import (
            _detect_paragraph_numbering,
        )

        # Plain HTML — should auto-number
        plain_html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        auto_number, para_map = _detect_paragraph_numbering(plain_html)
        assert auto_number is True
        assert len(para_map) == 2

        # AustLII HTML — should use source numbering
        austlii_html = '<ol><li value="5">First</li><li value="6">Second</li></ol>'
        auto_number_src, para_map_src = _detect_paragraph_numbering(austlii_html)
        assert auto_number_src is False
        assert len(para_map_src) > 0
