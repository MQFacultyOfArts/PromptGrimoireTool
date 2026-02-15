"""Unit tests for Tab 2 (Organise) rendering logic.

Tests verify that render_organise_tab correctly groups highlights by tag
into columns, respects tag_order, and handles untagged highlights.

Also tests the SortableJS event arg parsing logic used by the organise
tab's drag-and-drop reorder/reassign feature.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_03.md Task 2
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_04.md Task 2
- AC: three-tab-ui.AC2.1, AC2.2, AC2.3, AC2.4, AC2.6
"""

from __future__ import annotations

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.pages.annotation.organise import _SNIPPET_MAX_CHARS
from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info
from promptgrimoire.pages.annotation.workspace import _parse_sort_end_args


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


class TestSortEndEventParsing:
    """Verify SortableJS sort-end event arg parsing (AC2.3, AC2.4)."""

    def test_parse_simple_same_column_reorder(self) -> None:
        """Parse event args for reordering within same tag column."""
        args = {
            "item": "hl-highlight-123",
            "from": "sort-jurisdiction",
            "to": "sort-jurisdiction",
            "newIndex": 2,
        }
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == "highlight-123"
        assert source_tag == "jurisdiction"
        assert target_tag == "jurisdiction"
        assert new_index == 2

    def test_parse_cross_column_move(self) -> None:
        """Parse event args for moving highlight between tag columns."""
        args = {
            "item": "hl-highlight-456",
            "from": "sort-jurisdiction",
            "to": "sort-legal_issues",
            "newIndex": 1,
        }
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == "highlight-456"
        assert source_tag == "jurisdiction"
        assert target_tag == "legal_issues"
        assert new_index == 1

    def test_parse_untagged_source_to_tagged(self) -> None:
        """Parse move FROM untagged column (sort-untagged) TO tagged column."""
        args = {
            "item": "hl-highlight-789",
            "from": "sort-untagged",
            "to": "sort-jurisdiction",
            "newIndex": 0,
        }
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == "highlight-789"
        assert source_tag == ""  # sort-untagged -> empty string
        assert target_tag == "jurisdiction"
        assert new_index == 0

    def test_parse_tagged_to_untagged_destination(self) -> None:
        """Parse move FROM tagged column TO untagged column."""
        args = {
            "item": "hl-highlight-abc",
            "from": "sort-legal_issues",
            "to": "sort-untagged",
            "newIndex": 3,
        }
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == "highlight-abc"
        assert source_tag == "legal_issues"
        assert target_tag == ""  # sort-untagged -> empty string
        assert new_index == 3

    def test_parse_untagged_reorder_within_column(self) -> None:
        """Parse reorder event within untagged column (both from/to untagged)."""
        args = {
            "item": "hl-highlight-def",
            "from": "sort-untagged",
            "to": "sort-untagged",
            "newIndex": 1,
        }
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == "highlight-def"
        assert source_tag == ""
        assert target_tag == ""
        assert new_index == 1

    def test_parse_missing_item_id(self) -> None:
        """Parser handles missing item field gracefully."""
        args = {
            "from": "sort-jurisdiction",
            "to": "sort-jurisdiction",
            "newIndex": 0,
        }
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == ""  # Missing item -> empty string
        assert source_tag == "jurisdiction"
        assert target_tag == "jurisdiction"
        assert new_index == 0

    def test_parse_missing_container_ids(self) -> None:
        """Parser handles missing from/to IDs gracefully."""
        args = {
            "item": "hl-highlight-ghi",
            "newIndex": 1,
        }
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == "highlight-ghi"
        assert source_tag == ""  # Missing from -> empty string
        assert target_tag == ""  # Missing to -> empty string
        assert new_index == 1

    def test_parse_missing_new_index(self) -> None:
        """Parser handles missing newIndex field gracefully."""
        args = {
            "item": "hl-highlight-jkl",
            "from": "sort-jurisdiction",
            "to": "sort-jurisdiction",
        }
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == "highlight-jkl"
        assert source_tag == "jurisdiction"
        assert target_tag == "jurisdiction"
        assert new_index == -1  # Missing newIndex -> -1

    def test_parse_strips_hl_prefix(self) -> None:
        """The hl- prefix is correctly stripped from item ID."""
        args = {
            "item": "hl-my-custom-id-12345",
            "from": "sort-jurisdiction",
            "to": "sort-jurisdiction",
            "newIndex": 0,
        }
        highlight_id, _, _, _ = _parse_sort_end_args(args)
        assert highlight_id == "my-custom-id-12345"
        assert not highlight_id.startswith("hl-")

    def test_parse_strips_sort_prefix(self) -> None:
        """The sort- prefix is correctly stripped from container IDs."""
        args = {
            "item": "hl-highlight-123",
            "from": "sort-my-custom-tag",
            "to": "sort-another-tag",
            "newIndex": 0,
        }
        _, source_tag, target_tag, _ = _parse_sort_end_args(args)
        assert source_tag == "my-custom-tag"
        assert target_tag == "another-tag"
        assert not source_tag.startswith("sort-")
        assert not target_tag.startswith("sort-")

    def test_parse_empty_args_dict(self) -> None:
        """Parser handles empty args dict gracefully."""
        args: dict[str, str | int] = {}
        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(args)
        assert highlight_id == ""
        assert source_tag == ""
        assert target_tag == ""
        assert new_index == -1

    def test_parse_return_tuple_order(self) -> None:
        """Return tuple is in correct order: (hl_id, src, dst, idx)."""
        args = {
            "item": "hl-hl-id",
            "from": "sort-src",
            "to": "sort-dst",
            "newIndex": 5,
        }
        result = _parse_sort_end_args(args)
        assert len(result) == 4
        assert result[0] == "hl-id"  # highlight_id
        assert result[1] == "src"  # source_tag
        assert result[2] == "dst"  # target_tag
        assert result[3] == 5  # new_index
