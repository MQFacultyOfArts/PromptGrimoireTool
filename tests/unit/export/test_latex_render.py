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


class TestRenderLatexConversions:
    """Characterisation tests for conversion specifiers (!r, !s, !a) and
    format specs -- these branches were previously untested and are the
    source of most of render_latex's cognitive complexity (a nested
    if/elif chain), so they must be pinned down before refactoring.
    """

    def test_repr_conversion_applied_before_escaping(self) -> None:
        """!r applies repr() to the value, then the LaTeX-special result
        (the quotes from repr are not special, the & is) is escaped."""
        val = "a&b"
        result = render_latex(t"{val!r}")
        assert result == "'a\\&b'"

    def test_str_conversion_applied(self) -> None:
        """!s applies str() to the value before escaping."""

        class Wrapper:
            def __str__(self) -> str:
                return "wrapped#value"

        result = render_latex(t"{Wrapper()!s}")
        assert result == "wrapped\\#value"

    def test_ascii_conversion_applied(self) -> None:
        """!a applies ascii() (backslash-escaping non-ASCII) before LaTeX
        escaping, so the backslashes ascii() introduces are themselves
        escaped to \\textbackslash{}."""
        val = "café"
        result = render_latex(t"{val!a}")
        assert result == "'caf\\textbackslash{}xe9'"

    def test_no_conversion_leaves_value_untouched(self) -> None:
        """Absence of a conversion specifier applies none of !r/!s/!a."""
        result = render_latex(t"{42}")
        assert result == "42"

    def test_format_spec_applied(self) -> None:
        """A format spec (e.g. .2f) is applied via format() before escaping."""
        result = render_latex(t"{3.14159:.2f}")
        assert result == "3.14"

    def test_format_spec_combined_with_conversion(self) -> None:
        """Conversion runs first, then the format spec is applied to the
        converted (string) value -- matching f-string evaluation order."""
        result = render_latex(t"{42!r:>6}")
        assert result == "    42"

    def test_noescape_without_format_spec_stays_unescaped(self) -> None:
        """A NoEscape value with no format spec passes through verbatim."""
        val = NoEscape(r"\textbf{x}")
        result = render_latex(t"{val}")
        assert result == "\\textbf{x}"

    def test_noescape_with_format_spec_loses_trust_marker(self) -> None:
        """Documented gotcha: str.__format__ on a str subclass always
        returns a plain str (verified directly against builtins, not
        against this module), so applying a format spec to a NoEscape
        value strips the NoEscape marker and the padded result gets
        escaped like untrusted text. This is current behaviour, not
        necessarily desired behaviour -- pinned here so a refactor
        cannot silently change it either way.
        """
        val = NoEscape(r"\textbf{x}")
        assert type(format(val, ">20")) is str
        result = render_latex(t"{val:>20}")
        assert result == "          \\textbackslash{}textbf\\{x\\}"
