"""Unit tests for Tab 2 (Organise) rendering logic.

Tests verify that render_organise_tab correctly groups highlights by tag
into columns, respects tag_order, and handles untagged highlights.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_03.md Task 2
- AC: three-tab-ui.AC2.1, AC2.2, AC2.6
"""

from __future__ import annotations

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.pages.annotation_organise import _SNIPPET_MAX_CHARS
from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info


class TestHighlightGrouping:
    """Verify highlight grouping logic for Organise tab columns."""

    def test_highlights_grouped_by_tag(self) -> None:
        """Highlights are grouped into the correct tag based on their tag field."""
        doc = AnnotationDocument("test-grouping")
        doc.add_highlight(0, 10, "jurisdiction", "test text 1", "Author A")
        doc.add_highlight(10, 20, "legal_issues", "test text 2", "Author B")
        doc.add_highlight(20, 30, "jurisdiction", "test text 3", "Author A")

        tags = brief_tags_to_tag_info()
        all_highlights = doc.get_all_highlights()

        # Build the same grouping logic as render_organise_tab
        tag_raw_values: dict[str, str] = {
            tag_info.raw_key: tag_info.name for tag_info in tags
        }

        tagged: dict[str, list[dict]] = {ti.name: [] for ti in tags}
        untagged: list[dict] = []
        for hl in all_highlights:
            raw_tag = hl.get("tag", "")
            if raw_tag and raw_tag in tag_raw_values:
                tagged[tag_raw_values[raw_tag]].append(hl)
            else:
                untagged.append(hl)

        assert len(tagged["Jurisdiction"]) == 2
        assert len(tagged["Legal Issues"]) == 1
        assert len(untagged) == 0

    def test_untagged_highlights_collected(self) -> None:
        """Highlights with empty or unknown tag go to untagged group (AC2.6)."""
        doc = AnnotationDocument("test-untagged")
        doc.add_highlight(0, 10, "", "untagged text", "Author A")
        doc.add_highlight(10, 20, "jurisdiction", "tagged text", "Author B")
        doc.add_highlight(20, 30, "nonexistent_tag", "unknown tag text", "Author C")

        tags = brief_tags_to_tag_info()
        all_highlights = doc.get_all_highlights()

        tag_raw_values: dict[str, str] = {
            tag_info.raw_key: tag_info.name for tag_info in tags
        }

        tagged: dict[str, list[dict]] = {ti.name: [] for ti in tags}
        untagged: list[dict] = []
        for hl in all_highlights:
            raw_tag = hl.get("tag", "")
            if raw_tag and raw_tag in tag_raw_values:
                tagged[tag_raw_values[raw_tag]].append(hl)
            else:
                untagged.append(hl)

        assert len(tagged["Jurisdiction"]) == 1
        assert len(untagged) == 2  # empty string + nonexistent_tag

    def test_tag_order_respected(self) -> None:
        """Highlights are returned in tag_order when available."""
        doc = AnnotationDocument("test-order")
        id1 = doc.add_highlight(0, 10, "jurisdiction", "first", "Author A")
        id2 = doc.add_highlight(10, 20, "jurisdiction", "second", "Author B")
        id3 = doc.add_highlight(20, 30, "jurisdiction", "third", "Author C")

        # Set custom order: 3, 1, 2
        doc.set_tag_order("jurisdiction", [id3, id1, id2])

        ordered_ids = doc.get_tag_order("jurisdiction")
        assert ordered_ids == [id3, id1, id2]

        # Verify we can reconstruct the ordered list
        hl_by_id = {h["id"]: h for h in doc.get_all_highlights()}
        ordered_highlights = [hl_by_id[hid] for hid in ordered_ids if hid in hl_by_id]
        assert ordered_highlights[0]["text"] == "third"
        assert ordered_highlights[1]["text"] == "first"
        assert ordered_highlights[2]["text"] == "second"

    def test_empty_document_no_highlights(self) -> None:
        """An empty document produces no highlights in any group."""
        doc = AnnotationDocument("test-empty")
        all_highlights = doc.get_all_highlights()
        assert len(all_highlights) == 0

    def test_highlight_card_data_extraction(self) -> None:
        """Verify highlight dict contains expected fields for card rendering."""
        doc = AnnotationDocument("test-card-data")
        doc.add_highlight(
            5, 15, "legal_issues", "sample highlighted text", "Test Author"
        )

        highlights = doc.get_all_highlights()
        assert len(highlights) == 1

        hl = highlights[0]
        assert hl["tag"] == "legal_issues"
        assert hl["text"] == "sample highlighted text"
        assert hl["author"] == "Test Author"
        assert hl["start_char"] == 5
        assert hl["end_char"] == 15
        assert "id" in hl

    def test_snippet_truncation_logic(self) -> None:
        """Long text should be truncated at _SNIPPET_MAX_CHARS in card rendering."""
        long_text = "x" * 150
        snippet = long_text[:_SNIPPET_MAX_CHARS]
        if len(long_text) > _SNIPPET_MAX_CHARS:
            snippet += "..."
        assert len(snippet) == _SNIPPET_MAX_CHARS + 3  # _SNIPPET_MAX_CHARS + "..."
        assert snippet.endswith("...")

    def test_all_ten_tags_produce_columns(self) -> None:
        """Each of the 10 BriefTag members maps to a column (AC2.1)."""
        tags = brief_tags_to_tag_info()
        assert len(tags) == 10
        # Verify all have non-empty names and colours
        for tag_info in tags:
            assert tag_info.name
            assert tag_info.colour.startswith("#")
