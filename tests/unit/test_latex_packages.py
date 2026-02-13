"""Tests for LaTeX package availability."""

import shutil
import subprocess
from pathlib import Path

import pytest

from promptgrimoire.export.pdf import compile_latex
from promptgrimoire.export.pdf_export import _ensure_sty_in_dir
from promptgrimoire.export.preamble import build_annotation_preamble

# Required packages for unicode support (fonts come from system via fontspec)
UNICODE_PACKAGES = ["emoji", "luatexja"]

# Replacement character indicates missing glyph (tofu)
REPLACEMENT_CHAR = "\ufffd"

# Required system fonts for full Unicode support (from scripts/setup_latex.py)
REQUIRED_SYSTEM_FONTS = [
    # Main font (TNR equivalent)
    "TeX Gyre Termes",
    # CJK fonts (at least one variant needed)
    "Noto Serif CJK SC",
    "Noto Sans CJK SC",
    # Script-specific fonts for fallback chain
    "Noto Serif",
    "Noto Serif Hebrew",
    "Noto Naskh Arabic",
    "Noto Serif Devanagari",
    "Noto Serif Bengali",
    "Noto Serif Tamil",
    "Noto Serif Thai",
    # Historic/rare scripts (for BLNS coverage)
    "Noto Sans Deseret",
    "Noto Sans Osage",
    "Noto Sans Shavian",
    # Symbols and emoji
    "Noto Sans Symbols",
    "Noto Sans Symbols2",
    "Noto Color Emoji",
]


def get_fc_list_path() -> Path | None:
    """Get path to fc-list if installed."""
    path = shutil.which("fc-list")
    return Path(path) if path else None


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


@pytest.mark.order("first")
@pytest.mark.latex
class TestLaTeXPackages:
    """Test LaTeX package availability.

    These tests verify the LaTeX environment is correctly configured.
    They FAIL (not skip) when dependencies are missing - this is intentional.

    To exclude these tests (e.g., in CI without LaTeX):
        pytest -m "not latex"
    """

    def test_unicode_packages_installed(self) -> None:
        """Verify CJK and emoji packages are installed in TinyTeX."""
        tlmgr = get_tlmgr_path()
        assert tlmgr is not None, (
            "TinyTeX not installed. Run: uv run python scripts/setup_latex.py\n"
            "To skip LaTeX tests: pytest -m 'not latex'"
        )

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

    @pytest.mark.asyncio
    async def test_unicode_preamble_compiles_without_tofu(self, tmp_path: Path) -> None:
        """Verify production preamble (.sty) compiles and renders CJK without tofu."""
        pdftotext = get_pdftotext_path()
        assert pdftotext is not None, (
            "pdftotext not installed. Install poppler-utils:\n"
            "  Ubuntu/Debian: sudo apt install poppler-utils\n"
            "  Fedora: sudo dnf install poppler-utils\n"
            "  Arch: sudo pacman -S poppler\n"
            "To skip LaTeX tests: pytest -m 'not latex'"
        )

        # Test content - CJK text that must render correctly
        cjk_text = "日本語"

        # Copy .sty to tmp_path so latexmk can find it
        _ensure_sty_in_dir(tmp_path)

        # Build preamble via the production path (loads .sty + tag colours)
        preamble = build_annotation_preamble({})

        # Create minimal document using production preamble
        tex_content = (
            "\\documentclass{article}\n"
            f"{preamble}\n"
            "\\begin{document}\n"
            f"Hello World. CJK: \\cjktext{{{cjk_text}}} "
            "Emoji: \\emoji{party-popper}\n"
            "\\end{document}\n"
        )
        tex_file = tmp_path / "test_unicode.tex"
        tex_file.write_text(tex_content, encoding="utf-8")

        pdf_file = await compile_latex(tex_file, output_dir=tmp_path)
        assert pdf_file.exists(), "LuaLaTeX compilation failed"

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

    def test_system_fonts_installed(self) -> None:
        """Verify required system fonts are installed for Unicode rendering."""
        fc_list = get_fc_list_path()
        assert fc_list is not None, (
            "fc-list not installed (fontconfig). Install:\n"
            "  Ubuntu/Debian: sudo apt install fontconfig\n"
            "  Fedora: sudo dnf install fontconfig\n"
            "  Arch: sudo pacman -S fontconfig\n"
            "To skip LaTeX tests: pytest -m 'not latex'"
        )

        # Get list of installed font families
        result = subprocess.run(
            [str(fc_list), ":", "family"],
            capture_output=True,
            text=True,
            check=True,
        )
        installed = set(result.stdout.replace("\n", ",").split(","))
        installed = {f.strip() for f in installed if f.strip()}

        missing = []
        for font in REQUIRED_SYSTEM_FONTS:
            # Check if font family is installed (partial match for variants)
            if not any(font in f for f in installed):
                missing.append(font)

        assert not missing, (
            f"Missing system fonts for Unicode support: {missing}\n"
            "Install with:\n"
            "  Ubuntu/Debian: sudo apt install fonts-noto fonts-noto-cjk "
            "fonts-noto-cjk-extra fonts-noto-color-emoji tex-gyre\n"
            "  Fedora: sudo dnf install google-noto-fonts-all "
            "google-noto-emoji-fonts texlive-tex-gyre\n"
            "  Arch: sudo pacman -S noto-fonts noto-fonts-cjk "
            "noto-fonts-emoji noto-fonts-extra tex-gyre-fonts"
        )
