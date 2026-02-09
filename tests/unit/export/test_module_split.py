"""Validation tests for AC3: module split of latex.py.

Verifies that Phase 1 refactoring preserved public API while splitting
latex.py into preamble.py and pandoc.py along DFD process boundaries.

AC3.1: No single module exceeds ~400 lines (new modules); latex.py is
       smaller than its pre-split 1,708 lines.
AC3.2: Symbols land in the correct module per DFD alignment.
AC3.3: All public imports continue to resolve.
"""

from __future__ import annotations

from pathlib import Path

# ── AC3.1: Line count constraints ──────────────────────────────────────

EXPORT_DIR = Path(__file__).resolve().parents[3] / "src" / "promptgrimoire" / "export"

# Generous threshold — allows growth without false alarms
_NEW_MODULE_LINE_LIMIT = 450
# latex.py was 1,708 lines before the split
_ORIGINAL_LATEX_LINES = 1708


class TestAC3_1_LineCounts:
    """AC3.1: Each new module stays under ~400 lines; latex.py shrinks."""

    def test_preamble_under_limit(self) -> None:
        lines = (EXPORT_DIR / "preamble.py").read_text().splitlines()
        assert len(lines) < _NEW_MODULE_LINE_LIMIT, (
            f"preamble.py has {len(lines)} lines (limit {_NEW_MODULE_LINE_LIMIT})"
        )

    def test_pandoc_under_limit(self) -> None:
        lines = (EXPORT_DIR / "pandoc.py").read_text().splitlines()
        assert len(lines) < _NEW_MODULE_LINE_LIMIT, (
            f"pandoc.py has {len(lines)} lines (limit {_NEW_MODULE_LINE_LIMIT})"
        )

    def test_latex_still_exists(self) -> None:
        assert (EXPORT_DIR / "latex.py").exists(), (
            "latex.py should still exist (P2+P4 code remains)"
        )

    def test_latex_smaller_than_original(self) -> None:
        lines = (EXPORT_DIR / "latex.py").read_text().splitlines()
        assert len(lines) < _ORIGINAL_LATEX_LINES, (
            f"latex.py has {len(lines)} lines, "
            f"expected fewer than {_ORIGINAL_LATEX_LINES}"
        )


# ── AC3.2: Correct symbols in correct modules ─────────────────────────


class TestAC3_2_SymbolPlacement:
    """AC3.2: Module boundaries align with DFD processes."""

    def test_preamble_has_build_annotation_preamble(self) -> None:
        from promptgrimoire.export.preamble import build_annotation_preamble

        assert callable(build_annotation_preamble)

    def test_preamble_has_generate_tag_colour_definitions(self) -> None:
        from promptgrimoire.export.preamble import generate_tag_colour_definitions

        assert callable(generate_tag_colour_definitions)

    def test_pandoc_has_convert_html_to_latex(self) -> None:
        from promptgrimoire.export.pandoc import convert_html_to_latex

        assert callable(convert_html_to_latex)

    def test_pandoc_has_convert_html_with_annotations(self) -> None:
        from promptgrimoire.export.pandoc import convert_html_with_annotations

        assert callable(convert_html_with_annotations)


# ── AC3.3: Public API imports resolve ──────────────────────────────────


class TestAC3_3_PublicAPI:
    """AC3.3: All imports from pdf_export.py and annotation.py resolve."""

    def test_export_package_convert_html_to_latex(self) -> None:
        from promptgrimoire.export import convert_html_to_latex

        assert callable(convert_html_to_latex)

    def test_export_package_export_annotation_pdf(self) -> None:
        from promptgrimoire.export import export_annotation_pdf

        assert callable(export_annotation_pdf)

    def test_preamble_build_annotation_preamble(self) -> None:
        from promptgrimoire.export.preamble import build_annotation_preamble

        assert callable(build_annotation_preamble)

    def test_pandoc_convert_html_with_annotations(self) -> None:
        from promptgrimoire.export.pandoc import convert_html_with_annotations

        assert callable(convert_html_with_annotations)

    def test_pdf_export_export_annotation_pdf(self) -> None:
        from promptgrimoire.export.pdf_export import export_annotation_pdf

        assert callable(export_annotation_pdf)
