"""Tests to verify LaTeX environment is correctly configured.

These tests ensure TinyTeX packages and system fonts are installed,
preventing cryptic LaTeX errors at runtime.
"""

from __future__ import annotations

import subprocess

import pytest

# Import from setup script to stay in sync
from scripts.setup_latex import (
    LATEXMK,
    REQUIRED_PACKAGES,
    REQUIRED_SYSTEM_FONTS,
    TLMGR,
    is_tinytex_installed,
)

# Marker for tests requiring TinyTeX
requires_tinytex = pytest.mark.skipif(
    not is_tinytex_installed(),
    reason="TinyTeX not installed - run: uv run python scripts/setup_latex.py",
)


@pytest.mark.order("first")
class TestLaTeXEnvironment:
    """Verify LaTeX environment is correctly configured."""

    @requires_tinytex
    def test_tinytex_installed(self) -> None:
        """TinyTeX binaries exist at expected paths."""
        assert TLMGR.exists(), f"tlmgr not found at {TLMGR}"
        assert LATEXMK.exists(), f"latexmk not found at {LATEXMK}"

    @requires_tinytex
    def test_required_packages_installed(self) -> None:
        """All required LaTeX packages are installed in TinyTeX."""
        result = subprocess.run(
            [str(TLMGR), "list", "--only-installed"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.fail(f"tlmgr list failed: {result.stderr}")

        installed = result.stdout.lower()

        missing = []
        for package in REQUIRED_PACKAGES:
            # tlmgr output format: "i packagename: description"
            if f"i {package.lower()}:" not in installed:
                missing.append(package)

        if missing:
            pytest.fail(
                f"Missing LaTeX packages: {missing}\n"
                f"Run: uv run python scripts/setup_latex.py"
            )

    def test_system_fonts_installed(self) -> None:
        """Required system fonts are installed (via OS package manager)."""
        result = subprocess.run(
            ["fc-list", ":", "family"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("fc-list not available - cannot check system fonts")

        # Parse font families from fc-list output
        installed = set(result.stdout.replace("\n", ",").split(","))
        installed = {f.strip() for f in installed if f.strip()}

        missing = []
        for font in REQUIRED_SYSTEM_FONTS:
            # Partial match for font variants (e.g., "Noto Serif" matches
            # "Noto Serif,Noto Serif Light")
            if not any(font in f for f in installed):
                missing.append(font)

        if missing:
            pytest.fail(
                f"Missing system fonts: {missing}\n"
                f"Install with your package manager. See scripts/setup_latex.py "
                f"docstring for commands."
            )

    @requires_tinytex
    def test_latexmk_runs(self) -> None:
        """latexmk can be executed and reports version."""
        result = subprocess.run(
            [str(LATEXMK), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, f"latexmk failed: {result.stderr}"
        assert "Latexmk" in result.stdout, "Unexpected latexmk output"
