"""Unit tests for latex_render module: NoEscape, escape_latex, latex_cmd, render_latex.

Tests the four components of the LaTeX rendering module:
- NoEscape: trusted string marker (str subclass)
- escape_latex: LaTeX special character escaping (10 chars)
- latex_cmd: programmatic LaTeX command builder
- render_latex: t-string renderer with auto-escaping

Verifies: AC4.3 (escape_latex special chars), AC4.5 (tag names with specials)
"""

from __future__ import annotations

import pytest

from promptgrimoire.export.latex_render import (
    NoEscape,
    escape_latex,
    latex_cmd,
    render_latex,
)


class TestNoEscape:
    """Tests for the NoEscape trusted-string marker."""

    def test_is_str_subclass(self) -> None:
        """NoEscape instances are regular strings."""
        assert isinstance(NoEscape("x"), str)

    def test_concatenation_preserves_content(self) -> None:
        """Concatenating two NoEscape values produces the expected string."""
        result = NoEscape("x") + NoEscape("y")
        assert result == "xy"

    def test_escape_latex_passthrough(self) -> None:
        """escape_latex returns NoEscape values unchanged."""
        val = NoEscape("already safe")
        assert escape_latex(val) is val


class TestEscapeLatex:
    """Tests for escape_latex: AC4.3 (10 LaTeX special characters)."""

    @pytest.mark.parametrize(
        ("char", "expected"),
        [
            ("#", "\\#"),
            ("$", "\\$"),
            ("%", "\\%"),
            ("&", "\\&"),
            ("_", "\\_"),
            ("{", "\\{"),
            ("}", "\\}"),
            ("~", "\\textasciitilde{}"),
            ("^", "\\textasciicircum{}"),
            ("\\", "\\textbackslash{}"),
        ],
        ids=[
            "hash",
            "dollar",
            "percent",
            "ampersand",
            "underscore",
            "lbrace",
            "rbrace",
            "tilde",
            "caret",
            "backslash",
        ],
    )
    def test_single_special_char(self, char: str, expected: str) -> None:
        """Each LaTeX special character is escaped correctly (AC4.3)."""
        assert escape_latex(char) == expected

    def test_passthrough_normal_text(self) -> None:
        """Normal text without specials passes through unchanged."""
        assert escape_latex("normal text") == "normal text"

    def test_combined_specials(self) -> None:
        """Multiple specials in one string are all escaped."""
        assert escape_latex("Cost: $30 & 50%") == "Cost: \\$30 \\& 50\\%"

    def test_tag_name_with_specials(self) -> None:
        """AC4.5: tag names containing LaTeX specials are escaped."""
        assert escape_latex("C#_notes") == "C\\#\\_notes"

    def test_noescape_passthrough(self) -> None:
        """NoEscape values are returned unchanged."""
        val = NoEscape("\\textbf{safe}")
        result = escape_latex(val)
        assert result is val

    def test_returns_noescape(self) -> None:
        """escape_latex returns a NoEscape instance."""
        result = escape_latex("hello")
        assert isinstance(result, NoEscape)


class TestLatexCmd:
    """Tests for latex_cmd: programmatic LaTeX command builder."""

    def test_simple_command(self) -> None:
        """Single-arg command produces correct LaTeX."""
        assert latex_cmd("textbf", "hello") == "\\textbf{hello}"

    def test_two_args(self) -> None:
        """Multi-arg command produces correct LaTeX."""
        result = latex_cmd("definecolor", "mycolor", "HTML", "FF0000")
        assert result == "\\definecolor{mycolor}{HTML}{FF0000}"

    def test_auto_escaping(self) -> None:
        """String args are auto-escaped for LaTeX specials."""
        assert latex_cmd("textbf", "C#_notes") == "\\textbf{C\\#\\_notes}"

    def test_noescape_arg(self) -> None:
        """NoEscape args are not re-escaped."""
        result = latex_cmd("textbf", NoEscape("\\em{x}"))
        assert result == "\\textbf{\\em{x}}"

    def test_returns_noescape(self) -> None:
        """latex_cmd returns a NoEscape instance."""
        assert isinstance(latex_cmd("textbf", "x"), NoEscape)


class TestRenderLatex:
    """Tests for render_latex: t-string renderer with auto-escaping."""

    def test_static_passthrough(self) -> None:
        """Static t-string with no interpolation passes through."""
        assert render_latex(t"hello world") == "hello world"

    def test_interpolation_escaping(self) -> None:
        """Interpolated values are auto-escaped."""
        val = "C#"
        assert render_latex(t"tag: {val}") == "tag: C\\#"

    def test_noescape_interpolation(self) -> None:
        """NoEscape interpolations are not re-escaped."""
        val = NoEscape("\\textbf{x}")
        assert render_latex(t"cmd: {val}") == "cmd: \\textbf{x}"

    def test_mixed_template(self) -> None:
        r"""Complex template with braces and interpolation works correctly.

        t"\\definecolor{{tag-{name}}}{{HTML}}{{FF0000}}" should produce
        \definecolor{tag-test\_tag}{HTML}{FF0000}
        """
        name = "test_tag"
        result = render_latex(t"\\definecolor{{tag-{name}}}{{HTML}}{{FF0000}}")
        assert result == "\\definecolor{tag-test\\_tag}{HTML}{FF0000}"
