"""Tests for RTF parser."""

from pathlib import Path

import pytest

from promptgrimoire.models import ParsedRTF
from promptgrimoire.parsers.rtf import _MAX_FILE_SIZE, parse_rtf

# Run all RTF tests on same worker to share LibreOffice process
pytestmark = pytest.mark.xdist_group("rtf_parser")


@pytest.fixture
def lawlis_rtf_path() -> Path:
    """Path to the Lawlis v R test fixture."""
    return Path(__file__).parent.parent / "fixtures" / "183.rtf"


@pytest.fixture(scope="module")
def parsed_lawlis() -> ParsedRTF:
    """Parse RTF once, reuse across all tests in module.

    This saves ~13s by avoiding repeated LibreOffice spawns.
    """
    path = Path(__file__).parent.parent / "fixtures" / "183.rtf"
    return parse_rtf(path)


class TestParseRTF:
    """Tests for parse_rtf function."""

    def test_returns_parsed_rtf(self, parsed_lawlis: ParsedRTF) -> None:
        """Parser returns a ParsedRTF dataclass."""
        assert isinstance(parsed_lawlis, ParsedRTF)

    def test_preserves_original_blob(self, parsed_lawlis: ParsedRTF) -> None:
        """Original RTF content is stored as bytes."""
        assert isinstance(parsed_lawlis.original_blob, bytes)
        assert parsed_lawlis.original_blob.lstrip().startswith(b"{\\rtf")

    def test_generates_html(self, parsed_lawlis: ParsedRTF) -> None:
        """HTML output is generated for rendering."""
        assert isinstance(parsed_lawlis.html, str)
        # LibreOffice uses <p class="western"> style
        assert "<table" in parsed_lawlis.html or "<p " in parsed_lawlis.html

    def test_html_contains_case_name(self, parsed_lawlis: ParsedRTF) -> None:
        """Case name appears in HTML output."""
        assert "Lawlis" in parsed_lawlis.html
        assert "v" in parsed_lawlis.html
        assert "R" in parsed_lawlis.html

    def test_html_preserves_emphasis(self, parsed_lawlis: ParsedRTF) -> None:
        """HTML preserves italic/emphasis formatting."""
        # LibreOffice uses <i> tags for italics
        assert "<em>" in parsed_lawlis.html or "<i>" in parsed_lawlis.html

    def test_stores_source_filename(self, parsed_lawlis: ParsedRTF) -> None:
        """Source filename is preserved."""
        assert parsed_lawlis.source_filename == "183.rtf"

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
