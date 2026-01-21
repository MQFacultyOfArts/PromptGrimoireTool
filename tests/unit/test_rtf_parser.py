"""Tests for RTF parser."""

from pathlib import Path

import pytest

from promptgrimoire.models import ParsedRTF
from promptgrimoire.parsers.rtf import _MAX_FILE_SIZE, parse_rtf


@pytest.fixture
def lawlis_rtf_path() -> Path:
    """Path to the Lawlis v R test fixture."""
    return Path(__file__).parent.parent / "fixtures" / "183.rtf"


class TestParseRTF:
    """Tests for parse_rtf function."""

    def test_returns_parsed_rtf(self, lawlis_rtf_path: Path) -> None:
        """Parser returns a ParsedRTF dataclass."""
        result = parse_rtf(lawlis_rtf_path)

        assert isinstance(result, ParsedRTF)

    def test_preserves_original_blob(self, lawlis_rtf_path: Path) -> None:
        """Original RTF content is stored as bytes."""
        result = parse_rtf(lawlis_rtf_path)

        assert isinstance(result.original_blob, bytes)
        assert result.original_blob.lstrip().startswith(b"{\\rtf")

    def test_generates_html(self, lawlis_rtf_path: Path) -> None:
        """HTML output is generated for rendering."""
        result = parse_rtf(lawlis_rtf_path)

        assert isinstance(result.html, str)
        # LibreOffice uses <p class="western"> style
        assert "<table" in result.html or "<p " in result.html

    def test_html_contains_case_name(self, lawlis_rtf_path: Path) -> None:
        """Case name appears in HTML output."""
        result = parse_rtf(lawlis_rtf_path)

        assert "Lawlis" in result.html
        assert "v" in result.html
        assert "R" in result.html

    def test_html_preserves_emphasis(self, lawlis_rtf_path: Path) -> None:
        """HTML preserves italic/emphasis formatting."""
        result = parse_rtf(lawlis_rtf_path)

        # LibreOffice uses <i> tags for italics
        assert "<em>" in result.html or "<i>" in result.html

    def test_generates_plain_text(self, lawlis_rtf_path: Path) -> None:
        """Plain text output is generated for search."""
        result = parse_rtf(lawlis_rtf_path)

        assert isinstance(result.plain_text, str)
        assert len(result.plain_text) > 0

    def test_plain_text_contains_case_name(self, lawlis_rtf_path: Path) -> None:
        """Case name appears in plain text output."""
        result = parse_rtf(lawlis_rtf_path)

        assert "Lawlis v R" in result.plain_text

    def test_plain_text_has_paragraph_numbers(self, lawlis_rtf_path: Path) -> None:
        """Paragraph numbers are preserved in plain text."""
        result = parse_rtf(lawlis_rtf_path)

        # NSW judgments use "1." style numbering
        assert "1." in result.plain_text
        assert "2." in result.plain_text

    def test_stores_source_filename(self, lawlis_rtf_path: Path) -> None:
        """Source filename is preserved."""
        result = parse_rtf(lawlis_rtf_path)

        assert result.source_filename == "183.rtf"

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="RTF file not found"):
            parse_rtf(tmp_path / "nonexistent.rtf")

    def test_invalid_rtf_raises(self, tmp_path: Path) -> None:
        """Non-RTF file raises ValueError."""
        bad_file = tmp_path / "bad.rtf"
        bad_file.write_text("This is not RTF content")

        with pytest.raises(ValueError, match="valid RTF"):
            parse_rtf(bad_file)

    def test_oversized_file_raises(self, tmp_path: Path) -> None:
        """File exceeding size limit raises ValueError."""
        large_file = tmp_path / "large.rtf"
        # Create content just over the limit
        large_file.write_bytes(b"{\\rtf1" + b"x" * _MAX_FILE_SIZE)

        with pytest.raises(ValueError, match="10MB limit"):
            parse_rtf(large_file)
