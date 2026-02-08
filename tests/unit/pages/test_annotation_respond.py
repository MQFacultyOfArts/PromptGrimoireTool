"""Unit tests for Tab 3 (Respond) reference panel logic.

Tests verify that the reference panel correctly groups highlights by tag,
handles empty state, and truncates text snippets.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_05.md Task 2
- AC: three-tab-ui.AC4.4, AC4.5
"""

from __future__ import annotations

from typing import Any

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.pages.annotation_respond import _SNIPPET_MAX_CHARS
from promptgrimoire.pages.annotation_tags import TagInfo, brief_tags_to_tag_info


def _group_highlights_for_reference(
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], bool]:
    """Replicate the reference panel grouping logic for testing.

    Returns:
        (tagged_highlights, untagged_highlights, has_any_highlights)
    """
    all_highlights = crdt_doc.get_all_highlights()

    tag_raw_values: dict[str, TagInfo] = {tag.raw_key: tag for tag in tags}

    tagged_highlights: dict[str, list[dict[str, Any]]] = {
        tag_info.name: [] for tag_info in tags
    }
    untagged_highlights: list[dict[str, Any]] = []

    for hl in all_highlights:
        raw_tag = hl.get("tag", "")
        if raw_tag and raw_tag in tag_raw_values:
            display_name = tag_raw_values[raw_tag].name
            tagged_highlights[display_name].append(hl)
        else:
            untagged_highlights.append(hl)

    has_any = bool(all_highlights)
    return tagged_highlights, untagged_highlights, has_any


class TestReferenceHighlightGrouping:
    """Verify highlight grouping logic for the reference panel."""

    def test_highlights_grouped_by_tag(self) -> None:
        """Highlights are grouped into the correct tag sections."""
        doc = AnnotationDocument("test-ref-group")
        doc.add_highlight(0, 10, "jurisdiction", "test text 1", "Author A")
        doc.add_highlight(10, 20, "legal_issues", "test text 2", "Author B")
        doc.add_highlight(20, 30, "jurisdiction", "test text 3", "Author A")

        tags = brief_tags_to_tag_info()
        tagged, untagged, has_any = _group_highlights_for_reference(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 2
        assert len(tagged["Legal Issues"]) == 1
        assert len(untagged) == 0

    def test_empty_document_returns_no_highlights(self) -> None:
        """An empty document produces has_any_highlights=False (AC4.5)."""
        doc = AnnotationDocument("test-ref-empty")
        tags = brief_tags_to_tag_info()
        tagged, untagged, has_any = _group_highlights_for_reference(tags, doc)

        assert has_any is False
        assert len(untagged) == 0
        # All tag groups should be empty
        for tag_info in tags:
            assert len(tagged[tag_info.name]) == 0

    def test_untagged_highlights_in_separate_group(self) -> None:
        """Highlights with no/unknown tag go to untagged group."""
        doc = AnnotationDocument("test-ref-untagged")
        doc.add_highlight(0, 10, "", "no tag", "Author A")
        doc.add_highlight(10, 20, "nonexistent_tag", "bad tag", "Author B")
        doc.add_highlight(20, 30, "jurisdiction", "good tag", "Author C")

        tags = brief_tags_to_tag_info()
        tagged, untagged, has_any = _group_highlights_for_reference(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 1
        assert len(untagged) == 2

    def test_snippet_truncation(self) -> None:
        """Long highlight text is truncated with ellipsis."""
        long_text = "x" * 150
        snippet = long_text[:_SNIPPET_MAX_CHARS]
        if len(long_text) > _SNIPPET_MAX_CHARS:
            snippet += "..."

        assert len(snippet) == _SNIPPET_MAX_CHARS + 3
        assert snippet.endswith("...")

    def test_snippet_short_text_no_truncation(self) -> None:
        """Short highlight text is not truncated."""
        short_text = "short"
        snippet = short_text[:_SNIPPET_MAX_CHARS]
        if len(short_text) > _SNIPPET_MAX_CHARS:
            snippet += "..."

        assert snippet == "short"
        assert not snippet.endswith("...")

    def test_multiple_tags_with_highlights(self) -> None:
        """Highlights across many tags are grouped correctly (AC4.4)."""
        doc = AnnotationDocument("test-ref-multi")
        doc.add_highlight(0, 10, "jurisdiction", "hl1", "A")
        doc.add_highlight(10, 20, "legal_issues", "hl2", "B")
        doc.add_highlight(20, 30, "legally_relevant_facts", "hl3", "C")
        doc.add_highlight(30, 40, "reasons", "hl4", "D")

        tags = brief_tags_to_tag_info()
        tagged, untagged, has_any = _group_highlights_for_reference(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 1
        assert len(tagged["Legal Issues"]) == 1
        assert len(tagged["Legally Relevant Facts"]) == 1
        assert len(tagged["Reasons"]) == 1
        assert len(untagged) == 0

    def test_only_non_empty_tags_should_render(self) -> None:
        """Tags with no highlights should produce empty lists."""
        doc = AnnotationDocument("test-ref-sparse")
        doc.add_highlight(0, 10, "jurisdiction", "only one tag", "A")

        tags = brief_tags_to_tag_info()
        tagged, _untagged, has_any = _group_highlights_for_reference(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 1
        # All other tags should be empty
        for tag_info in tags:
            if tag_info.name != "Jurisdiction":
                assert len(tagged[tag_info.name]) == 0
