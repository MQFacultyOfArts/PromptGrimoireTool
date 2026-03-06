"""Unit tests for _cleanup_crdt_highlights_on_doc resilience to CRDT corruption.

Verifies that highlight cleanup continues past corrupted entries,
logging warnings instead of crashing.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.db.tags import _cleanup_crdt_highlights_on_doc


class TestCleanupCrdtHighlightsCorruption:
    """Verify _cleanup_crdt_highlights_on_doc handles corrupted highlights."""

    def test_continues_past_value_error(self) -> None:
        """Cleanup continues when remove_highlight raises ValueError.

        Simulates CRDT corruption where the highlight Map entry exists
        but its internal structure is invalid.
        """
        doc = AnnotationDocument("test-corrupt")
        tag_id = uuid4()
        tag_str = str(tag_id)

        # Add two highlights for this tag
        hl1 = doc.add_highlight(
            start_char=0, end_char=5, tag=tag_str, text="first", author="test"
        )
        hl2 = doc.add_highlight(
            start_char=10, end_char=15, tag=tag_str, text="second", author="test"
        )
        doc.set_tag_order(tag_str, [hl1, hl2])
        doc.set_tag(
            tag_id=tag_id,
            name="Corrupt",
            colour="#ff0000",
            order_index=0,
            highlights=[hl1, hl2],
        )

        call_count = 0
        original_remove = doc.remove_highlight

        def raise_on_first(highlight_id, origin_client_id=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("corrupted CRDT entry")
            return original_remove(highlight_id, origin_client_id)

        with patch.object(doc, "remove_highlight", side_effect=raise_on_first):
            removed = _cleanup_crdt_highlights_on_doc(doc, tag_id)

        # Both highlights were attempted
        assert removed == 2
        # tag_order and tags Map cleaned up despite the error
        assert tag_str not in doc.tag_order
        assert doc.get_tag(tag_id) is None

    def test_continues_past_key_error(self) -> None:
        """Cleanup continues when remove_highlight raises KeyError.

        Simulates CRDT corruption where the highlight ID references
        a missing Map key.
        """
        doc = AnnotationDocument("test-keyerr")
        tag_id = uuid4()
        tag_str = str(tag_id)

        hl1 = doc.add_highlight(
            start_char=0, end_char=5, tag=tag_str, text="first", author="test"
        )
        hl2 = doc.add_highlight(
            start_char=10, end_char=15, tag=tag_str, text="second", author="test"
        )
        doc.set_tag(
            tag_id=tag_id,
            name="KeyErr",
            colour="#00ff00",
            order_index=0,
            highlights=[hl1, hl2],
        )

        def raise_key_error_on_all(highlight_id, **_kwargs):
            raise KeyError(f"missing key {highlight_id}")

        with patch.object(doc, "remove_highlight", side_effect=raise_key_error_on_all):
            removed = _cleanup_crdt_highlights_on_doc(doc, tag_id)

        # All highlights attempted despite errors
        assert removed == 2
        # Tag itself still cleaned up
        assert doc.get_tag(tag_id) is None

    def test_happy_path_no_corruption(self) -> None:
        """Cleanup works normally when no corruption present."""
        doc = AnnotationDocument("test-clean")
        tag_id = uuid4()
        tag_str = str(tag_id)

        hl1 = doc.add_highlight(
            start_char=0, end_char=5, tag=tag_str, text="clean", author="test"
        )
        doc.set_tag_order(tag_str, [hl1])
        doc.set_tag(
            tag_id=tag_id,
            name="Clean",
            colour="#0000ff",
            order_index=0,
            highlights=[hl1],
        )

        removed = _cleanup_crdt_highlights_on_doc(doc, tag_id)

        assert removed == 1
        assert doc.get_all_highlights() == []
        assert tag_str not in doc.tag_order
        assert doc.get_tag(tag_id) is None
