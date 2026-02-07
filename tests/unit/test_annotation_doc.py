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
            start_char=0,
            end_char=5,
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
            start_char=0,
            end_char=5,
            tag="jurisdiction",
            text="test text",
            author="TestAuthor",
        )

        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["para_ref"] == ""


class TestTagOrder:
    """Tests for tag_order operations."""

    def test_get_tag_order_empty_tag(self) -> None:
        """get_tag_order returns empty list for unknown tag."""
        doc = AnnotationDocument("test-doc")

        assert doc.get_tag_order("nonexistent") == []

    def test_set_and_get_tag_order(self) -> None:
        """set_tag_order stores IDs; get_tag_order retrieves them."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_order("jurisdiction", ["h1", "h2", "h3"])

        assert doc.get_tag_order("jurisdiction") == ["h1", "h2", "h3"]

    def test_set_tag_order_replaces_existing(self) -> None:
        """Setting tag_order again replaces the previous order."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_order("jurisdiction", ["h1", "h2"])
        doc.set_tag_order("jurisdiction", ["h3", "h1"])

        assert doc.get_tag_order("jurisdiction") == ["h3", "h1"]

    def test_move_highlight_to_tag_appends(self) -> None:
        """move_highlight_to_tag removes from source, appends to target."""
        doc = AnnotationDocument("test-doc")
        h1 = doc.add_highlight(0, 5, "issue", "text", "author")
        h2 = doc.add_highlight(6, 10, "issue", "more", "author")
        h3 = doc.add_highlight(11, 15, "facts", "data", "author")
        doc.set_tag_order("issue", [h1, h2])
        doc.set_tag_order("facts", [h3])

        result = doc.move_highlight_to_tag(h2, from_tag="issue", to_tag="facts")

        assert result is True
        assert doc.get_tag_order("issue") == [h1]
        assert doc.get_tag_order("facts") == [h3, h2]

    def test_move_highlight_to_tag_at_position(self) -> None:
        """move_highlight_to_tag inserts at the given position."""
        doc = AnnotationDocument("test-doc")
        h1 = doc.add_highlight(0, 5, "facts", "a", "author")
        h2 = doc.add_highlight(6, 10, "facts", "b", "author")
        h3 = doc.add_highlight(11, 15, "issue", "c", "author")
        doc.set_tag_order("facts", [h1, h2])
        doc.set_tag_order("issue", [h3])

        doc.move_highlight_to_tag(h3, from_tag="issue", to_tag="facts", position=1)

        assert doc.get_tag_order("facts") == [h1, h3, h2]
        assert doc.get_tag_order("issue") == []

    def test_move_highlight_to_tag_updates_highlight_tag(self) -> None:
        """move_highlight_to_tag updates the highlight's tag field."""
        doc = AnnotationDocument("test-doc")
        h1 = doc.add_highlight(0, 5, "old_tag", "text", "author")
        doc.set_tag_order("old_tag", [h1])

        doc.move_highlight_to_tag(h1, from_tag="old_tag", to_tag="new_tag")

        hl = doc.get_highlight(h1)
        assert hl is not None
        assert hl["tag"] == "new_tag"

    def test_move_highlight_to_tag_nonexistent_highlight(self) -> None:
        """move_highlight_to_tag returns False for nonexistent highlight."""
        doc = AnnotationDocument("test-doc")

        result = doc.move_highlight_to_tag(
            "nonexistent-id", from_tag=None, to_tag="facts"
        )

        assert result is False

    def test_tag_order_syncs_between_docs(self) -> None:
        """tag_order changes sync via CRDT updates."""
        doc1 = AnnotationDocument("test-doc")
        doc2 = AnnotationDocument("test-doc")

        # Sync initial state
        doc2.apply_update(doc1.get_full_state())

        # Set tag order in doc1
        doc1.set_tag_order("jurisdiction", ["h1", "h2", "h3"])
        update = doc1.doc.get_update()

        # Apply to doc2
        doc2.apply_update(update)

        assert doc2.get_tag_order("jurisdiction") == ["h1", "h2", "h3"]
