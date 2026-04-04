"""Tests for LaTeX AST parse helpers.

Validates that parse_latex, find_macros, get_opt_arg, get_body_text
correctly parse the macro structures produced by the export pipeline.
"""

from __future__ import annotations

from tests.helpers.latex_parse import (
    find_macros,
    get_body_text,
    get_mandatory_args,
    get_opt_arg,
    parse_latex,
)


class TestParseLaTeX:
    """Tests for parse_latex function."""

    def test_plain_text_returns_nodes(self) -> None:
        """Plain text parses into a non-empty node list."""
        nodes = parse_latex("hello world")
        assert len(nodes) > 0

    def test_known_macro_parsed(self) -> None:
        """A known macro like \\highLight is parsed as a macro node."""
        nodes = parse_latex(r"\highLight[tag-a-light]{text}")
        macros = find_macros(nodes, "highLight")
        assert len(macros) == 1

    def test_unknown_macro_still_parsed(self) -> None:
        """Unknown macros (e.g. \\par) don't crash the parser."""
        nodes = parse_latex(r"before \par after")
        assert len(nodes) > 0

    def test_nested_macros_parsed(self) -> None:
        """Nested macros like \\highLight{\\underLine{text}} are parsed."""
        latex = (
            r"\highLight[tag-a-light]"
            r"{\underLine[color=x, height=1pt, bottom=-3pt]{inner}}"
        )
        nodes = parse_latex(latex)
        highlights = find_macros(nodes, "highLight")
        assert len(highlights) == 1
        underlines = find_macros(nodes, "underLine")
        assert len(underlines) == 1


class TestFindMacros:
    """Tests for find_macros function."""

    def test_finds_single_macro(self) -> None:
        """Finds a single top-level macro."""
        nodes = parse_latex(r"\annot{tag-jurisdiction}")
        found = find_macros(nodes, "annot")
        assert len(found) == 1

    def test_finds_multiple_macros(self) -> None:
        """Finds multiple occurrences of the same macro."""
        latex = r"\highLight[a]{text1}\highLight[b]{text2}"
        nodes = parse_latex(latex)
        found = find_macros(nodes, "highLight")
        assert len(found) == 2

    def test_finds_nested_macro(self) -> None:
        """Finds macros nested inside other macros' arguments."""
        latex = r"\highLight[a]{\underLine[b]{text}}"
        nodes = parse_latex(latex)
        found = find_macros(nodes, "underLine")
        assert len(found) == 1

    def test_returns_empty_for_absent_macro(self) -> None:
        """Returns empty list when macro not present."""
        nodes = parse_latex("plain text")
        found = find_macros(nodes, "highLight")
        assert found == []

    def test_finds_definecolor(self) -> None:
        """Finds \\definecolor macros (3 mandatory args)."""
        latex = r"\definecolor{tag-alpha}{HTML}{1f77b4}"
        nodes = parse_latex(latex)
        found = find_macros(nodes, "definecolor")
        assert len(found) == 1

    def test_finds_colorlet(self) -> None:
        """Finds \\colorlet macros (2 mandatory args)."""
        latex = r"\colorlet{tag-alpha-dark}{tag-alpha!70!black}"
        nodes = parse_latex(latex)
        found = find_macros(nodes, "colorlet")
        assert len(found) == 1

    def test_finds_cjktext(self) -> None:
        """Finds \\cjktext macros."""
        latex = r"\cjktext{田中太郎}"
        nodes = parse_latex(latex)
        found = find_macros(nodes, "cjktext")
        assert len(found) == 1

    def test_finds_emoji(self) -> None:
        """Finds \\emoji macros."""
        latex = r"\emoji{🎉}"
        nodes = parse_latex(latex)
        found = find_macros(nodes, "emoji")
        assert len(found) == 1


class TestGetOptArg:
    """Tests for get_opt_arg function."""

    def test_extracts_optional_arg(self) -> None:
        """Extracts the text content of an optional [arg]."""
        nodes = parse_latex(r"\highLight[tag-a-light]{text}")
        macro = find_macros(nodes, "highLight")[0]
        assert get_opt_arg(macro) == "tag-a-light"

    def test_returns_none_when_no_opt_arg(self) -> None:
        """Returns None when macro has no optional arg."""
        nodes = parse_latex(r"\annot{tag-jurisdiction}")
        macro = find_macros(nodes, "annot")[0]
        assert get_opt_arg(macro) is None

    def test_extracts_complex_optional_arg(self) -> None:
        """Extracts complex optional args like underLine colour specs."""
        latex = r"\underLine[color=tag-alpha-dark, height=1pt, bottom=-3pt]{text}"
        nodes = parse_latex(latex)
        macro = find_macros(nodes, "underLine")[0]
        opt = get_opt_arg(macro)
        assert opt is not None
        assert "tag-alpha-dark" in opt
        assert "height=1pt" in opt


class TestGetBodyText:
    """Tests for get_body_text function."""

    def test_extracts_simple_body(self) -> None:
        """Extracts plain text from a simple {body}."""
        nodes = parse_latex(r"\annot{tag-jurisdiction}")
        macro = find_macros(nodes, "annot")[0]
        assert get_body_text(macro) == "tag-jurisdiction"

    def test_extracts_body_through_nested_macros(self) -> None:
        """Recurses through nested macros to extract leaf text."""
        latex = (
            r"\highLight[tag-a-light]"
            r"{\underLine[color=x, height=1pt, bottom=-3pt]{hello}}"
        )
        nodes = parse_latex(latex)
        macro = find_macros(nodes, "highLight")[0]
        assert get_body_text(macro) == "hello"

    def test_extracts_body_from_underline(self) -> None:
        """Gets the text wrapped by \\underLine."""
        latex = r"\underLine[color=tag-alpha-dark, height=1pt, bottom=-3pt]{some text}"
        nodes = parse_latex(latex)
        macro = find_macros(nodes, "underLine")[0]
        assert get_body_text(macro) == "some text"

    def test_extracts_cjk_body(self) -> None:
        """Gets CJK text from \\cjktext body."""
        nodes = parse_latex(r"\cjktext{田中太郎}")
        macro = find_macros(nodes, "cjktext")[0]
        assert get_body_text(macro) == "田中太郎"

    def test_extracts_definecolor_first_mandatory_arg(self) -> None:
        """Gets the colour name from \\definecolor (first mandatory arg)."""
        latex = r"\definecolor{tag-alpha}{HTML}{1f77b4}"
        nodes = parse_latex(latex)
        macro = find_macros(nodes, "definecolor")[0]
        # get_body_text returns the first mandatory arg's text
        assert get_body_text(macro) == "tag-alpha"

    def test_get_mandatory_args_definecolor(self) -> None:
        """Gets all 3 mandatory args from \\definecolor."""
        latex = r"\definecolor{tag-alpha}{HTML}{1f77b4}"
        nodes = parse_latex(latex)
        macro = find_macros(nodes, "definecolor")[0]
        args = get_mandatory_args(macro)
        assert args == ["tag-alpha", "HTML", "1f77b4"]

    def test_get_mandatory_args_colorlet(self) -> None:
        """Gets both mandatory args from \\colorlet."""
        latex = r"\colorlet{tag-alpha-dark}{tag-alpha!70!black}"
        nodes = parse_latex(latex)
        macro = find_macros(nodes, "colorlet")[0]
        args = get_mandatory_args(macro)
        assert args == ["tag-alpha-dark", "tag-alpha!70!black"]

    def test_deeply_nested_body_text(self) -> None:
        """Recurses through multiple nesting levels."""
        latex = r"\highLight[a]{\highLight[b]{\underLine[c]{deep}}}"
        nodes = parse_latex(latex)
        outer = find_macros(nodes, "highLight")
        # The outermost highLight's body text should reach "deep"
        assert get_body_text(outer[0]) == "deep"
