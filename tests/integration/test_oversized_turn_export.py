"""Regression test: oversized speaker turns must not crash LaTeX compilation.

Reproduces the ``! Dimension too large`` error from mdframed when a single
``userturn`` environment exceeds TeX's ``\\maxdimen`` (~575cm rendered height).

Production trigger: workspace a91667f4 — student pasted a ~2,600-line style
guide as a single conversation turn. The mdframed ``framemethod=tikz`` path
measures the full box height before splitting, overflowing the dimension register.

This test belongs in the ``latexmk_full`` / ``e2e slow`` lane because it
requires real PDF compilation to exercise the TeX dimension limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from promptgrimoire.export.pdf_export import export_annotation_pdf
from tests.conftest import requires_full_latexmk

if TYPE_CHECKING:
    from pathlib import Path


def _build_oversized_turn_html(*, paragraph_count: int = 3000) -> str:
    """Build HTML with a single user turn containing many paragraphs.

    The content is structured as a realistic paste: a system message
    followed by a single enormous user turn.  Each paragraph is ~80 chars
    (one line of lorem-ish text) so 3,000 paragraphs ≈ 240K chars of
    rendered content — well above the ~575cm dimension limit.
    """
    filler = (
        "Esta es una oración de ejemplo que simula contenido extenso pegado "
        "por un estudiante en un solo turno de conversación."
    )
    body_paragraphs = "\n".join(
        f"<p>{filler} (§{i})</p>" for i in range(paragraph_count)
    )

    return f"""\
<div data-speaker="system"><p>You are a helpful assistant.</p></div>
<div data-speaker="user">
{body_paragraphs}
</div>
<div data-speaker="assistant"><p>Thank you for providing that content.</p></div>
"""


@requires_full_latexmk
class TestOversizedTurnExport:
    """PDF export must handle arbitrarily long speaker turns without crashing."""

    @pytest.mark.asyncio
    async def test_oversized_user_turn_compiles_to_pdf(self, tmp_path: Path) -> None:
        """A 3,000-paragraph user turn must compile without Dimension too large.

        This currently fails because mdframed's framemethod=tikz measures the
        full box height, which exceeds TeX's maxdimen for very tall content.

        AC1: export_annotation_pdf succeeds (no LaTeXCompilationError).
        AC2: Output PDF exists and is a valid PDF (starts with %PDF).
        AC3: PDF contains content from the oversized turn (spot-check §0 and §2999).
        """
        html = _build_oversized_turn_html(paragraph_count=3000)

        pdf_path = await export_annotation_pdf(
            html_content=html,
            highlights=[],
            tag_colours={},
            output_dir=tmp_path,
            filename="oversized_turn_test",
        )

        # AC1: No exception raised (implicit — we got here)

        # AC2: Valid PDF
        assert pdf_path.exists(), f"PDF not created at {pdf_path}"
        with pdf_path.open("rb") as f:
            header = f.read(4)
        assert header == b"%PDF", f"Not a valid PDF: starts with {header!r}"

        # AC3: Content spot-check
        import pymupdf

        doc = pymupdf.open(str(pdf_path))
        full_text = "\n".join(page.get_text() for page in doc)
        doc.close()

        assert "§0" in full_text, "First paragraph marker missing from PDF"
        assert "§2999" in full_text, "Last paragraph marker missing from PDF"
