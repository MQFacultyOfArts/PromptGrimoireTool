"""Unit tests for LaTeX export pure functions.

Tests string manipulation, formatting, and colour generation functions.
These are pure functions with no external dependencies (except LaTeX compilation).
Assertions use LaTeX AST parsing (pylatexenc) for structural validation.

Extracted from tests/unit/test_latex_export.py during Phase 5 reorganization.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from promptgrimoire.export.latex_format import format_annot_latex
from promptgrimoire.export.preamble import (
    _format_timestamp,
    generate_tag_colour_definitions,
)
from promptgrimoire.export.unicode_latex import escape_unicode_latex
from tests.conftest import requires_latexmk
from tests.helpers.latex_parse import (
    find_macros,
    get_body_text,
    get_mandatory_args,
    parse_latex,
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
        nodes = parse_latex(result)
        dcs = find_macros(nodes, "definecolor")

        # Find the tag-jurisdiction definecolor
        found = [
            d
            for d in dcs
            if get_mandatory_args(d) and get_mandatory_args(d)[0] == "tag-jurisdiction"
        ]
        assert len(found) == 1
        args = get_mandatory_args(found[0])
        assert args == ["tag-jurisdiction", "HTML", "1f77b4"]

    def test_multiple_tags(self) -> None:
        """Multiple tags should produce multiple definecolors."""
        result = generate_tag_colour_definitions(
            {
                "jurisdiction": "#1f77b4",
                "legal_issues": "#d62728",
            }
        )
        nodes = parse_latex(result)
        dcs = find_macros(nodes, "definecolor")
        names = {get_body_text(d) for d in dcs}

        assert "tag-jurisdiction" in names
        assert "tag-legal-issues" in names

    def test_underscore_converted_to_dash(self) -> None:
        """Underscores in tag names should become dashes."""
        result = generate_tag_colour_definitions({"my_tag_name": "#ffffff"})
        nodes = parse_latex(result)
        dcs = find_macros(nodes, "definecolor")
        names = {get_body_text(d) for d in dcs}

        assert "tag-my-tag-name" in names

    def test_hash_stripped_from_colour(self) -> None:
        """Hash should be stripped from colour value."""
        result = generate_tag_colour_definitions({"tag": "#AABBCC"})
        nodes = parse_latex(result)
        dcs = find_macros(nodes, "definecolor")

        tag_dc = [
            d
            for d in dcs
            if get_mandatory_args(d) and get_mandatory_args(d)[0] == "tag-tag"
        ]
        assert len(tag_dc) == 1
        args = get_mandatory_args(tag_dc[0])
        assert args[2] == "AABBCC"
        assert "#" not in args[2]

    def test_generates_dark_colour_variants(self) -> None:
        """Dark colour variants are generated for underlines."""
        result = generate_tag_colour_definitions({"alpha": "#1f77b4"})
        nodes = parse_latex(result)
        cls = find_macros(nodes, "colorlet")

        dark_cls = [c for c in cls if get_body_text(c) == "tag-alpha-dark"]
        assert len(dark_cls) == 1
        args = get_mandatory_args(dark_cls[0])
        assert args[0] == "tag-alpha-dark"
        assert args[1] == "tag-alpha!70!black"

    def test_generates_many_dark_colour(self) -> None:
        """many-dark colour (#333333) is always generated."""
        result = generate_tag_colour_definitions({"alpha": "#1f77b4"})
        nodes = parse_latex(result)
        dcs = find_macros(nodes, "definecolor")

        many = [
            d
            for d in dcs
            if get_mandatory_args(d) and get_mandatory_args(d)[0] == "many-dark"
        ]
        assert len(many) == 1
        args = get_mandatory_args(many[0])
        assert args == ["many-dark", "HTML", "333333"]


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
        result = format_annot_latex(highlight)
        nodes = parse_latex(result)
        annots = find_macros(nodes, "annot")

        assert len(annots) >= 1
        assert get_body_text(annots[0]) == "tag-jurisdiction"
        assert "Jurisdiction" in result
        assert "Alice" in result

    def test_uuid_tag_with_tag_name_displays_name(self) -> None:
        """When tag is a UUID but tag_name is provided, display name not UUID."""
        highlight = {
            "tag": "0bd64204-fce6-4069-ba38-920fae78eefc",
            "tag_name": "Jurisdiction",
            "author": "Alice",
            "text": "The court held",
            "comments": [],
            "created_at": "2026-01-26T14:30:00+00:00",
        }
        result = format_annot_latex(highlight)

        # Should display the human-readable name, not the UUID
        assert "Jurisdiction" in result
        assert "0bd64204" not in result.lower().replace("\\", "")

        # Colour name should still use the UUID (matches \definecolor)
        nodes = parse_latex(result)
        annots = find_macros(nodes, "annot")
        assert len(annots) >= 1
        assert get_body_text(annots[0]) == "tag-0bd64204-fce6-4069-ba38-920fae78eefc"

    def test_uuid_tag_without_tag_name_falls_back(self) -> None:
        """Without tag_name, UUID tags display as-is (legacy fallback)."""
        highlight = {
            "tag": "jurisdiction",
            "author": "Alice",
            "text": "The court held",
            "comments": [],
        }
        result = format_annot_latex(highlight)
        assert "Jurisdiction" in result

    def test_with_paragraph_reference(self) -> None:
        """Annotation with para ref should include it."""
        highlight = {
            "tag": "reasons",
            "author": "Bob",
            "text": "reasoning here",
            "comments": [],
        }
        result = format_annot_latex(highlight, para_ref="[45]")
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
        result = format_annot_latex(highlight)
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
        result = format_annot_latex(highlight)
        # The & should be escaped as a macro node
        assert r"\&" in result

    def test_escapes_special_characters_in_comments(self) -> None:
        """Special characters in comments should be escaped."""
        highlight = {
            "tag": "tag",
            "author": "User",
            "text": "some text",
            "comments": [{"author": "Bob", "text": "100% agree & more"}],
        }
        result = format_annot_latex(highlight)
        assert r"\%" in result
        assert r"\&" in result


# =============================================================================
# Compilation Validation Test
# =============================================================================


# Output directory for visual inspection
_OUTPUT_DIR = Path("output/test_output/latex_validation")


@pytest.mark.order("first")
@requires_latexmk
class TestCompilationValidation:
    """Validates that all string outputs actually compile with LuaLaTeX.

    This is the source of truth. The string assertion tests above are
    regression guards; this test proves the outputs are valid LaTeX.

    Output saved to: output/test_output/latex_validation/
    """

    @pytest.mark.asyncio
    async def test_all_outputs_compile_with_lualatex(self) -> None:
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

        # Create output directory for inspection (purge first for clean state)
        output_dir = Path(_OUTPUT_DIR)
        if output_dir.exists():
            import shutil

            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build comprehensive test content
        tag_colours = {
            "jurisdiction": "#1f77b4",
            "legal_issues": "#d62728",
            "my_tag_name": "#2ca02c",
        }
        colour_defs = generate_tag_colour_definitions(tag_colours)

        # Test all escape sequences in body text
        escaped_text = escape_unicode_latex(
            "Special chars: A & B, 100%, $50, #1, foo_bar, {braces}, ~tilde, ^caret"
        )

        # Test annotation with special characters in author and comments
        annot_special = format_annot_latex(
            {
                "tag": "jurisdiction",
                "author": "User & Co",
                "text": "test",
                "comments": [
                    {
                        "author": "Bob",
                        "text": "100% agree & $50 worth",
                    },
                ],
                "created_at": "2026-01-26T14:30:00+00:00",
            }
        )

        # Test annotation with paragraph reference
        annot_with_para = format_annot_latex(
            {
                "tag": "legal_issues",
                "author": "Alice",
                "text": "test",
                "comments": [],
            },
            para_ref="[45]",
        )

        # Test annotation with multiple comments
        annot_multi_comment = format_annot_latex(
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

        # Copy .sty to output directory so latexmk can find it
        import shutil

        from promptgrimoire.export.pdf_export import STY_SOURCE

        shutil.copy2(STY_SOURCE, output_dir / "promptgrimoire-export.sty")

        # Build complete document using .sty for static preamble content
        tex_content = rf"""
\documentclass[a4paper]{{article}}
\usepackage{{promptgrimoire-export}}
{colour_defs}

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
        pdf_path = await compile_latex(tex_path, output_dir=output_dir)

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


class TestUnicodeAnnotationEscaping:
    """Test unicode handling in annotation formatting."""

    def test_cjk_author_name_escaped(self) -> None:
        """CJK characters in author name are wrapped correctly."""

        result = escape_unicode_latex("田中太郎")
        nodes = parse_latex(result)
        cjks = find_macros(nodes, "cjktext")
        assert len(cjks) >= 1
        assert get_body_text(cjks[0]) == "田中太郎"

    def test_cjk_comment_text_escaped(self) -> None:
        """CJK characters in comment text are wrapped correctly."""

        result = escape_unicode_latex("これは日本語のコメントです")
        nodes = parse_latex(result)
        cjks = find_macros(nodes, "cjktext")
        assert len(cjks) >= 1

    def test_emoji_in_comment_escaped(self) -> None:
        """Emoji in comment text are wrapped correctly."""

        result = escape_unicode_latex("Great work! 🎉")
        nodes = parse_latex(result)
        emojis = find_macros(nodes, "emoji")
        assert len(emojis) >= 1

    def test_mixed_ascii_cjk_special_chars(self) -> None:
        """Mixed content with special chars handles all correctly."""

        result = escape_unicode_latex("User & 田中 100%")
        nodes = parse_latex(result)

        # CJK wrapped
        cjks = find_macros(nodes, "cjktext")
        assert len(cjks) >= 1
        assert get_body_text(cjks[0]) == "田中"

        # Special chars escaped (these are macro nodes)
        assert r"\&" in result
        assert r"\%" in result

    def test_format_annot_cjk_author(self) -> None:
        """CJK in author name is wrapped in _format_annot output."""
        highlight = {
            "tag": "tag",
            "author": "田中太郎",
            "text": "some text",
            "comments": [],
        }
        result = format_annot_latex(highlight)
        nodes = parse_latex(result)
        cjks = find_macros(nodes, "cjktext")
        bodies = {get_body_text(c) for c in cjks}
        assert "田中太郎" in bodies

    def test_format_annot_cjk_comment_author(self) -> None:
        """CJK in comment author is wrapped in _format_annot output."""
        highlight = {
            "tag": "tag",
            "author": "Alice",
            "text": "some text",
            "comments": [
                {"author": "山田花子", "text": "Comment text"},
            ],
        }
        result = format_annot_latex(highlight)
        nodes = parse_latex(result)
        cjks = find_macros(nodes, "cjktext")
        bodies = {get_body_text(c) for c in cjks}
        assert "山田花子" in bodies

    def test_format_annot_emoji_in_comment(self) -> None:
        """Emoji in comment text is wrapped in _format_annot output."""
        highlight = {
            "tag": "tag",
            "author": "Alice",
            "text": "some text",
            "comments": [
                {"author": "Bob", "text": "Great work! 🎉"},
            ],
        }
        result = format_annot_latex(highlight)
        nodes = parse_latex(result)
        emojis = find_macros(nodes, "emoji")
        assert len(emojis) >= 1

    def test_format_annot_mixed_unicode_and_special_chars(
        self,
    ) -> None:
        """Mixed unicode and special chars in _format_annot output."""
        highlight = {
            "tag": "tag",
            "author": "User & 田中",
            "text": "some text",
            "comments": [],
        }
        result = format_annot_latex(highlight)
        nodes = parse_latex(result)

        # Should have both escaped special char and wrapped CJK
        assert r"\&" in result
        cjks = find_macros(nodes, "cjktext")
        bodies = {get_body_text(c) for c in cjks}
        assert "田中" in bodies
