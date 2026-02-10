"""Tests that highlights spanning every standard HTML element produce valid LaTeX.

Verifies that \\annot commands (which contain \\par and \\marginalia) are never
placed inside LaTeX restricted contexts like \\section{}, \\subsection{}, etc.

Covers Issue #132: generalize LaTeX annotation splitting.

Each test creates HTML with a specific element, adds a highlight spanning its
content, runs the full export pipeline through convert_html_with_annotations,
and verifies the LaTeX output is structurally valid.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from promptgrimoire.export.pandoc import convert_html_with_annotations
from promptgrimoire.input_pipeline.html_input import extract_text_from_html

# Sectioning commands that are "moving arguments" in LaTeX — \par is forbidden inside
_SECTION_COMMANDS = (
    r"\section",
    r"\subsection",
    r"\subsubsection",
    r"\paragraph",
    r"\subparagraph",
)

# Regex to find \section{...}, \subsection{...}, etc. and extract their brace content.
# Uses a simple approach: find the command, then match balanced braces.
_SECTION_PATTERN = re.compile(
    r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?\{",
)


def _extract_brace_content(latex: str, open_pos: int) -> str:
    """Extract content between balanced braces starting at open_pos.

    Args:
        latex: Full LaTeX string.
        open_pos: Position of the opening '{'.

    Returns:
        Content between the braces (excluding the braces themselves).
    """
    depth = 0
    for i in range(open_pos, len(latex)):
        if latex[i] == "{":
            depth += 1
        elif latex[i] == "}":
            depth -= 1
            if depth == 0:
                return latex[open_pos + 1 : i]
    return latex[open_pos + 1 :]  # Unclosed brace — return rest


def _find_annots_in_sections(latex: str) -> list[str]:
    """Find any \\annot commands inside sectioning command arguments.

    Returns a list of problematic sections (empty if all clean).
    """
    problems = []
    for match in _SECTION_PATTERN.finditer(latex):
        cmd = match.group(0)
        brace_pos = match.end() - 1  # Position of '{'
        content = _extract_brace_content(latex, brace_pos)
        if r"\annot" in content:
            problems.append(f"{cmd}...}} contains \\annot")
    return problems


def _make_highlight(
    start: int,
    end: int,
    tag: str = "jurisdiction",
) -> dict[str, Any]:
    """Create a highlight dict for testing."""
    return {
        "start_char": start,
        "end_char": end,
        "tag": tag,
        "author": "Tester",
        "created_at": "2026-02-09T10:00:00+00:00",
        "comments": [],
    }


TAG_COLOURS = {"jurisdiction": "#1f77b4"}


class TestHighlightInHeadings:
    """Highlights spanning headings must not place \\annot inside \\section{}."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tag,html",
        [
            ("h1", "<h1>Case Title Here</h1><p>Body text.</p>"),
            ("h2", "<h2>Sub Heading</h2><p>Body text.</p>"),
            ("h3", "<h3>Sub Sub Heading</h3><p>Body text.</p>"),
            ("h4", "<h4>Paragraph Heading</h4><p>Body text.</p>"),
            ("h5", "<h5>Sub Paragraph</h5><p>Body text.</p>"),
            ("h6", "<h6>Minor Heading</h6><p>Body text.</p>"),
        ],
        ids=["h1", "h2", "h3", "h4", "h5", "h6"],
    )
    async def test_highlight_spanning_heading(self, tag: str, html: str) -> None:
        """Highlight covering heading text should not put \\annot inside \\section{}."""
        chars = extract_text_from_html(html)
        # Highlight the heading text (first element, before body)
        heading_end = min(10, len(chars))
        highlights = [_make_highlight(0, heading_end)]

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=TAG_COLOURS,
        )

        problems = _find_annots_in_sections(latex)
        assert not problems, (
            f"\\annot found inside sectioning command for <{tag}>: {problems}"
        )


class TestHighlightInInlineElements:
    """Highlights spanning inline formatting elements should produce valid LaTeX."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "desc,html",
        [
            ("strong", "<p>Hello <strong>bold text</strong> world.</p>"),
            ("em", "<p>Hello <em>italic text</em> world.</p>"),
            ("code", "<p>Hello <code>inline code</code> world.</p>"),
            ("link", '<p>Hello <a href="https://example.com">link text</a> world.</p>'),
            (
                "nested",
                "<p>Hello <strong><em>bold italic</em></strong> world.</p>",
            ),
        ],
        ids=["strong", "em", "code", "link", "nested-formatting"],
    )
    async def test_highlight_spanning_inline(self, desc: str, html: str) -> None:  # noqa: ARG002
        """Highlight spanning inline elements should produce valid LaTeX."""
        chars = extract_text_from_html(html)
        # Highlight the full text
        highlights = [_make_highlight(0, len(chars))]

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=TAG_COLOURS,
        )

        # Should have highlight markers and annotation
        assert r"\highLight" in latex
        assert r"\annot" in latex
        # No structural issues
        problems = _find_annots_in_sections(latex)
        assert not problems


class TestHighlightInBlockElements:
    """Highlights spanning block-level elements should produce valid LaTeX."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "desc,html",
        [
            (
                "unordered-list",
                "<ul><li>Item one</li><li>Item two</li></ul>",
            ),
            (
                "ordered-list",
                "<ol><li>First</li><li>Second</li></ol>",
            ),
            (
                "blockquote",
                "<blockquote><p>Quoted text here.</p></blockquote>",
            ),
            (
                "code-block",
                "<pre><code>def hello():\n    pass</code></pre>",
            ),
            (
                "table",
                "<table><tr><td>Cell A</td><td>Cell B</td></tr></table>",
            ),
            (
                "hr-with-text",
                "<p>Before rule.</p><hr><p>After rule.</p>",
            ),
        ],
        ids=[
            "unordered-list",
            "ordered-list",
            "blockquote",
            "code-block",
            "table",
            "hr-with-text",
        ],
    )
    async def test_highlight_spanning_block(self, desc: str, html: str) -> None:  # noqa: ARG002
        """Highlight spanning block elements should produce valid LaTeX."""
        chars = extract_text_from_html(html)
        if not chars:
            pytest.skip("No extractable text in this HTML")
        # Highlight the full text
        end = min(len(chars), 15)
        highlights = [_make_highlight(0, end)]

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=TAG_COLOURS,
        )

        # Code blocks become \begin{verbatim} which cannot contain
        # inline formatting — Pandoc strips all <span> elements inside
        # <pre><code>. This is a Pandoc/LaTeX limitation, not a bug.
        if r"\begin{verbatim}" in latex:
            assert "def hello" in latex  # content survives
        else:
            assert r"\highLight" in latex or r"\annot" in latex
        problems = _find_annots_in_sections(latex)
        assert not problems


class TestHighlightSpanningHeadingAndBody:
    """Highlight that starts in heading and continues into body text."""

    @pytest.mark.asyncio
    async def test_highlight_crossing_heading_boundary(self) -> None:
        """Highlight spanning from heading into paragraph should split correctly."""
        html = "<h1>Title</h1><p>Body text follows the heading.</p>"
        chars = extract_text_from_html(html)
        # Highlight from start of title into body
        highlights = [_make_highlight(0, min(20, len(chars)))]

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=TAG_COLOURS,
        )

        problems = _find_annots_in_sections(latex)
        assert not problems, f"\\annot found inside sectioning command: {problems}"
