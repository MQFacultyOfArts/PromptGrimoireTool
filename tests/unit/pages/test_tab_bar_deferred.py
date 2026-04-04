"""Unit tests for per-document tab panel deferred rendering logic.

Tests verify:
- AC2.4: Tab content renders on first visit (deferred) and persists
- AC2.1: Each source tab renders its own document HTML content

Traceability:
- Design: docs/design-plans/multi-document-tabbed-workspace.md Phase 7 Task 3
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from promptgrimoire.pages.annotation.tab_bar import (
    _is_source_tab,
    _restore_source_tab_state,
    _save_source_tab_state,
)
from promptgrimoire.pages.annotation.tab_state import DocumentTabState


class TestIsSourceTab:
    """Verify _is_source_tab identifies UUID tab names."""

    def test_uuid_string_is_source(self) -> None:
        assert _is_source_tab(str(uuid4())) is True

    def test_organise_is_not_source(self) -> None:
        assert _is_source_tab("Organise") is False

    def test_respond_is_not_source(self) -> None:
        assert _is_source_tab("Respond") is False

    def test_empty_string_is_not_source(self) -> None:
        assert _is_source_tab("") is False


class TestSaveSourceTabState:
    """_save_source_tab_state persists PageState to DocumentTabState."""

    def test_saves_document_content_fields(self) -> None:
        """Document chars, paragraph_map, and UI refs are saved."""
        doc_id = uuid4()
        doc_tab = DocumentTabState(document_id=doc_id, tab=None, panel=None)

        state = _make_mock_state(doc_id, doc_tab)
        state.document_chars = ["a", "b", "c"]
        state.paragraph_map = {"p1": 0, "p2": 10}
        state.document_content = "<p>hello</p>"
        state.doc_container = MagicMock()
        state.highlight_style = MagicMock()
        state.highlight_menu = MagicMock()
        state.toolbar_container = MagicMock()
        _save_source_tab_state(state, doc_tab)

        assert doc_tab.document_chars == ["a", "b", "c"]
        assert doc_tab.paragraph_map == {"p1": 0, "p2": 10}
        assert doc_tab.document_content == "<p>hello</p>"
        assert doc_tab.doc_container is state.doc_container
        assert doc_tab.highlight_style is state.highlight_style
        assert doc_tab.highlight_menu is state.highlight_menu
        assert doc_tab.toolbar_container is state.toolbar_container


class TestRestoreSourceTabState:
    """Verify _restore_source_tab_state loads DocumentTabState."""

    def test_restores_document_id_and_containers(self) -> None:
        """Document ID and annotations container restored."""
        doc_id = uuid4()
        mock_container = MagicMock()
        doc_tab = DocumentTabState(document_id=doc_id, tab=None, panel=None)
        doc_tab.cards_container = mock_container
        doc_tab.rendered = True

        state = _make_mock_state(doc_id, doc_tab)

        _restore_source_tab_state(state, doc_tab)

        assert state.document_id == doc_id
        assert state.annotations_container is mock_container

    def test_restores_document_content_and_ui_refs(self) -> None:
        """Document chars, paragraph_map, and UI refs are restored."""
        doc_id = uuid4()
        mock_doc_container = MagicMock()
        mock_hl_style = MagicMock()
        mock_hl_menu = MagicMock()
        mock_toolbar = MagicMock()

        doc_tab = DocumentTabState(document_id=doc_id, tab=None, panel=None)
        doc_tab.rendered = True
        doc_tab.document_chars = ["x", "y"]
        doc_tab.paragraph_map = {"p1": 5}
        doc_tab.document_content = "<p>test</p>"
        doc_tab.doc_container = mock_doc_container
        doc_tab.highlight_style = mock_hl_style
        doc_tab.highlight_menu = mock_hl_menu
        doc_tab.toolbar_container = mock_toolbar

        state = _make_mock_state(doc_id, doc_tab)
        _restore_source_tab_state(state, doc_tab)

        assert state.document_chars == ["x", "y"]
        assert state.paragraph_map == {"p1": 5}
        assert state.document_content == "<p>test</p>"
        assert state.doc_container is mock_doc_container
        assert state.highlight_style is mock_hl_style
        assert state.highlight_menu is mock_hl_menu
        assert state.toolbar_container is mock_toolbar

    def test_restores_unrendered_tab_state(self) -> None:
        """Unrendered tabs restore basic state."""
        doc_id = uuid4()
        doc_tab = DocumentTabState(document_id=doc_id, tab=None, panel=None)
        doc_tab.rendered = False

        state = _make_mock_state(doc_id, doc_tab)
        _restore_source_tab_state(state, doc_tab)

        # Vue sidebar re-renders from props — no card state
        assert state.document_id == doc_id


class TestDeferredRenderingFlags:
    """Verify deferred rendering flag management."""

    def test_new_tab_state_not_rendered(self) -> None:
        """Newly created DocumentTabState has rendered=False."""
        doc_tab = DocumentTabState(document_id=uuid4(), tab=None, panel=None)
        assert doc_tab.rendered is False

    def test_save_does_not_change_rendered_flag(self) -> None:
        """_save_source_tab_state does not alter rendered flag."""
        doc_id = uuid4()
        doc_tab = DocumentTabState(document_id=doc_id, tab=None, panel=None)
        doc_tab.rendered = False

        state = _make_mock_state(doc_id, doc_tab)

        _save_source_tab_state(state, doc_tab)

        assert doc_tab.rendered is False


# -------------------------------------------------------------------
# Test helpers
# -------------------------------------------------------------------


def _make_mock_state(doc_id, doc_tab):
    """Build a minimal mock PageState with document_tabs populated."""
    state = MagicMock()
    state.document_id = doc_id
    state.document_tabs = {doc_id: doc_tab}
    state.annotations_container = None
    # Document content fields
    state.document_chars = None
    state.paragraph_map = {}
    state.document_content = ""
    state.auto_number_paragraphs = True
    # UI element refs
    state.doc_container = None
    state.highlight_style = None
    state.highlight_menu = None
    state.toolbar_container = None
    return state
