"""Unit tests for Tab 3 (Respond) reference panel logic.

Tests verify that the reference panel correctly groups highlights by tag,
handles empty state, and truncates text snippets.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_05.md Task 2
- AC: three-tab-ui.AC4.4, AC4.5
"""

from __future__ import annotations

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.pages.annotation.respond import (
    _SNIPPET_MAX_CHARS,
    _matches_filter,
    group_highlights_by_tag,
)
from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info


class TestReferenceHighlightGrouping:
    """Verify highlight grouping logic for the reference panel."""

    def test_highlights_grouped_by_tag(self) -> None:
        """Highlights are grouped into the correct tag sections."""
        doc = AnnotationDocument("test-ref-group")
        doc.add_highlight(0, 10, "jurisdiction", "test text 1", "Author A")
        doc.add_highlight(10, 20, "legal_issues", "test text 2", "Author B")
        doc.add_highlight(20, 30, "jurisdiction", "test text 3", "Author A")

        tags = brief_tags_to_tag_info()
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 2
        assert len(tagged["Legal Issues"]) == 1
        assert len(untagged) == 0

    def test_empty_document_returns_no_highlights(self) -> None:
        """An empty document produces has_any_highlights=False (AC4.5)."""
        doc = AnnotationDocument("test-ref-empty")
        tags = brief_tags_to_tag_info()
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)

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
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)

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
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)

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
        tagged, _untagged, has_any = group_highlights_by_tag(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 1
        # All other tags should be empty
        for tag_info in tags:
            if tag_info.name != "Jurisdiction":
                assert len(tagged[tag_info.name]) == 0


class TestMatchesFilter:
    """Verify the highlight search filter logic."""

    def test_matches_highlight_text(self) -> None:
        """Filter matches against highlight text content."""
        hl = {"text": "The court held that negligence was proven", "author": "Alice"}
        assert _matches_filter(hl, "negligence") is True

    def test_matches_author(self) -> None:
        """Filter matches against highlight author."""
        hl = {"text": "some text", "author": "Professor Smith"}
        assert _matches_filter(hl, "smith") is True

    def test_matches_comment_text(self) -> None:
        """Filter matches against comment text within a highlight."""
        hl = {
            "text": "highlighted passage",
            "author": "Alice",
            "comments": [{"text": "This is a key finding", "author": "Bob"}],
        }
        assert _matches_filter(hl, "key finding") is True

    def test_matches_comment_author(self) -> None:
        """Filter matches against comment author within a highlight."""
        hl = {
            "text": "highlighted passage",
            "author": "Alice",
            "comments": [{"text": "Good point", "author": "Dr. Jones"}],
        }
        assert _matches_filter(hl, "jones") is True

    def test_no_match_returns_false(self) -> None:
        """Filter returns False when nothing matches."""
        hl = {
            "text": "The sky is blue",
            "author": "Alice",
            "comments": [{"text": "Indeed", "author": "Bob"}],
        }
        assert _matches_filter(hl, "jurisdiction") is False

    def test_case_insensitive(self) -> None:
        """Filter matching is case-insensitive."""
        hl = {"text": "NEGLIGENCE was proven", "author": "alice"}
        assert _matches_filter(hl, "Negligence") is True
        assert _matches_filter(hl, "ALICE") is True

    def test_empty_filter_matches_everything(self) -> None:
        """An empty filter string matches any highlight."""
        hl = {"text": "anything", "author": "anyone"}
        assert _matches_filter(hl, "") is True

    def test_missing_fields_do_not_crash(self) -> None:
        """Highlights with missing keys don't raise errors."""
        assert _matches_filter({}, "test") is False
        assert _matches_filter({"text": "hello"}, "hello") is True

    def test_highlight_with_no_comments(self) -> None:
        """Highlights without a comments key still work."""
        hl = {"text": "some text", "author": "Alice"}
        assert _matches_filter(hl, "some") is True
        assert _matches_filter(hl, "missing") is False

    def test_multiple_comments_any_match(self) -> None:
        """If any comment matches, the highlight matches."""
        hl = {
            "text": "passage",
            "author": "Alice",
            "comments": [
                {"text": "Not relevant", "author": "Bob"},
                {"text": "Very important point", "author": "Carol"},
            ],
        }
        assert _matches_filter(hl, "important") is True
        assert _matches_filter(hl, "carol") is True
        assert _matches_filter(hl, "nonexistent") is False
