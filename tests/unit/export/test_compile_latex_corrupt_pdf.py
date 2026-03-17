"""Tests for compile_latex rejection of corrupt PDFs.

When latexmk exits with a non-zero returncode but leaves a non-empty PDF
from a prior pass, compile_latex must raise LaTeXCompilationError rather
than returning the corrupt file.

Regression test for issue #372.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from promptgrimoire.export.pdf import (
    LaTeXCompilationError,
    compile_latex,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def _fake_latexmk_fails_with_pdf(tmp_path: Path) -> Path:
    """Create a fake latexmk that exits non-zero but leaves a non-empty PDF.

    Simulates the real failure mode: first lualatex pass creates a PDF,
    second pass hits a fatal error (e.g. \\label with \\textquotesingle),
    latexmk exits 12 but the PDF from pass 1 still exists on disk.
    """
    script = tmp_path / "fake_latexmk.sh"
    script.write_text(
        textwrap.dedent("""\
        #!/bin/bash
        # Parse output directory from latexmk args
        for arg in "$@"; do
            case "$arg" in
                -output-directory=*) outdir="${arg#-output-directory=}" ;;
                *.tex) texfile="$arg" ;;
            esac
        done
        stem=$(basename "$texfile" .tex)
        # Create a non-empty PDF (corrupt — from a partial first pass)
        echo "%PDF-1.4 corrupt partial output" > "$outdir/$stem.pdf"
        # Create a log file with fatal error
        cat > "$outdir/$stem.log" << 'LOGEOF'
        ! Missing \\endcsname inserted.
        l.1094 ...S À L\\textquotesingle ABRI MAINTENANT}}
        !  ==> Fatal error occurred, no output PDF file produced!
        LOGEOF
        # Exit non-zero like real latexmk does on fatal error
        exit 12
        """)
    )
    script.chmod(0o755)
    return script


@pytest.mark.asyncio
async def test_nonzero_exit_with_nonempty_pdf_raises(
    tmp_path: Path,
    _fake_latexmk_fails_with_pdf: Path,
) -> None:
    """compile_latex must reject a non-empty PDF when returncode is non-zero.

    This is the actual failure mode from production: latexmk exits 12
    (fatal error) but a PDF from a prior pass still exists on disk.
    The current code only checks existence + size, so the corrupt PDF
    passes through as "success".
    """
    tex_path = tmp_path / "test.tex"
    tex_path.write_text(r"\documentclass{article}\begin{document}x\end{document}")

    with (
        patch(
            "promptgrimoire.export.pdf.get_latexmk_path",
            return_value=str(_fake_latexmk_fails_with_pdf),
        ),
        pytest.raises(LaTeXCompilationError, match="exit 12"),
    ):
        await compile_latex(tex_path, output_dir=tmp_path)


@pytest.mark.asyncio
async def test_zero_exit_with_valid_pdf_succeeds(tmp_path: Path) -> None:
    """compile_latex returns the PDF path when returncode is 0 and PDF exists."""
    script = tmp_path / "fake_latexmk_ok.sh"
    script.write_text(
        textwrap.dedent("""\
        #!/bin/bash
        for arg in "$@"; do
            case "$arg" in
                -output-directory=*) outdir="${arg#-output-directory=}" ;;
                *.tex) texfile="$arg" ;;
            esac
        done
        stem=$(basename "$texfile" .tex)
        echo "%PDF-1.4 valid output" > "$outdir/$stem.pdf"
        touch "$outdir/$stem.log"
        exit 0
        """)
    )
    script.chmod(0o755)

    tex_path = tmp_path / "test.tex"
    tex_path.write_text(r"\documentclass{article}\begin{document}x\end{document}")

    with patch(
        "promptgrimoire.export.pdf.get_latexmk_path",
        return_value=str(script),
    ):
        result = await compile_latex(tex_path, output_dir=tmp_path)

    assert result.exists()
    assert result.name == "test.pdf"
