"""Tests for LaTeX package availability."""

import shutil
import subprocess
from pathlib import Path

import pytest

# Required packages for unicode support (fonts come from system via fontspec)
UNICODE_PACKAGES = ["emoji", "luatexja"]

# Replacement character indicates missing glyph (tofu)
REPLACEMENT_CHAR = "\ufffd"


def get_pdftotext_path() -> Path | None:
    """Get path to pdftotext if installed."""
    path = shutil.which("pdftotext")
    return Path(path) if path else None


def get_tlmgr_path() -> Path | None:
    """Get path to tlmgr if TinyTeX is installed."""
    tinytex_bin = Path.home() / ".TinyTeX" / "bin"
    if not tinytex_bin.exists():
        return None
    # Find architecture-specific bin dir
    for arch_dir in tinytex_bin.iterdir():
        tlmgr = arch_dir / "tlmgr"
        if tlmgr.exists():
            return tlmgr
    return None


def get_lualatex_path() -> Path | None:
    """Get path to lualatex if TinyTeX is installed."""
    tinytex_bin = Path.home() / ".TinyTeX" / "bin"
    if not tinytex_bin.exists():
        return None
    for arch_dir in tinytex_bin.iterdir():
        lualatex = arch_dir / "lualatex"
        if lualatex.exists():
            return lualatex
    return None


@pytest.mark.slow
class TestLaTeXPackages:
    """Test LaTeX package availability."""

    def test_unicode_packages_installed(self) -> None:
        """Verify CJK and emoji packages are installed in TinyTeX."""
        tlmgr = get_tlmgr_path()
        if tlmgr is None:
            pytest.skip("TinyTeX not installed")

        result = subprocess.run(
            [str(tlmgr), "list", "--only-installed"],
            capture_output=True,
            text=True,
            check=True,
        )
        installed = result.stdout

        for package in UNICODE_PACKAGES:
            assert f"i {package}" in installed or package in installed, (
                f"Package {package} not installed. "
                "Run: uv run python scripts/setup_latex.py"
            )

    def test_unicode_preamble_compiles_without_tofu(self, tmp_path: Path) -> None:
        """Verify UNICODE_PREAMBLE compiles and renders CJK without tofu."""
        from promptgrimoire.export.unicode_latex import UNICODE_PREAMBLE

        lualatex = get_lualatex_path()
        if lualatex is None:
            pytest.skip("TinyTeX not installed")

        pdftotext = get_pdftotext_path()
        if pdftotext is None:
            pytest.skip("pdftotext not installed")

        # Test content - CJK text that must render correctly
        cjk_text = "日本語"

        # Create minimal document with UNICODE_PREAMBLE
        tex_content = rf"""\documentclass{{article}}
{UNICODE_PREAMBLE}
\begin{{document}}
Hello World. CJK: \cjktext{{{cjk_text}}} Emoji: \emoji{{party-popper}}
\end{{document}}
"""
        tex_file = tmp_path / "test_unicode.tex"
        tex_file.write_text(tex_content, encoding="utf-8")

        # Compile with LuaLaTeX (check=False because we verify via PDF existence)
        compile_result = subprocess.run(
            [str(lualatex), "-interaction=nonstopmode", str(tex_file)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            check=False,
        )

        pdf_file = tmp_path / "test_unicode.pdf"
        assert pdf_file.exists(), (
            f"LuaLaTeX compilation failed.\n"
            f"Return code: {compile_result.returncode}\n"
            f"Stdout: {compile_result.stdout[-2000:]}\n"
            f"Stderr: {compile_result.stderr[-500:]}"
        )

        # Extract text and check for tofu (missing glyphs)
        extract_result = subprocess.run(
            [str(pdftotext), str(pdf_file), "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        extracted = extract_result.stdout

        # No replacement characters = no tofu
        assert REPLACEMENT_CHAR not in extracted, (
            "Tofu detected in PDF output. "
            "Replacement character (U+FFFD) found in extracted text."
        )

        # CJK text should appear in extraction
        assert cjk_text in extracted, (
            f"CJK text '{cjk_text}' not found in extracted PDF text. "
            f"Extracted: {extracted[:500]}"
        )
