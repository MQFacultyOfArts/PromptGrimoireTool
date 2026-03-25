"""Tests for bidirectional endnote cross-references — AC2.1 through AC2.4.

Verifies that annotation macros in ``promptgrimoire-export.sty`` produce
``\\label``/``\\hyperref`` pairs for bidirectional linking between inline
superscripts and endnote entries.

- AC2.1: Long annotations produce label/hyperref at inline location
- AC2.2: Endnote entries contain label/hyperref back-links
- AC2.3: Table-safe variants (\\annotref/\\annotendnote) produce matching pairs
- AC2.4: Short annotations (margin path) do NOT get hyperref linking

Tests use static analysis of the ``.sty`` file for macro definitions (since
``\\label``/``\\hyperref`` are generated at LaTeX compile time via ``\\write``,
not present in ``.tex`` output from Pandoc), plus a ``@requires_latexmk``
compilation test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from promptgrimoire.export.pandoc import convert_html_with_annotations
from promptgrimoire.export.pdf import compile_latex
from promptgrimoire.export.pdf_export import generate_tex_only
from tests.conftest import requires_latexmk, requires_pandoc

STY_PATH = (
    Path(__file__).parents[3]
    / "src"
    / "promptgrimoire"
    / "export"
    / "promptgrimoire-export.sty"
)


def _read_sty() -> str:
    """Read the LaTeX style file contents."""
    return STY_PATH.read_text()


def _extract_macro(sty: str, name: str) -> str:
    r"""Extract a \\newcommand definition body from the .sty file.

    Skips past ``\newcommand{\name}[N]`` prefix and returns the
    full definition body (outermost braces inclusive).
    """
    marker = rf"\newcommand{{\{name}}}"
    start = sty.find(marker)
    assert start != -1, f"Macro {name} not found in .sty"

    # Skip past \newcommand{\name} and optional [N] arg count
    i = start + len(marker)
    while i < len(sty) and sty[i] in " \t\n":
        i += 1
    # Skip optional argument count [N]
    if i < len(sty) and sty[i] == "[":
        close = sty.index("]", i)
        i = close + 1

    # Now find the body: next balanced {...} group
    assert sty[i] == "{", f"Expected body brace at {i}"
    depth = 0
    body_start = i
    while i < len(sty):
        if sty[i] == "{":
            depth += 1
        elif sty[i] == "}":
            depth -= 1
            if depth == 0:
                return sty[body_start : i + 1]
        i += 1
    msg = f"Unbalanced braces in macro {name}"
    raise ValueError(msg)


class TestAnnotMacroLongPath:
    r"""AC2.1 + AC2.2: \annot long-annotation path has bidirectional links."""

    def test_annot_long_path_has_inline_label(self) -> None:
        r"""Long path has \phantomsection\label{annot-inline:}."""
        sty = _read_sty()
        annot = _extract_macro(sty, "annot")
        # The long path (inside \ifdim\ht\annotbox>\annotmaxht) should have:
        assert r"\phantomsection\label{annot-inline:\theannotnum}" in annot

    def test_annot_long_path_has_inline_hyperref(self) -> None:
        r"""Long path wraps superscript in \hyperref."""
        sty = _read_sty()
        annot = _extract_macro(sty, "annot")
        assert r"\hyperref[annot-endnote:\theannotnum]" in annot

    def test_annot_write_has_endnote_label(self) -> None:
        r"""The \write block contains \noexpand\label{annot-endnote:...}."""
        sty = _read_sty()
        annot = _extract_macro(sty, "annot")
        assert r"\noexpand\label{annot-endnote:\theannotnum}" in annot

    def test_annot_write_has_endnote_hyperref(self) -> None:
        r"""The \write block contains \noexpand\hyperref[annot-inline:...]."""
        sty = _read_sty()
        annot = _extract_macro(sty, "annot")
        assert r"\noexpand\hyperref[annot-inline:\theannotnum]" in annot


class TestAnnotMacroShortPath:
    r"""AC2.4: \annot short-annotation path does NOT have hyperref linking."""

    def test_short_path_no_label(self) -> None:
        r"""The short path (\else branch) must NOT contain \label{annot-inline:...}."""
        sty = _read_sty()
        annot = _extract_macro(sty, "annot")
        # Split at \else to isolate the short path
        parts = annot.split(r"\else")
        assert len(parts) == 2, r"Expected exactly one \else in \annot"
        short_path = parts[1]
        assert r"\label{annot-inline:" not in short_path
        assert r"\hyperref[annot-endnote:" not in short_path


class TestAnnotrefMacro:
    r"""AC2.3: \annotref has inline label and hyperref."""

    def test_annotref_has_inline_label(self) -> None:
        r"""\annotref contains \phantomsection\label{annot-inline:...}."""
        sty = _read_sty()
        annotref = _extract_macro(sty, "annotref")
        assert r"\phantomsection\label{annot-inline:\theannotnum}" in annotref

    def test_annotref_has_hyperref(self) -> None:
        r"""\annotref wraps superscript in \hyperref[annot-endnote:...]."""
        sty = _read_sty()
        annotref = _extract_macro(sty, "annotref")
        assert r"\hyperref[annot-endnote:\theannotnum]" in annotref


class TestAnnotendnoteMacro:
    r"""AC2.3: \annotendnote has endnote label and back-link hyperref."""

    def test_annotendnote_has_endnote_label(self) -> None:
        r"""\annotendnote's \write block contains \noexpand\label{annot-endnote:...}."""
        sty = _read_sty()
        endnote = _extract_macro(sty, "annotendnote")
        assert r"\noexpand\label{annot-endnote:" in endnote

    def test_annotendnote_has_back_hyperref(self) -> None:
        r"""\annotendnote \write has back-link \hyperref."""
        sty = _read_sty()
        endnote = _extract_macro(sty, "annotendnote")
        assert r"\noexpand\hyperref[annot-inline:" in endnote


class TestLinkAffordance:
    """Cross-reference links must have visible click affordance."""

    def test_inline_superscript_has_link_icon(self) -> None:
        r"""The inline superscript in \annot long path has a link icon."""
        sty = _read_sty()
        annot = _extract_macro(sty, "annot")
        # The long path's hyperref-wrapped superscript must contain
        # a visible indicator that it's clickable (not just hidelinks)
        long_path = annot.split(r"\else")[0]
        # Look for a link icon character inside the hyperref block
        assert "\\,\\textsuperscript{\\linkicon}" in long_path or (
            "\\linkicon" in long_path
        ), "Inline superscript needs visible link affordance"

    def test_see_endnotes_stub_has_link_icon(self) -> None:
        r"""The 'see endnotes' margin stub has a visible link icon."""
        sty = _read_sty()
        annot = _extract_macro(sty, "annot")
        long_path = annot.split(r"\else")[0]
        # The margin note for long annotations must contain a
        # link icon so users know they can navigate to the endnote
        assert "see endnotes" in long_path
        # Find the marginalia block containing "see endnotes"
        margin_start = long_path.find(r"\marginalia")
        margin_section = long_path[margin_start:]
        assert r"\linkicon" in margin_section, (
            "Margin stub needs visible link affordance"
        )

    def test_endnote_back_link_has_icon(self) -> None:
        r"""Endnote number back-link has a visible link icon."""
        sty = _read_sty()
        annot = _extract_macro(sty, "annot")
        # In the \write block, the hyperref-wrapped endnote number
        # should include a visible icon
        assert r"\noexpand\linkicon" in annot, (
            "Endnote back-link needs visible link affordance"
        )

    def test_annotref_has_link_icon(self) -> None:
        r"""\annotref superscript has a visible link icon."""
        sty = _read_sty()
        annotref = _extract_macro(sty, "annotref")
        assert r"\linkicon" in annotref, "annotref needs visible link affordance"

    def test_annotendnote_has_link_icon(self) -> None:
        r"""\annotendnote back-link has a visible link icon."""
        sty = _read_sty()
        endnote = _extract_macro(sty, "annotendnote")
        assert r"\noexpand\linkicon" in endnote, (
            "annotendnote needs visible link affordance"
        )

    def test_linkicon_command_defined(self) -> None:
        r"""The \linkicon command is defined in the .sty file."""
        sty = _read_sty()
        assert r"\newcommand{\linkicon}" in sty, (
            r"\linkicon command must be defined in the .sty"
        )


@requires_pandoc
class TestShortAnnotationNoLinks:
    """AC2.4: Document with only short annotations has no cross-reference links."""

    @pytest.mark.asyncio
    async def test_short_annotations_no_label_hyperref(self) -> None:
        """Short annotations produce \\annot but no label/hyperref.

        The Pandoc output contains \\annot{} commands (positive),
        but no \\label or \\hyperref (negative). The \\label/\\hyperref
        commands are only emitted at LaTeX compile time via the
        long-path \\write block, so they should never appear in the
        .tex source for short-only annotations. Static analysis
        tests (TestAnnotMacroShortPath) verify the .sty level.
        """
        html = "<p>Some text with a short note.</p>"
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 9,
                "tag": "issue",
                "text": "Some text",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                "comments": [],
            },
        ]
        tag_colours = {"issue": "#e377c2"}

        latex = await convert_html_with_annotations(
            html=html,
            highlights=highlights,
            tag_colours=tag_colours,
        )
        # Pipeline should produce \annot commands
        assert r"\annot{" in latex
        # Negative: no cross-reference commands in .tex source
        assert r"\label{annot-inline:" not in latex
        assert r"\hyperref[annot-endnote:" not in latex


@requires_latexmk
class TestCrossrefCompilation:
    """Compilation test: bidirectional cross-references compile without errors."""

    @pytest.mark.asyncio
    async def test_document_with_annotations_compiles(self, tmp_path: Path) -> None:
        """A document with annotations compiles to PDF (two-pass via latexmk).

        This exercises the \\label/\\hyperref pairs in the compiled document.
        The test cannot verify clickable links, but confirms no LaTeX errors
        from the cross-reference machinery.
        """
        # Create HTML with a highlight that will produce an \annot command
        html = (
            "<p>First paragraph with some highlighted text that needs "
            "an annotation. This is a fairly long paragraph with enough "
            "content to potentially trigger the endnote path depending "
            "on margin width calculations. We add more text here to "
            "ensure we have sufficient content for the annotation to "
            "be meaningful in the export.</p>"
            "<p>Second paragraph without annotations.</p>"
        )
        highlights = [
            {
                "id": "h1",
                "start_char": 0,
                "end_char": 45,
                "tag": "issue",
                "text": "First paragraph with some highlighted text",
                "author": "Alice",
                "created_at": "2026-01-26T10:00:00+00:00",
                "comments": [
                    {
                        "author": "Bob",
                        "text": "This is a detailed comment about the issue "
                        "that provides enough content to push the annotation "
                        "beyond the margin height threshold, triggering the "
                        "endnote path. We need quite a bit of text here to "
                        "ensure the annotation is long enough.",
                        "created_at": "2026-01-26T11:00:00+00:00",
                    },
                ],
            },
        ]
        tag_colours = {"issue": "#e377c2"}

        tex_path = await generate_tex_only(
            html_content=html,
            highlights=highlights,
            tag_colours=tag_colours,
            output_dir=tmp_path,
        )
        assert tex_path.exists()

        pdf_path = await compile_latex(tex_path)
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
