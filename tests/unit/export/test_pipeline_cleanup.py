"""Validation tests for AC4 (deletion/cleanup) and AC5 (visual equivalence).

Asserts that the Process 4 code removal is complete and that the new pipeline
integration tests exist and resolve.

AC4.1: pylatexenc removed from main dependencies (kept in dev for test helpers).
AC4.2: latex.py deleted entirely.
AC4.3: All Process 4 test files deleted.
AC4.4: MarkerToken, MarkerTokenType, Region classes no longer importable.
AC4.5: lark removed from pyproject.toml dependencies.
AC4.6: _format_annot not importable from any promptgrimoire.export module.

AC5.1/AC5.2: Visual equivalence tests require PDF compilation and mutool
    analysis. These are verified during UAT, not in automated unit tests.
AC5.3: Integration test file exists and imports resolve.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import ClassVar

import pytest

# Resolve paths relative to this test file's location
_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXPORT_DIR = _REPO_ROOT / "src" / "promptgrimoire" / "export"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


# ── AC4.1: pylatexenc removed from main dependencies ─────────────────


class TestAC4_1_PylatexencRemoved:
    """AC4.1: pylatexenc is NOT in pyproject.toml main dependencies."""

    def test_pylatexenc_not_in_main_deps(self) -> None:
        """pylatexenc must not appear in [project] dependencies."""
        text = _PYPROJECT.read_text()
        # Extract the [project] dependencies section
        match = re.search(
            r"^dependencies\s*=\s*\[(.*?)\]",
            text,
            re.MULTILINE | re.DOTALL,
        )
        assert match is not None, "Could not find dependencies section"
        deps_section = match.group(1)
        assert "pylatexenc" not in deps_section, (
            "pylatexenc should be removed from main dependencies"
        )

    def test_pylatexenc_still_in_dev_deps(self) -> None:
        """pylatexenc must still be present in dev dependencies.

        It is used by tests/helpers/latex_parse.py for structural LaTeX
        assertions.
        """
        text = _PYPROJECT.read_text()
        # Extract the [dependency-groups] dev section.
        # Use \n] to match the closing bracket on its own line, since
        # entries like "psycopg[binary]" contain literal brackets.
        match = re.search(
            r"\[dependency-groups\].*?dev\s*=\s*\[(.*?)\n\]",
            text,
            re.DOTALL,
        )
        assert match is not None, "Could not find dev dependencies section"
        dev_section = match.group(1)
        assert "pylatexenc" in dev_section, (
            "pylatexenc should remain in dev dependencies for test helpers"
        )


# ── AC4.2: latex.py deleted ──────────────────────────────────────────


class TestAC4_2_LatexPyDeleted:
    """AC4.2: latex.py does not exist."""

    def test_latex_py_does_not_exist(self) -> None:
        """The file src/promptgrimoire/export/latex.py must not exist."""
        assert not (_EXPORT_DIR / "latex.py").exists(), (
            "latex.py should have been deleted"
        )


# ── AC4.3: Process 4 test files deleted ──────────────────────────────


class TestAC4_3_P4TestFilesDeleted:
    """AC4.3: All Process 4 test files are deleted."""

    _DELETED_FILES: ClassVar[list[str]] = [
        "tests/unit/export/test_region_builder.py",
        "tests/unit/export/test_latex_generator.py",
        "tests/unit/export/test_walk_and_wrap.py",
        "tests/unit/export/test_marker_lexer.py",
        "tests/unit/test_overlapping_highlights.py",
        "tests/unit/export/test_marker_insertion.py",
        "tests/unit/export/test_crlf_char_index_bug.py",
    ]

    @pytest.mark.parametrize("rel_path", _DELETED_FILES)
    def test_file_deleted(self, rel_path: str) -> None:
        """Each Process 4 test file must not exist."""
        full_path = _REPO_ROOT / rel_path
        assert not full_path.exists(), f"{rel_path} should have been deleted"


# ── AC4.4: P4 classes not importable ─────────────────────────────────


class TestAC4_4_P4ClassesRemoved:
    """AC4.4: MarkerToken, MarkerTokenType, Region are not importable."""

    @pytest.mark.parametrize("symbol", ["MarkerToken", "MarkerTokenType", "Region"])
    def test_symbol_not_importable_from_export(self, symbol: str) -> None:
        """P4 class must not be importable from promptgrimoire.export."""
        mod = importlib.import_module("promptgrimoire.export")
        assert not hasattr(mod, symbol), (
            f"{symbol} should not be accessible on promptgrimoire.export"
        )


# ── AC4.5: lark removed from dependencies ───────────────────────────


class TestAC4_5_LarkRemoved:
    """AC4.5: lark is NOT in pyproject.toml dependencies."""

    def test_lark_not_in_main_deps(self) -> None:
        """lark must not appear in [project] dependencies."""
        text = _PYPROJECT.read_text()
        match = re.search(
            r"^dependencies\s*=\s*\[(.*?)\]",
            text,
            re.MULTILINE | re.DOTALL,
        )
        assert match is not None, "Could not find dependencies section"
        deps_section = match.group(1)
        # Match "lark" as a dependency name (not substring of another name)
        assert not re.search(r'"lark[><=!]', deps_section), (
            "lark should be removed from main dependencies"
        )

    def test_lark_not_in_dev_deps(self) -> None:
        """lark must not appear in dev dependencies either."""
        text = _PYPROJECT.read_text()
        match = re.search(
            r"\[dependency-groups\].*?dev\s*=\s*\[(.*?)\n\]",
            text,
            re.DOTALL,
        )
        assert match is not None, "Could not find dev dependencies section"
        dev_section = match.group(1)
        assert not re.search(r'"lark[><=!]', dev_section), (
            "lark should not be in dev dependencies"
        )


# ── AC4.6: _format_annot not importable ─────────────────────────────


class TestAC4_6_FormatAnnotRemoved:
    """AC4.6: _format_annot is not importable from any export module."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "promptgrimoire.export",
            "promptgrimoire.export.preamble",
            "promptgrimoire.export.pandoc",
        ],
    )
    def test_format_annot_not_importable(self, module_path: str) -> None:
        """_format_annot must not be accessible on export modules."""
        mod = importlib.import_module(module_path)
        assert not hasattr(mod, "_format_annot"), (
            f"_format_annot should not be accessible on {module_path}"
        )

    def test_format_annot_latex_exists_in_highlight_spans(self) -> None:
        """The replacement function format_annot_latex must be importable."""
        mod = importlib.import_module("promptgrimoire.export.highlight_spans")
        assert hasattr(mod, "format_annot_latex")
        assert callable(mod.format_annot_latex)


# ── AC5.3: Integration tests exist and resolve ──────────────────────


class TestAC5_3_IntegrationTestsExist:
    """AC5.3: Integration test file exists and imports resolve."""

    def test_highlight_latex_elements_test_exists(self) -> None:
        """The integration test file must exist."""
        test_file = (
            _REPO_ROOT / "tests" / "integration" / "test_highlight_latex_elements.py"
        )
        assert test_file.exists(), (
            "tests/integration/test_highlight_latex_elements.py must exist"
        )

    def test_integration_test_imports_resolve(self) -> None:
        """The integration test module must be importable."""
        # This will raise if any imports inside the module fail
        mod = importlib.import_module("tests.integration.test_highlight_latex_elements")
        assert mod is not None


# ── AC5.1/AC5.2: Visual equivalence (UAT only) ─────────────────────
#
# AC5.1: The Lawlis v R fixture produces a PDF with identical highlight
#     rectangles (verified via mutool draw -F trace colour rectangle count).
# AC5.2: The E7 perverse overlap test case (4 overlapping highlights,
#     heading boundary) produces equivalent output through the new pipeline.
#
# These are visual/integration verification steps that require PDF compilation
# and mutool analysis. They should be verified during UAT, not in automated
# unit tests.
