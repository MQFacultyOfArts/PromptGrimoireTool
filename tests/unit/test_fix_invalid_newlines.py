"""Tests for _fix_invalid_newlines() — Issue #462.

The LaTeX error 'There's no line here to end' occurs when \\newline{}
appears at the start of a table cell with no preceding text. The Lua
filter converts <br> tags to \\newline{}, but when a cell *starts* with
a <br>, the \\newline{} has no line to end.
"""

from promptgrimoire.export.pandoc import _fix_invalid_newlines


class TestLeadingNewlineInCell:
    """Issue #462: \\newline{} at the start of a table cell."""

    def test_newline_after_column_separator(self):
        """A \\newline{} right after & should be stripped."""
        latex = r"First cell & \newline{}Second cell \\"
        result = _fix_invalid_newlines(latex)
        assert r"\newline{}" not in result
        assert "Second cell" in result

    def test_newline_at_start_of_first_cell_in_row(self):
        """A \\newline{} at the very start of a row (first cell) should be stripped."""
        latex = (
            r"\begin{longtable}{@{}p{0.50\textwidth}p{0.50\textwidth}@{}}"
            "\n"
            r"\newline{}Content & Other \\"
            "\n"
            r"\end{longtable}"
        )
        result = _fix_invalid_newlines(latex)
        # Should not start with \newline{} inside the table
        assert r"\newline{}Content" not in result
        assert "Content" in result

    def test_newline_after_separator_with_whitespace(self):
        """Whitespace between & and \\newline{} should also be handled."""
        latex = r"First & " + "\n" + r"\newline{}Second \\"
        result = _fix_invalid_newlines(latex)
        assert r"\newline{}" not in result
        assert "Second" in result

    def test_preserves_valid_mid_cell_newline(self):
        """A \\newline{} between text in a cell must be preserved."""
        latex = r"Line one\newline{}Line two & Other \\"
        result = _fix_invalid_newlines(latex)
        assert r"\newline{}" in result

    def test_multiple_cells_with_leading_newlines(self):
        """Multiple cells in a row can each have leading \\newline{}."""
        latex = r"\newline{}A & \newline{}B & \newline{}C \\"
        result = _fix_invalid_newlines(latex)
        assert result.count(r"\newline{}") == 0
        assert "A" in result
        assert "B" in result
        assert "C" in result

    def test_issue_462_actual_pandoc_output(self):
        r"""Exact Pandoc output pattern from workspace 11c93033."""
        latex = (
            "\\begingroup\\small\n"
            "\\begin{longtable}{@{}p{0.78\\textwidth}p{0.09\\textwidth}@{}}\n"
            "\\toprule\n"
            "\\newline{}\n"
            "(MtCO2eq)91 &  \\\\\n"
            "\\midrule\n"
            "\\endhead\n"
            "A & B \\\\\n"
            "\\bottomrule\n"
            "\\end{longtable}\n"
            "\\endgroup"
        )
        result = _fix_invalid_newlines(latex)
        assert r"\newline{}" not in result
        assert "(MtCO2eq)91" in result


class TestExistingBehaviourPreserved:
    """Regression tests for already-handled patterns."""

    def test_consecutive_newlines_removed(self):
        latex = r"text\newline{}\newline{}more"
        result = _fix_invalid_newlines(latex)
        assert r"\newline{}\newline{}" not in result

    def test_newline_before_separator_removed(self):
        latex = r"text\newline{} & other \\"
        result = _fix_invalid_newlines(latex)
        assert r"\newline{} &" not in result
        assert "text" in result

    def test_newline_after_row_end_removed(self):
        latex = r"\\ \newline{}"
        result = _fix_invalid_newlines(latex)
        assert r"\newline{}" not in result
