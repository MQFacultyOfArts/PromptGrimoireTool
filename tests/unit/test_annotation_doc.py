"""Unit tests for AnnotationDocument CRDT operations."""

from __future__ import annotations

from promptgrimoire.crdt.annotation_doc import AnnotationDocument


class TestGeneralNotes:
    """Tests for general_notes collaborative text field."""

    def test_general_notes_initially_empty(self) -> None:
        """New documents should have empty general notes."""
        doc = AnnotationDocument("test-doc")

        assert doc.get_general_notes() == ""

    def test_set_general_notes(self) -> None:
        """set_general_notes should update the notes content."""
        doc = AnnotationDocument("test-doc")

        doc.set_general_notes("Test notes content")

        assert doc.get_general_notes() == "Test notes content"

    def test_set_general_notes_with_origin_client(self) -> None:
        """set_general_notes should accept origin_client_id for echo prevention."""
        doc = AnnotationDocument("test-doc")
        doc.register_client("client-1", "User1")

        doc.set_general_notes("Notes from client 1", origin_client_id="client-1")

        assert doc.get_general_notes() == "Notes from client 1"

    def test_set_general_notes_replaces_content(self) -> None:
        """set_general_notes should replace existing content."""
        doc = AnnotationDocument("test-doc")

        doc.set_general_notes("First version")
        doc.set_general_notes("Second version")

        assert doc.get_general_notes() == "Second version"

    def test_general_notes_syncs_between_docs(self) -> None:
        """General notes should sync via CRDT updates."""
        doc1 = AnnotationDocument("test-doc")
        doc2 = AnnotationDocument("test-doc")

        # Get initial state to sync
        doc2.apply_update(doc1.get_full_state())

        # Update doc1
        doc1.set_general_notes("Shared notes")
        update = doc1.doc.get_update()

        # Apply to doc2
        doc2.apply_update(update)

        # Both should have same content
        assert doc2.get_general_notes() == "Shared notes"

    def test_general_notes_property_access(self) -> None:
        """general_notes property should return the Text object."""
        doc = AnnotationDocument("test-doc")

        # Property should return pycrdt Text object
        notes = doc.general_notes
        assert hasattr(notes, "__iadd__")  # Text has __iadd__ for appending


class TestHighlights:
    """Tests for highlight operations."""

    def test_add_highlight_stores_para_ref(self) -> None:
        """add_highlight should store the para_ref field."""
        doc = AnnotationDocument("test-doc")

        highlight_id = doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="jurisdiction",
            text="test text",
            author="TestAuthor",
            para_ref="[3]",
        )

        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["para_ref"] == "[3]"

    def test_add_highlight_para_ref_defaults_to_empty(self) -> None:
        """add_highlight without para_ref should default to empty string."""
        doc = AnnotationDocument("test-doc")

        highlight_id = doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="jurisdiction",
            text="test text",
            author="TestAuthor",
        )

        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["para_ref"] == ""
