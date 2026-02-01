"""Tests for LaTeX package availability."""

import subprocess
from pathlib import Path

import pytest

# Required packages for unicode support
UNICODE_PACKAGES = ["emoji", "luatexja", "notocjksc"]


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
