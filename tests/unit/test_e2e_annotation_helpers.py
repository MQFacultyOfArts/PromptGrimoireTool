"""Unit tests for slow-mode export text normalization in E2E helpers."""

from __future__ import annotations

from tests.e2e.export_tools import ExportResult


def test_export_result_matches_wrapped_uuid_in_pdf_text() -> None:
    """Long tokens should survive PyMuPDF line breaks inside a single token."""
    uuid_text = "5d4db31a07ed4842a705df82b718c7b4"
    pdf_text = "comment: 5d4db31a07ed4842a705df82b718c\n7b4"

    result = ExportResult(pdf_text, is_pdf=True)

    assert uuid_text in result


def test_export_result_does_not_glue_short_tokens_across_whitespace() -> None:
    """Short tokens should keep normal word-boundary semantics."""
    result = ExportResult("a b", is_pdf=True)

    assert "ab" not in result


def test_export_result_does_not_glue_long_words_across_plain_spaces() -> None:
    """Fallback should only heal line wraps, not merge separate long words."""
    result = ExportResult("internationalization localization", is_pdf=True)

    assert "internationalizationlocalization" not in result
