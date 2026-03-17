"""Tests for LaTeX escaping in headings.

Verifies that fragile commands are handled correctly when they appear
inside section headings (LaTeX "moving arguments"). Covers:

1. Annotations on heading text — \\annot must be moved outside \\section{}
2. Annotations on bold heading text — \\annot nested inside \\textbf must
   also be extracted (Gemini review: extract_annots depth bug)
3. Emoji in headings — \\BeginAccSupp must not appear inside \\section{}
4. \\textquotesingle in headings — must be replaced with safe literal
5. HTML <u> tags — soul's \\ul{} must not wrap lua-ul \\underLine

Regression tests for issue #372.
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.pandoc import convert_html_to_latex

# Path to highlight.lua filter (used by the annotation pipeline)
_HIGHLIGHT_FILTER = (
    __import__("pathlib").Path(__file__).parent.parent.parent.parent
    / "src"
    / "promptgrimoire"
    / "export"
    / "filters"
    / "highlight.lua"
)


class TestAnnotOnHeading:
    """Annotations on heading text must be moved outside \\section{}."""

    @pytest.mark.asyncio
    async def test_annot_on_plain_heading(self) -> None:
        """\\annot on a plain heading is moved after \\section{}."""
        html = (
            '<h2><span data-hl="1" data-colors="red-light" '
            'data-annots="\\annot{red}{Test comment}">Heading Text</span></h2>'
            "<p>Body paragraph.</p>"
        )
        latex = await convert_html_to_latex(html, filter_paths=[_HIGHLIGHT_FILTER])

        # The annot must NOT be inside \section{...}
        assert r"\section" in latex or r"\subsection" in latex
        # Check that \annot appears AFTER the section command, not inside it
        section_line = next(
            line
            for line in latex.splitlines()
            if r"\section" in line or r"\subsection" in line
        )
        assert r"\annot" not in section_line, (
            f"\\annot found inside heading: {section_line}"
        )
        # But the annot must still exist somewhere in the output
        assert r"\annot{red}{Test comment}" in latex

    @pytest.mark.asyncio
    async def test_annot_on_bold_heading(self) -> None:
        """\\annot nested inside \\textbf{} in a heading is still extracted.

        Regression: extract_annots only walks direct children of Header,
        missing annots inside Strong/Emph nodes.
        """
        html = (
            '<h2><strong><span data-hl="1" data-colors="blue-light" '
            'data-annots="\\annot{blue}{Nested comment}">'
            "Bold Heading</span></strong></h2>"
            "<p>Body.</p>"
        )
        latex = await convert_html_to_latex(html, filter_paths=[_HIGHLIGHT_FILTER])

        # Extract the full \subsection{...} command including its brace group.
        # The command may span multiple lines, so line-by-line check is wrong.
        assert r"\subsection" in latex
        # Find everything between \subsection{ and the matching }
        import re

        section_match = re.search(r"\\subsection\{", latex)
        assert section_match is not None
        # Walk from the { after \subsection to find matching }
        depth = 0
        start = section_match.start()
        section_end = start
        for i in range(section_match.end() - 1, len(latex)):
            if latex[i] == "{":
                depth += 1
            elif latex[i] == "}":
                depth -= 1
                if depth == 0:
                    section_end = i
                    break
        section_cmd = latex[start : section_end + 1]

        assert r"\annot" not in section_cmd, (
            f"\\annot found inside bold heading: {section_cmd}"
        )
        assert r"\annot{blue}{Nested comment}" in latex


class TestEmojiInHeading:
    """Emoji AccSupp wrapping must not appear inside \\section{}."""

    @pytest.mark.asyncio
    async def test_emoji_in_heading_no_accsupp(self) -> None:
        """\\BeginAccSupp must be stripped from headings."""
        html = "<h2>🔴 Critical Warning</h2><p>Body.</p>"
        latex = await convert_html_to_latex(html, filter_paths=[_HIGHLIGHT_FILTER])

        section_line = next(
            line
            for line in latex.splitlines()
            if r"\section" in line or r"\subsection" in line
        )
        assert r"\BeginAccSupp" not in section_line, (
            f"AccSupp found inside heading: {section_line}"
        )


class TestTextquotesingleInHeading:
    """\\textquotesingle must be replaced with safe literal."""

    @pytest.mark.asyncio
    async def test_apostrophe_in_heading(self) -> None:
        """French apostrophe in heading must not crash LaTeX."""
        html = "<h2>L'ABRI MAINTENANT</h2><p>Body.</p>"
        latex = await convert_html_to_latex(html, filter_paths=[_HIGHLIGHT_FILTER])

        # \textquotesingle must not appear anywhere (it's fragile)
        assert r"\textquotesingle" not in latex, (
            "\\textquotesingle should be replaced with literal apostrophe"
        )
        # The apostrophe should be preserved as a safe character
        assert "ABRI" in latex


class TestHtmlUnderlineTag:
    """HTML <u> must not produce soul's fragile \\ul{}."""

    @pytest.mark.asyncio
    async def test_u_tag_no_soul_ul(self) -> None:
        """<u> tags must produce \\underLine (lua-ul), not \\ul (soul)."""
        html = "<p><u>Underlined text</u></p>"
        latex = await convert_html_to_latex(html, filter_paths=[_HIGHLIGHT_FILTER])

        assert r"\ul{" not in latex, (
            "soul's \\ul{} found — should use lua-ul's \\underLine instead"
        )
        # The underline should still be present
        assert "Underlined" in latex

    @pytest.mark.asyncio
    async def test_u_tag_with_highlights_no_crash(self) -> None:
        """<u> tag wrapping highlighted text must not crash.

        This is the exact production failure: <u>My Will</u> where
        "My Will" also has annotation highlights.
        """
        html = (
            '<p><u><span data-hl="1" data-colors="red-light" '
            'data-annots="\\annot{red}{Comment}">My Will</span></u></p>'
        )
        latex = await convert_html_to_latex(html, filter_paths=[_HIGHLIGHT_FILTER])

        assert r"\ul{" not in latex, (
            "soul's \\ul{} wrapping \\underLine — this crashes LaTeX"
        )
        assert "My" in latex
        assert "Will" in latex
