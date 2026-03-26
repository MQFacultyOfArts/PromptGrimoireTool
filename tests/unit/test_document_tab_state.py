"""Tests for DocumentTabState dataclass."""

from __future__ import annotations

from uuid import uuid4

from promptgrimoire.pages.annotation.tab_state import DocumentTabState


class TestDocumentTabState:
    """DocumentTabState construction and defaults."""

    def test_requires_document_id_tab_panel(self) -> None:
        """Must supply document_id, tab, and panel."""
        doc_id = uuid4()
        state = DocumentTabState(document_id=doc_id, tab=None, panel=None)
        assert state.document_id == doc_id
        assert state.tab is None
        assert state.panel is None

    def test_defaults(self) -> None:
        """Mutable defaults are isolated and correct."""
        state = DocumentTabState(document_id=uuid4(), tab=None, panel=None)
        assert state.cards_container is None
        assert state.annotation_cards == {}
        assert state.card_snapshots == {}
        assert state.rendered is False
        assert state.cards_epoch == 0
        # Document content defaults
        assert state.document_chars is None
        assert state.paragraph_map == {}
        assert state.document_content == ""
        assert state.auto_number_paragraphs is True
        # UI element ref defaults
        assert state.doc_container is None
        assert state.highlight_style is None
        assert state.highlight_menu is None
        assert state.toolbar_container is None

    def test_mutable_default_isolation(self) -> None:
        """Each instance gets its own mutable containers."""
        a = DocumentTabState(document_id=uuid4(), tab=None, panel=None)
        b = DocumentTabState(document_id=uuid4(), tab=None, panel=None)
        a.annotation_cards["x"] = 1
        assert "x" not in b.annotation_cards
