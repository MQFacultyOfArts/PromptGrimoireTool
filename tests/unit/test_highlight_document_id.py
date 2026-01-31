"""Tests for document_id in highlight data."""

from __future__ import annotations


class TestHighlightDocumentId:
    """Tests for document_id field in highlights."""

    def test_add_highlight_without_document_id_works(self) -> None:
        """Backward compatibility: highlight without document_id works."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Test text",
            author="Author",
        )

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        # document_id should be None when not provided
        assert highlight.get("document_id") is None

    def test_add_highlight_with_document_id(self) -> None:
        """Highlight stores document_id when provided."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Test text",
            author="Author",
            document_id="workspace-doc-uuid-123",
        )

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        assert highlight.get("document_id") == "workspace-doc-uuid-123"

    def test_document_id_survives_crdt_roundtrip(self) -> None:
        """document_id preserved through CRDT state transfer."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        # Create doc with document_id
        doc1 = AnnotationDocument("test-doc-1")
        hl_id = doc1.add_highlight(
            start_word=10,
            end_word=20,
            tag="citation",
            text="Citation text",
            author="Author",
            document_id="my-document-id",
        )

        # Transfer state to another doc
        state_bytes = doc1.get_full_state()
        doc2 = AnnotationDocument("test-doc-2")
        doc2.apply_update(state_bytes)

        # Verify document_id preserved
        highlight = doc2.get_highlight(hl_id)
        assert highlight is not None
        assert highlight.get("document_id") == "my-document-id"

    def test_get_all_highlights_includes_document_id(self) -> None:
        """get_all_highlights returns document_id field."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-doc")
        doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Text 1",
            author="Author",
            document_id="doc-1",
        )
        doc.add_highlight(
            start_word=10,
            end_word=15,
            tag="citation",
            text="Text 2",
            author="Author",
            document_id="doc-2",
        )

        highlights = doc.get_all_highlights()
        assert len(highlights) == 2
        # Sorted by start_word
        assert highlights[0]["document_id"] == "doc-1"
        assert highlights[1]["document_id"] == "doc-2"


class TestGetHighlightsForDocument:
    """Tests for filtering highlights by document_id."""

    def test_get_highlights_for_specific_document(self) -> None:
        """Returns only highlights for specified document_id."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-workspace")

        # Add highlights for different documents
        doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Doc A highlight 1",
            author="Author",
            document_id="doc-a",
        )
        doc.add_highlight(
            start_word=10,
            end_word=15,
            tag="citation",
            text="Doc B highlight",
            author="Author",
            document_id="doc-b",
        )
        doc.add_highlight(
            start_word=20,
            end_word=25,
            tag="issue",
            text="Doc A highlight 2",
            author="Author",
            document_id="doc-a",
        )

        # Get highlights for doc-a only
        doc_a_highlights = doc.get_highlights_for_document("doc-a")

        assert len(doc_a_highlights) == 2
        assert all(h["document_id"] == "doc-a" for h in doc_a_highlights)
        # Should be sorted by start_word
        assert doc_a_highlights[0]["start_word"] == 0
        assert doc_a_highlights[1]["start_word"] == 20

    def test_get_highlights_for_unknown_document_returns_empty(self) -> None:
        """Returns empty list for document with no highlights."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-workspace")
        doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Some highlight",
            author="Author",
            document_id="doc-a",
        )

        highlights = doc.get_highlights_for_document("doc-nonexistent")

        assert highlights == []

    def test_get_highlights_for_document_excludes_none(self) -> None:
        """Highlights without document_id are NOT returned."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument

        doc = AnnotationDocument("test-workspace")

        # Highlight without document_id (old style)
        doc.add_highlight(
            start_word=0,
            end_word=5,
            tag="issue",
            text="Old style",
            author="Author",
        )
        # Highlight with document_id
        doc.add_highlight(
            start_word=10,
            end_word=15,
            tag="citation",
            text="New style",
            author="Author",
            document_id="doc-a",
        )

        highlights = doc.get_highlights_for_document("doc-a")

        assert len(highlights) == 1
        assert highlights[0]["document_id"] == "doc-a"
