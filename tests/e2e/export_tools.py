"""PDF/LaTeX export helpers for annotation E2E tests.

Provides functions to trigger export downloads and extract text
from both .tex and compiled .pdf files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


def _normalise_pdf_text(s: str) -> str:
    """Normalise PDF-extracted text for fuzzy comparison.

    LuaLaTeX converts straight quotes to typographic quotes, and PyMuPDF
    inserts line breaks at PDF column boundaries.  Both transformations
    break naive ``in`` checks, so we normalise before comparing.
    """

    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s)


def _looks_like_wrappable_long_token(s: str) -> bool:
    """Return True for long single tokens that PDF extraction may wrap."""

    return len(s) >= 16 and re.fullmatch(r"[\w-]+", s) is not None


def _collapse_wrapped_long_token_breaks(s: str) -> str:
    """Remove PDF-inserted whitespace inside single word-like tokens."""

    return re.sub(r"(?<=[\w-])\s*[\r\n]+\s*(?=[\w-])", "", s)


class ExportResult:
    """Result of an annotation export -- adapts to .tex (fast) or .pdf (slow) mode.

    In fast mode (default ``e2e run``), ``compile_latex`` is monkey-patched
    to a no-op so the download is a ``.tex`` file.  In slow mode
    (``e2e slow``), compilation runs and the download is a real PDF.

    Attributes:
        text: Extracted text -- raw LaTeX source (.tex) or PyMuPDF-extracted
              plaintext (.pdf).
        is_pdf: ``True`` when the download was a compiled PDF.
        suggested_filename: The browser-suggested download filename from
            ``download.suggested_filename``.
    """

    def __init__(
        self,
        text: str,
        *,
        is_pdf: bool,
        size_bytes: int | None = None,
        suggested_filename: str = "",
    ) -> None:
        self.text = text
        self.is_pdf = is_pdf
        self.size_bytes = size_bytes
        self.suggested_filename = suggested_filename

    def __contains__(self, item: str) -> bool:
        if self.is_pdf:
            # LuaLaTeX converts straight quotes to typographic quotes and
            # PyMuPDF inserts line breaks; normalise both sides for comparison.
            needle = _normalise_pdf_text(item)
            haystack = _normalise_pdf_text(self.text)
            if needle in haystack:
                return True
            if _looks_like_wrappable_long_token(needle):
                return needle in _collapse_wrapped_long_token_breaks(self.text)
            return False
        return item in self.text


def export_pdf_text(page: Page) -> str:
    """Click Export PDF, download, extract text via pymupdf.

    Args:
        page: Playwright page with annotation workspace loaded.

    Returns:
        Extracted text from the PDF with soft-hyphen breaks removed.

    Raises:
        pytest.skip: If export times out (TinyTeX not installed).
    """
    import pytest
    from playwright.sync_api import (
        TimeoutError as PlaywrightTimeoutError,
    )

    try:
        with page.expect_download(timeout=120000) as dl:
            page.get_by_test_id("export-pdf-btn").click()

        download = dl.value
        pdf_path = download.path()
        pdf_bytes = Path(pdf_path).read_bytes()
        assert len(pdf_bytes) > 5_000, f"PDF too small: {len(pdf_bytes)} bytes"

        import pymupdf

        doc = pymupdf.open(pdf_path)
        pdf_text = "".join(p.get_text() for p in doc)
        doc.close()

        return re.sub(r"-\n", "", pdf_text)
    except PlaywrightTimeoutError:
        pytest.skip("PDF export timed out (TinyTeX not installed?)")


def export_annotation_tex_text(page: Page) -> ExportResult:
    """Click Export PDF and return the downloaded content.

    Detects whether the download is a ``.tex`` file (fast mode) or a
    compiled PDF (slow mode) and returns an :class:`ExportResult` with
    the appropriate text extraction.

    The result supports ``in`` checks (``"word" in result``) so most
    existing assertions work unchanged.

    Args:
        page: Playwright page with an annotation workspace loaded.

    Returns:
        :class:`ExportResult` with extracted text, format flag, and
        the browser-suggested download filename.
    """
    with page.expect_download(timeout=120000) as dl:
        page.get_by_test_id("export-pdf-btn").click()

    download = dl.value
    suggested = download.suggested_filename
    file_path = download.path()
    raw = Path(file_path).read_bytes()

    if raw[:4] == b"%PDF":
        import pymupdf

        doc = pymupdf.open(file_path)
        pdf_text = "".join(p.get_text() for p in doc)
        doc.close()
        return ExportResult(
            re.sub(r"-\n", "", pdf_text),
            is_pdf=True,
            size_bytes=len(raw),
            suggested_filename=suggested,
        )

    return ExportResult(
        raw.decode("utf-8"),
        is_pdf=False,
        size_bytes=len(raw),
        suggested_filename=suggested,
    )
