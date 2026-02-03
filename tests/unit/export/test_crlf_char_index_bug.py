"""Test for CRLF/whitespace character index mismatch between UI and PDF export.

Issue #111: PDF export highlights appear at incorrect positions toward end of
long documents because UI and PDF count whitespace-only lines differently.

Root cause:
- UI (_process_text_to_char_spans): `if line:` - indexes whitespace-only lines
- PDF (_plain_text_to_html): `if line.strip():` - treats whitespace-only as empty

This causes cumulative drift in character indices for documents with:
- CRLF line endings (the \r at end of lines is indexed by UI but not PDF)
- Whitespace-only lines
"""

from __future__ import annotations

from promptgrimoire.export.latex import _insert_markers_into_html
from promptgrimoire.export.pdf_export import _plain_text_to_html
from promptgrimoire.pages.annotation import _process_text_to_char_spans


class TestCharIndexAlignment:
    """Verify UI and PDF character indexing match."""

    def _count_pdf_chars(self, text: str) -> int:
        """Count characters as PDF marker insertion does."""
        # Convert text to HTML (same as PDF export path)
        html_str = _plain_text_to_html(text)

        # Count chars like _insert_markers_into_html does
        char_count = 0
        i = 0
        while i < len(html_str):
            if html_str[i] == "<":
                tag_end = html_str.find(">", i)
                if tag_end == -1:
                    break
                i = tag_end + 1
            else:
                next_tag = html_str.find("<", i)
                if next_tag == -1:
                    next_tag = len(html_str)
                chunk = html_str[i:next_tag]
                for char in chunk:
                    if char != "\n":  # Skip newlines (same as marker insertion)
                        char_count += 1
                i = next_tag
        return char_count

    def _count_ui_chars(self, text: str) -> int:
        """Count characters as UI does."""
        _, chars = _process_text_to_char_spans(text)
        return len(chars)

    def test_lf_line_endings_match(self) -> None:
        """LF-only line endings should produce matching char counts."""
        text = "Line one\nLine two\nLine three"
        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        assert ui_count == pdf_count, f"UI={ui_count}, PDF={pdf_count}"

    def test_crlf_line_endings_match(self) -> None:
        """CRLF line endings should produce matching char counts.

        This is the key bug: \r from CRLF is indexed by UI but not by PDF
        because PDF's _plain_text_to_html uses `if line.strip():` which
        doesn't include whitespace-only content.
        """
        text = "Line one\r\nLine two\r\nLine three"
        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        assert ui_count == pdf_count, f"UI={ui_count}, PDF={pdf_count}"

    def test_whitespace_only_lines_match(self) -> None:
        """Lines with only whitespace should produce matching char counts."""
        text = "Before\n   \nAfter"  # Middle line has 3 spaces
        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        assert ui_count == pdf_count, f"UI={ui_count}, PDF={pdf_count}"

    def test_trailing_cr_lines_match(self) -> None:
        """Lines ending with \r (from CRLF split) should match."""
        # After split("\n"), CRLF leaves \r at end of each line
        text = "Line\r\nAnother\r\n"
        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        assert ui_count == pdf_count, f"UI={ui_count}, PDF={pdf_count}"

    def test_crlf_blank_lines_match(self) -> None:
        """Blank lines in CRLF documents should produce matching char counts.

        This is THE bug: CRLF blank lines become just '\r' after split("\n").
        - UI: '\r' is truthy, so it gets indexed
        - PDF: '\r'.strip() is empty, so <p></p> with no content

        Documents with many paragraph breaks (blank lines) accumulate this drift.
        """
        text = "Line1\r\n\r\nLine2"  # CRLF with blank line in middle
        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        assert ui_count == pdf_count, f"UI={ui_count}, PDF={pdf_count}"

    def test_many_crlf_blank_lines_cumulative_drift(self) -> None:
        """Many blank lines in CRLF document should not cause cumulative drift.

        Each blank line in CRLF causes 1 char drift. A document with 50 blank
        lines would have highlights off by 50 chars at the end.
        """
        # Simulate a document with 50 paragraph breaks (blank lines)
        paragraphs = [f"Paragraph {i}" for i in range(50)]
        text = "\r\n\r\n".join(paragraphs)  # Double CRLF between paragraphs

        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        drift = abs(ui_count - pdf_count)
        assert drift == 0, f"UI={ui_count}, PDF={pdf_count}, drift={drift} chars"

    def test_mixed_crlf_and_lf(self) -> None:
        """Documents with mixed line endings should match."""
        text = "Line1\r\nLine2\nLine3\r\nLine4"
        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        assert ui_count == pdf_count, f"UI={ui_count}, PDF={pdf_count}"

    def test_trailing_blank_lines(self) -> None:
        """Trailing blank lines should match."""
        text = "Content\r\n\r\n\r\n"  # Content followed by blank lines
        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        assert ui_count == pdf_count, f"UI={ui_count}, PDF={pdf_count}"

    def test_leading_blank_lines(self) -> None:
        """Leading blank lines should match."""
        text = "\r\n\r\nContent"  # Blank lines before content
        ui_count = self._count_ui_chars(text)
        pdf_count = self._count_pdf_chars(text)
        assert ui_count == pdf_count, f"UI={ui_count}, PDF={pdf_count}"

    def test_highlight_position_at_end_of_crlf_document(self) -> None:
        """Highlight at end of CRLF document should be at correct position.

        This tests the actual scenario from Issue #111: a highlight at the
        end of a long document with CRLF line endings appears at wrong position.
        """
        # Simulate a document with many CRLF lines
        lines = [f"Line {i}" for i in range(100)]
        text = "\r\n".join(lines)

        # UI character count for the last word "99"
        _, ui_chars = _process_text_to_char_spans(text)
        # Find where "99" starts - it's at the end
        last_line_start = len(ui_chars) - len("Line 99")
        highlight_start = last_line_start + 5  # "Line " is 5 chars, "99" starts at +5

        # Create highlight at that position
        highlights = [
            {
                "start_char": highlight_start,
                "end_char": highlight_start + 2,
                "tag": "test",
            }
        ]

        # Convert to HTML the same way PDF export does
        html_content = _plain_text_to_html(text)

        # Insert markers
        result, _markers = _insert_markers_into_html(html_content, highlights)

        # The marker should be around "99", not shifted earlier
        # If indices don't match, the marker will be in wrong position
        assert "HLSTART0ENDHL9" in result, (
            f"Highlight marker not at expected position. "
            f"UI counted {len(ui_chars)} chars, highlight at {highlight_start}"
        )
