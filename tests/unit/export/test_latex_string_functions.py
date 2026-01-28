"""Unit tests for LaTeX export pure functions.

Tests string manipulation, formatting, and colour generation functions.
These are pure functions with no external dependencies (except LaTeX compilation).

Extracted from tests/unit/test_latex_export.py during Phase 5 reorganization.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from promptgrimoire.export.latex import (
    ANNOTATION_PREAMBLE_BASE,
    _escape_latex,
    _format_annot,
    _format_timestamp,
    generate_tag_colour_definitions,
)


class TestFormatTimestamp:
    """Tests for _format_timestamp function."""

    def test_valid_iso_timestamp(self) -> None:
        """Valid ISO timestamp should be formatted."""
        result = _format_timestamp("2026-01-26T14:30:00+00:00")
        assert "26" in result
        assert "Jan" in result
        assert "2026" in result
        assert "14:30" in result

    def test_invalid_timestamp_returns_empty(self) -> None:
        """Invalid timestamp should return empty string."""
        assert _format_timestamp("not-a-date") == ""

    def test_empty_timestamp_returns_empty(self) -> None:
        """Empty timestamp should return empty string."""
        assert _format_timestamp("") == ""


class TestGenerateTagColourDefinitions:
    """Tests for generate_tag_colour_definitions function."""

    def test_single_tag(self) -> None:
        """Single tag should produce one definecolor."""
        result = generate_tag_colour_definitions({"jurisdiction": "#1f77b4"})
        assert r"\definecolor{tag-jurisdiction}{HTML}{1f77b4}" in result

    def test_multiple_tags(self) -> None:
        """Multiple tags should produce multiple definecolors."""
        result = generate_tag_colour_definitions(
            {
                "jurisdiction": "#1f77b4",
                "legal_issues": "#d62728",
            }
        )
        assert r"\definecolor{tag-jurisdiction}{HTML}{1f77b4}" in result
        assert r"\definecolor{tag-legal-issues}{HTML}{d62728}" in result

    def test_underscore_converted_to_dash(self) -> None:
        """Underscores in tag names should become dashes."""
        result = generate_tag_colour_definitions({"my_tag_name": "#ffffff"})
        assert "tag-my-tag-name" in result

    def test_hash_stripped_from_colour(self) -> None:
        """Hash should be stripped from colour value."""
        result = generate_tag_colour_definitions({"tag": "#AABBCC"})
        assert "{AABBCC}" in result
        assert "##" not in result

    def test_generates_dark_colour_variants(self) -> None:
        """Dark colour variants are generated for underlines."""
        tag_colours = {"alpha": "#1f77b4"}
        result = generate_tag_colour_definitions(tag_colours)

        assert "tag-alpha-dark" in result
        # Dark is 70% of base mixed with black
        assert r"\colorlet{tag-alpha-dark}{tag-alpha!70!black}" in result

    def test_generates_many_dark_colour(self) -> None:
        """many-dark colour (#333333) is always generated."""
        tag_colours = {"alpha": "#1f77b4"}
        result = generate_tag_colour_definitions(tag_colours)

        assert r"\definecolor{many-dark}{HTML}{333333}" in result


class TestFormatAnnot:
    """Tests for _format_annot function."""

    def test_basic_annotation(self) -> None:
        """Basic annotation should produce valid annot command."""
        highlight = {
            "tag": "jurisdiction",
            "author": "Alice",
            "text": "The court held",
            "comments": [],
            "created_at": "2026-01-26T14:30:00+00:00",
        }
        result = _format_annot(highlight)
        assert r"\annot{tag-jurisdiction}" in result
        assert "Jurisdiction" in result  # Tag display name
        assert "Alice" in result

    def test_with_paragraph_reference(self) -> None:
        """Annotation with para ref should include it."""
        highlight = {
            "tag": "reasons",
            "author": "Bob",
            "text": "reasoning here",
            "comments": [],
        }
        result = _format_annot(highlight, para_ref="[45]")
        assert "[45]" in result

    def test_with_comments(self) -> None:
        """Annotation with comments should include them."""
        highlight = {
            "tag": "decision",
            "author": "Alice",
            "text": "decision text",
            "comments": [
                {"author": "Bob", "text": "Good point"},
                {"author": "Carol", "text": "I agree"},
            ],
        }
        result = _format_annot(highlight)
        assert "Bob" in result
        assert "Good point" in result
        assert "Carol" in result
        assert "I agree" in result

    def test_escapes_special_characters_in_author(self) -> None:
        """Special characters in author should be escaped."""
        highlight = {
            "tag": "tag",
            "author": "User & Co",
            "text": "some text",
            "comments": [],
        }
        result = _format_annot(highlight)
        assert r"\&" in result

    def test_escapes_special_characters_in_comments(self) -> None:
        """Special characters in comments should be escaped."""
        highlight = {
            "tag": "tag",
            "author": "User",
            "text": "some text",
            "comments": [{"author": "Bob", "text": "100% agree & more"}],
        }
        result = _format_annot(highlight)
        assert r"\%" in result
        assert r"\&" in result


# =============================================================================
# Compilation Validation Test
# =============================================================================


def _has_latexmk() -> bool:
    """Check if latexmk is available via TinyTeX."""
    from promptgrimoire.export.pdf import get_latexmk_path

    try:
        get_latexmk_path()
        return True
    except FileNotFoundError:
        return False


requires_latexmk = pytest.mark.skipif(
    not _has_latexmk(), reason="latexmk not installed"
)


# Output directory for visual inspection
_OUTPUT_DIR = Path("output/test_output/latex_validation")


@requires_latexmk
class TestCompilationValidation:
    """Validates that all string outputs actually compile with LuaLaTeX.

    This is the source of truth. The string assertion tests above are
    regression guards; this test proves the outputs are valid LaTeX.

    Output saved to: output/test_output/latex_validation/
    """

    def test_all_outputs_compile_with_lualatex(self) -> None:
        """Compile a document containing all test outputs.

        EXPECTED PDF CONTENT (for visual inspection):
        =============================================

        1. ESCAPE SEQUENCES section should show literal text:
           "Special chars: A & B, 100%, $50, #1, foo_bar, {braces}, ~tilde, ^caret"
           - All special characters should render as their literal symbols
           - No LaTeX errors or missing characters

        2. ANNOTATION 1 (blue, "Jurisdiction" tag):
           - Superscript number "1" in blue
           - Blue margin box containing:
             - "Jurisdiction" (bold)
             - "User & Co, 26 Jan 2026 14:30" (small)
             - Separator line
             - "Bob, [no date]: 100% agree & $50 worth"

        3. ANNOTATION 2 (red, "Legal Issues" tag):
           - Superscript number "2" in red
           - Red margin box containing:
             - "Legal Issues [45]" (bold, with para ref)
             - "Alice" (small)

        4. ANNOTATION 3 (green, "My Tag Name" tag):
           - Superscript number "3" in green
           - Green margin box containing:
             - "My Tag Name" (bold)
             - "Carol" (small)
             - Separator line
             - Two comments from Dave and Eve

        If any of the above is missing or malformed, the string
        transformation functions are producing invalid LaTeX.
        """
        from promptgrimoire.export.pdf import compile_latex

        # Create output directory for inspection
        output_dir = Path(_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build comprehensive test content
        tag_colours = {
            "jurisdiction": "#1f77b4",
            "legal_issues": "#d62728",
            "my_tag_name": "#2ca02c",
        }
        colour_defs = generate_tag_colour_definitions(tag_colours)

        # Test all escape sequences in body text
        escaped_text = _escape_latex(
            "Special chars: A & B, 100%, $50, #1, foo_bar, {braces}, ~tilde, ^caret"
        )

        # Test annotation with special characters in author and comments
        annot_special = _format_annot(
            {
                "tag": "jurisdiction",
                "author": "User & Co",
                "text": "test",
                "comments": [
                    {"author": "Bob", "text": "100% agree & $50 worth"},
                ],
                "created_at": "2026-01-26T14:30:00+00:00",
            }
        )

        # Test annotation with paragraph reference
        annot_with_para = _format_annot(
            {
                "tag": "legal_issues",
                "author": "Alice",
                "text": "test",
                "comments": [],
            },
            para_ref="[45]",
        )

        # Test annotation with multiple comments
        annot_multi_comment = _format_annot(
            {
                "tag": "my_tag_name",
                "author": "Carol",
                "text": "test",
                "comments": [
                    {"author": "Dave", "text": "First comment"},
                    {"author": "Eve", "text": "Second comment"},
                ],
            }
        )

        # Build complete document
        tex_content = rf"""
\documentclass[a4paper]{{article}}
\usepackage{{xcolor}}
{colour_defs}
{ANNOTATION_PREAMBLE_BASE}

\begin{{document}}

\section*{{Escape Sequence Validation}}
{escaped_text}

\section*{{Annotation Validation}}
Test text with annotation.{annot_special}

More text with para ref.{annot_with_para}

Final text with comments.{annot_multi_comment}

\end{{document}}
"""

        tex_path = output_dir / "string_validation.tex"
        tex_path.write_text(tex_content)

        # Compile - this is the real test
        pdf_path = compile_latex(tex_path, output_dir=output_dir)

        assert pdf_path.exists(), f"PDF not created at {pdf_path}"
        with pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF", f"Invalid PDF header: {header!r}"

        # Validate LaTeX log for errors (not warnings - overfull boxes are OK)
        log_path = output_dir / "string_validation.log"
        log_text = log_path.read_text()

        # Fatal errors start with "! " in LaTeX logs
        fatal_errors = [line for line in log_text.split("\n") if line.startswith("! ")]
        assert not fatal_errors, "LaTeX fatal errors:\n" + "\n".join(fatal_errors)

        # Check for specific error patterns
        assert "Undefined control sequence" not in log_text, (
            "Undefined control sequence - a command wasn't defined"
        )
        assert "Missing $ inserted" not in log_text, (
            "Missing $ - unescaped special character in math context"
        )
        assert "Missing } inserted" not in log_text, "Missing } - unbalanced braces"
        assert "Missing { inserted" not in log_text, "Missing { - unbalanced braces"

        print(f"\n\nPDF saved for visual inspection: {pdf_path.absolute()}")
        print(f"TeX source: {tex_path.absolute()}")
        print(f"Log file: {log_path.absolute()}")
