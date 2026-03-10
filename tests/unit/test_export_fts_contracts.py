"""Tests verifying export pipeline and FTS contracts after CRDT tag refactor.

AC6.1: PDF export produces correct tag colours from CRDT source.
AC6.2: FTS search text includes resolved tag names from CRDT highlights.

These are pure unit tests — no database required.
"""

from __future__ import annotations

from uuid import uuid4

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.db.crdt_extraction import extract_searchable_text
from promptgrimoire.export.preamble import generate_tag_colour_definitions
from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt


class TestExportTagColours:
    """AC6.1: workspace_tags_from_crdt → generate_tag_colour_definitions pipeline."""

    def test_definecolor_emitted_for_each_tag(self) -> None:
        """Tags set in CRDT produce \\definecolor commands with correct hex values."""
        doc = AnnotationDocument("test-export")
        tag_a = str(uuid4())
        tag_b = str(uuid4())

        doc.set_tag(tag_a, "Jurisdiction", "#1f77b4", order_index=0)
        doc.set_tag(tag_b, "Legal Issues", "#ff7f0e", order_index=1)

        tag_info_list = workspace_tags_from_crdt(doc)
        tag_colours = {info.raw_key: info.colour for info in tag_info_list}

        latex_output = generate_tag_colour_definitions(tag_colours)

        # Each tag UUID should appear as a definecolor with the right hex
        assert f"\\definecolor{{tag-{tag_a}}}{{HTML}}{{1f77b4}}" in latex_output
        assert f"\\definecolor{{tag-{tag_b}}}{{HTML}}{{ff7f0e}}" in latex_output

    def test_colour_hex_stripped_of_hash(self) -> None:
        """Colours from CRDT include '#' prefix; definecolor strips it."""
        doc = AnnotationDocument("test-export-strip")
        tag_id = str(uuid4())
        doc.set_tag(tag_id, "Ethics", "#2ca02c", order_index=0)

        tag_info_list = workspace_tags_from_crdt(doc)
        tag_colours = {info.raw_key: info.colour for info in tag_info_list}

        latex_output = generate_tag_colour_definitions(tag_colours)

        # Should NOT contain double-hash or raw '#' in the HTML arg
        assert "HTML}{#" not in latex_output
        assert "{HTML}{2ca02c}" in latex_output

    def test_empty_tags_produce_no_tag_definitions(self) -> None:
        """No tags in CRDT → only the always-present many-dark fallback."""
        doc = AnnotationDocument("test-export-empty")

        tag_info_list = workspace_tags_from_crdt(doc)
        assert tag_info_list == []

        tag_colours = {info.raw_key: info.colour for info in tag_info_list}
        latex_output = generate_tag_colour_definitions(tag_colours)

        # No tag-specific definecolor, only the many-dark fallback
        assert "\\definecolor{tag-" not in latex_output
        assert "many-dark" in latex_output


class TestFtsSearchText:
    """AC6.2: extract_searchable_text resolves tag UUIDs to display names."""

    def test_tag_names_appear_in_search_text(self) -> None:
        """Highlights with tag UUIDs resolve to tag names in FTS text."""
        doc = AnnotationDocument("test-fts")
        tag_id = str(uuid4())
        doc.set_tag(tag_id, "Negligence", "#d62728", order_index=0)

        doc.add_highlight(
            start_char=0,
            end_char=10,
            tag=tag_id,
            text="duty of care",
            author="test-user",
        )

        tag_names = {tag_id: "Negligence"}
        search_text = extract_searchable_text(doc.get_full_state(), tag_names)

        assert "Negligence" in search_text
        assert "duty of care" in search_text

    def test_multiple_tags_all_resolved(self) -> None:
        """Multiple highlights with different tags all resolve in FTS text."""
        doc = AnnotationDocument("test-fts-multi")
        tag_a = str(uuid4())
        tag_b = str(uuid4())
        doc.set_tag(tag_a, "Jurisdiction", "#1f77b4", order_index=0)
        doc.set_tag(tag_b, "Damages", "#ff7f0e", order_index=1)

        doc.add_highlight(
            start_char=0, end_char=5, tag=tag_a, text="court", author="user1"
        )
        doc.add_highlight(
            start_char=10, end_char=20, tag=tag_b, text="compensation", author="user1"
        )

        tag_names = {tag_a: "Jurisdiction", tag_b: "Damages"}
        search_text = extract_searchable_text(doc.get_full_state(), tag_names)

        assert "Jurisdiction" in search_text
        assert "Damages" in search_text
        assert "court" in search_text
        assert "compensation" in search_text

    def test_no_highlights_returns_empty(self) -> None:
        """No highlights or content → empty search text."""
        doc = AnnotationDocument("test-fts-empty")

        search_text = extract_searchable_text(doc.get_full_state(), {})

        assert search_text == ""

    def test_none_state_returns_empty(self) -> None:
        """None crdt_state → empty search text."""
        search_text = extract_searchable_text(None, {})

        assert search_text == ""
