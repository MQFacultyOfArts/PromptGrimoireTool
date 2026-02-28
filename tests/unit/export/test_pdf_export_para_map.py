"""Tests for the string-to-int paragraph map key conversion at the PDF export boundary.

The WorkspaceDocument.paragraph_map stores keys as strings (PostgreSQL JSON
serialisation), while the export pipeline's ``word_to_legal_para`` expects
``dict[int, int | None]``.  The conversion happens at the call site in
``pages/annotation/pdf_export.py``.  These tests verify the pattern works
correctly for all edge cases.
"""

from __future__ import annotations


def _convert_paragraph_map(
    raw_map: dict[str, int] | None,
) -> dict[int, int | None] | None:
    """Replicate the conversion logic from pdf_export._handle_pdf_export().

    This is the exact pattern used at the call site:
        {int(k): v for k, v in doc_para_map.items()} if doc_para_map else None
    """
    return {int(k): v for k, v in raw_map.items()} if raw_map else None


class TestParagraphMapKeyConversion:
    """Verify string-to-int key conversion for the PDF export boundary."""

    def test_normal_conversion(self) -> None:
        """Standard map with string keys converts to int keys."""
        raw: dict[str, int] = {"0": 1, "50": 2, "120": 3}
        result = _convert_paragraph_map(raw)
        assert result == {0: 1, 50: 2, 120: 3}

    def test_empty_map_becomes_none(self) -> None:
        """Empty map converts to None (no paragraph numbering)."""
        result = _convert_paragraph_map({})
        assert result is None

    def test_none_input_stays_none(self) -> None:
        """None input stays None."""
        result = _convert_paragraph_map(None)
        assert result is None

    def test_all_output_keys_are_int(self) -> None:
        """Every key in the output must be an int, not a string."""
        raw: dict[str, int] = {"0": 1, "10": 2, "25": 3, "40": 4}
        result = _convert_paragraph_map(raw)
        assert result is not None
        for key in result:
            assert isinstance(key, int), f"Key {key!r} should be int, got {type(key)}"

    def test_all_output_values_are_int(self) -> None:
        """Every value in the output must be an int."""
        raw: dict[str, int] = {"0": 1, "50": 2, "120": 3}
        result = _convert_paragraph_map(raw)
        assert result is not None
        for val in result.values():
            assert isinstance(val, int), f"Value {val!r} should be int, got {type(val)}"

    def test_source_numbered_with_gaps(self) -> None:
        """Source-numbered map with non-sequential paragraph numbers."""
        raw: dict[str, int] = {"0": 1, "100": 5, "200": 12, "350": 13}
        result = _convert_paragraph_map(raw)
        assert result == {0: 1, 100: 5, 200: 12, 350: 13}

    def test_single_entry_map(self) -> None:
        """Single-paragraph document converts correctly."""
        raw: dict[str, int] = {"0": 1}
        result = _convert_paragraph_map(raw)
        assert result == {0: 1}
