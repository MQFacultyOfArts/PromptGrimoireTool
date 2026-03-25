"""Edge case and verification tests for paragraph numbering (#417).

- AC1.3: Empty paragraph map returns HTML unchanged
- AC3.2: para_ref survives endnote \\write path
- AC2.4: Short-only annotations have no cross-reference links
- Additional: no-annotation doc, br-br pseudo-paragraphs
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.highlight_spans import compute_highlight_spans
from promptgrimoire.export.pandoc import convert_html_with_annotations
from promptgrimoire.input_pipeline.paragraph_map import (
    inject_paragraph_markers_for_export,
)
from tests.conftest import requires_pandoc


class TestEmptyParagraphMap:
    """AC1.3: Empty paragraph map returns HTML unchanged."""

    def test_empty_dict_returns_unchanged(self) -> None:
        """Empty dict produces no markers."""
        html = "<p>Hello world.</p>"
        result = inject_paragraph_markers_for_export(html, {})
        assert result == html

    def test_none_returns_unchanged(self) -> None:
        """None word_to_legal_para produces no markers."""
        html = "<p>Hello world.</p>"
        result = inject_paragraph_markers_for_export(html, None)
        assert result == html


class TestNoAnnotationsWithParanumber:
    """Paragraph numbering works independently of annotations."""

    def test_no_highlights_still_gets_paranumber(self) -> None:
        """No annotations + paranumber markers still inject."""
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        para_map: dict[int, int | None] = {0: 1, 16: 2}

        # compute_highlight_spans with no highlights: unchanged
        span_html = compute_highlight_spans(html, [], {})
        assert "data-hl" not in span_html

        # But paranumber markers still work
        result = inject_paragraph_markers_for_export(html, para_map)
        assert 'data-paranumber="1"' in result
        assert 'data-paranumber="2"' in result


class TestBrBrPseudoParagraphMarkers:
    """br-br pseudo-paragraphs get paranumber markers."""

    def test_br_br_gets_paranumber(self) -> None:
        """Text after <br><br> gets wrapped with data-para."""
        html = "<p>First line.<br><br>Second line.</p>"
        # Build a para map matching the br-br split:
        # "First line." = 11 chars, then \n for first br = 1,
        # \n for second br = 1, so "Second line." starts at 13
        para_map: dict[int, int | None] = {0: 1, 13: 2}

        result = inject_paragraph_markers_for_export(html, para_map)
        assert 'data-paranumber="1"' in result
        assert 'data-paranumber="2"' in result


@requires_pandoc
class TestParaRefInEndnotePath:
    """AC3.2: para_ref text survives the endnote \\write path."""

    @pytest.mark.asyncio
    async def test_para_ref_in_annot_content(self) -> None:
        r"""Annotations with para_ref produce \annot containing [N]."""
        html = "<p>Some highlighted text in a paragraph.</p>"
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 20,
                "tag": "issue",
                "text": "Some highlighted text",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                "para_ref": "[3]",
                "comments": [
                    {
                        "author": "Bob",
                        "text": "A comment.",
                        "created_at": "2026-01-26T11:00:00+00:00",
                    },
                ],
            },
        ]
        tag_colours = {"issue": "#e377c2"}

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=tag_colours,
        )
        # The \annot content should include the para ref [3]
        assert r"\annot{" in latex
        assert "[3]" in latex


@requires_pandoc
class TestParaRefComputedAtExportTime:
    """para_ref computed from word_to_legal_para when not stored."""

    @pytest.mark.asyncio
    async def test_empty_para_ref_computed_from_map(self) -> None:
        r"""Highlights with no para_ref get it computed at export.

        Pre-existing highlights have para_ref=''. The export pipeline
        must compute it from word_to_legal_para so annotations show
        paragraph references like [3] in the margin/endnote content.
        """
        html = "<p>Some highlighted text in a paragraph.</p>"
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 20,
                "tag": "issue",
                "text": "Some highlighted text",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                # NO para_ref key — simulates pre-existing highlight
                "comments": [
                    {
                        "author": "Bob",
                        "text": "A comment.",
                        "created_at": "2026-01-26T11:00:00+00:00",
                    },
                ],
            },
        ]
        tag_colours = {"issue": "#e377c2"}
        para_map: dict[int, int | None] = {0: 3}

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=tag_colours,
            word_to_legal_para=para_map,
        )
        assert r"\annot{" in latex
        # para_ref [3] must appear even though highlight has no para_ref
        assert "[3]" in latex

    @pytest.mark.asyncio
    async def test_stored_para_ref_not_overwritten(self) -> None:
        r"""Highlights with existing para_ref keep their stored value."""
        html = "<p>Some highlighted text in a paragraph.</p>"
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 20,
                "tag": "issue",
                "text": "Some highlighted text",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                "para_ref": "[99]",  # manually set, should be kept
                "comments": [],
            },
        ]
        tag_colours = {"issue": "#e377c2"}
        para_map: dict[int, int | None] = {0: 3}

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=tag_colours,
            word_to_legal_para=para_map,
        )
        assert r"\annot{" in latex
        # Stored [99] should win over computed [3]
        assert "[99]" in latex
        assert "[3]" not in latex


@requires_pandoc
class TestMixedShortLongAnnotations:
    """Mixed short and long annotations both produce \\annot commands."""

    @pytest.mark.asyncio
    async def test_mixed_annotations_both_present(self) -> None:
        r"""Both short and long annotations emit \annot in LaTeX.

        Short/long routing happens at LaTeX compile time via
        \\ifdim in the .sty, so the .tex source contains \\annot
        for both. The static analysis tests in Phase 3
        (TestAnnotMacroShortPath/LongPath) verify the .sty macro
        structure for each path.
        """
        html = (
            "<p>Short note here and also a longer passage "
            "that has much more content to annotate.</p>"
        )
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 10,
                "tag": "note",
                "text": "Short note",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                "comments": [],
            },
            {
                "id": "h2",
                "start_char": 20,
                "end_char": 44,
                "tag": "issue",
                "text": "a longer passage that has",
                "author": "Bob",
                "created_at": "2026-01-26T10:00:00+00:00",
                "comments": [
                    {
                        "author": "Carol",
                        "text": (
                            "Detailed comment with enough "
                            "content to push the annotation "
                            "well beyond the margin height "
                            "threshold when compiled."
                        ),
                        "created_at": "2026-01-26T11:00:00+00:00",
                    },
                ],
            },
        ]
        tag_colours = {"note": "#4daf4a", "issue": "#e377c2"}

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=tag_colours,
        )
        # Both annotations produce \annot commands
        assert latex.count(r"\annot{") >= 2


@requires_pandoc
class TestShortOnlyAnnotationsNoCrossref:
    """AC2.4: Short-only doc has no endnote cross-references."""

    @pytest.mark.asyncio
    async def test_short_only_no_endnote_labels(self) -> None:
        r"""\annot present but no \label{annot-endnote: in .tex."""
        html = "<p>Short annotated text here.</p>"
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 5,
                "tag": "note",
                "text": "Short",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                "comments": [],
            },
        ]
        tag_colours = {"note": "#4daf4a"}

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=tag_colours,
        )
        assert r"\annot{" in latex
        # Short path: no endnote cross-ref labels in .tex source
        assert r"\label{annot-endnote:" not in latex
