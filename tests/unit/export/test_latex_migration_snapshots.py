"""Snapshot tests for pre-migration LaTeX output (AC4.4 baseline).

These tests capture the exact current output of functions that will be
migrated to use latex_render utilities (latex_cmd, render_latex).  They
form the regression safety net: after migration, output must be
byte-identical.

Snapshots capture CURRENT behaviour, including any existing escaping
quirks.  AC4.4 requires output identity -- fixing escaping bugs is
out of scope for the migration.
"""

from __future__ import annotations

from promptgrimoire.export.latex_format import format_annot_latex
from promptgrimoire.export.preamble import generate_tag_colour_definitions


class TestGenerateTagColourDefinitionsSnapshot:
    """Snapshot of generate_tag_colour_definitions() output."""

    def test_three_tags_including_special_chars(self) -> None:
        """AC4.4 + AC4.5: output matches pre-migration baseline.

        Includes 'C#_notes' to verify tag names with LaTeX specials
        are handled identically after migration.
        """
        tag_colours = {
            "jurisdiction": "#1f77b4",
            "evidence": "#ff7f0e",
            "C#_notes": "#2ca02c",
        }
        result = generate_tag_colour_definitions(tag_colours)

        expected = (
            "\\definecolor{tag-jurisdiction}{HTML}{1f77b4}\n"
            "\\colorlet{tag-jurisdiction-light}{tag-jurisdiction!30}\n"
            "\\colorlet{tag-jurisdiction-dark}{tag-jurisdiction!70!black}\n"
            "\\definecolor{tag-evidence}{HTML}{ff7f0e}\n"
            "\\colorlet{tag-evidence-light}{tag-evidence!30}\n"
            "\\colorlet{tag-evidence-dark}{tag-evidence!70!black}\n"
            "\\definecolor{tag-C#-notes}{HTML}{2ca02c}\n"
            "\\colorlet{tag-C#-notes-light}{tag-C#-notes!30}\n"
            "\\colorlet{tag-C#-notes-dark}{tag-C#-notes!70!black}\n"
            "\\definecolor{many-dark}{HTML}{333333}"
        )
        assert result == expected


class TestFormatAnnotLatexSnapshot:
    """Snapshots of format_annot_latex() output."""

    def test_basic_with_comments(self) -> None:
        """AC4.4: annotation with author, timestamp, and comment.

        UUID suffixes in author names are stripped by _strip_test_uuid().
        """
        highlight = {
            "tag": "jurisdiction",
            "author": "Alice Jones ABC123",
            "created_at": "2026-01-15T10:30:00Z",
            "comments": [
                {
                    "author": "Bob Smith DEF456",
                    "text": "Important point about $damages",
                    "created_at": "2026-01-15T11:00:00Z",
                },
            ],
        }
        result = format_annot_latex(highlight)

        expected = (
            "\\annot{tag-jurisdiction}"
            "{\\textbf{Jurisdiction}"
            "\\par{\\scriptsize Alice Jones, 15 Jan 2026 10:30}"
            "\\par\\hrulefill"
            "\\par{\\scriptsize \\textbf{Bob Smith}, 15 Jan 2026 11:00:}"
            " Important point about \\$damages}"
        )
        assert result == expected

    def test_special_chars_in_author_and_comments(self) -> None:
        """AC4.4: LaTeX specials in author/comment text are escaped.

        Captures current escaping behaviour including the unescaped '#'
        in the colour name (pre-existing bug, not fixed in migration).
        """
        highlight = {
            "tag": "C#_notes",
            "author": "O'Brien & Associates",
            "comments": [
                {
                    "author": "Test",
                    "text": "See section 42 & compare with ~50%",
                },
            ],
        }
        result = format_annot_latex(highlight)

        expected = (
            "\\annot{tag-C#-notes}"
            "{\\textbf{C\\# Notes}"
            "\\par{\\scriptsize O'Brien \\& Associates}"
            "\\par\\hrulefill"
            "\\par{\\scriptsize \\textbf{Test:}}"
            " See section 42 \\& compare with \\textasciitilde{}50\\%}"
        )
        assert result == expected

    def test_with_paragraph_reference(self) -> None:
        """AC4.4: annotation with para_ref includes it after tag name."""
        highlight = {
            "tag": "evidence",
            "author": "Alice",
            "created_at": "2026-01-20T09:00:00Z",
            "comments": [],
        }
        result = format_annot_latex(highlight, para_ref="[45]")

        expected = (
            "\\annot{tag-evidence}"
            "{\\textbf{Evidence} [45]"
            "\\par{\\scriptsize Alice, 20 Jan 2026 09:00}}"
        )
        assert result == expected

    def test_no_timestamp_no_comments(self) -> None:
        """AC4.4: annotation without timestamp or comments."""
        highlight = {
            "tag": "jurisdiction",
            "author": "Alice",
            "comments": [],
        }
        result = format_annot_latex(highlight)

        expected = (
            "\\annot{tag-jurisdiction}{\\textbf{Jurisdiction}\\par{\\scriptsize Alice}}"
        )
        assert result == expected
