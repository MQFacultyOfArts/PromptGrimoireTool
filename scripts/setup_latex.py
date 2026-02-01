#!/usr/bin/env python3
"""Setup TinyTeX for PDF export.

Installs TinyTeX and required LaTeX packages for the annotation PDF export feature.
Run with: uv run python scripts/setup_latex.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# TinyTeX installation paths
TINYTEX_DIR = Path.home() / ".TinyTeX"
TINYTEX_BIN = TINYTEX_DIR / "bin" / "x86_64-linux"
TLMGR = TINYTEX_BIN / "tlmgr"
LATEXMK = TINYTEX_BIN / "latexmk"

# Packages required for PDF export
REQUIRED_PACKAGES = [
    "lua-ul",  # Highlighting with LuaLaTeX
    "fontspec",  # System font support
    "luacolor",  # Color support for LuaLaTeX
    "todonotes",  # Margin notes (used in tests)
    "geometry",  # Page layout
    "marginalia",  # Auto-stacking margin notes (LuaLaTeX)
    "latexmk",  # Build automation
    "xcolor",  # Color support
    "soul",  # Underlining/highlighting (fallback)
    # Unicode support (Issue #101)
    "emoji",  # Emoji rendering in LuaLaTeX
    "luatexja",  # CJK support for LuaLaTeX
    "haranoaji",  # Default Japanese fonts for luatexja-fontspec
    "gentium-sil",  # Wide Unicode coverage fallback font
]


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    print(f"  Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def is_tinytex_installed() -> bool:
    """Check if TinyTeX is installed."""
    return TLMGR.exists() and LATEXMK.exists()


def install_tinytex() -> None:
    """Download and install TinyTeX."""
    print("Installing TinyTeX...")

    # Download installer
    installer_url = "https://yihui.org/tinytex/install-bin-unix.sh"
    result = run_cmd(["curl", "-sL", installer_url], check=True)

    # Run installer
    process = subprocess.run(
        ["sh"],
        input=result.stdout,
        capture_output=True,
        text=True,
        check=False,
    )

    if process.returncode != 0:
        print(f"TinyTeX installation failed:\n{process.stderr}")
        sys.exit(1)

    print("TinyTeX installed successfully.")


def install_packages() -> None:
    """Install required LaTeX packages via tlmgr."""
    print("Installing required LaTeX packages...")

    for package in REQUIRED_PACKAGES:
        print(f"  Installing {package}...")
        result = run_cmd([str(TLMGR), "install", package], check=False)
        if result.returncode != 0:
            # Package might already be installed or not available
            if "already installed" in result.stdout.lower():
                print(f"    {package} already installed")
            else:
                print(f"    Warning: {package} installation returned: {result.stderr}")


def verify_installation() -> bool:
    """Verify TinyTeX installation works."""
    print("Verifying installation...")

    # Check latexmk version
    result = run_cmd([str(LATEXMK), "--version"], check=False)
    if result.returncode != 0:
        print(f"latexmk verification failed: {result.stderr}")
        return False

    print(f"  latexmk: {result.stdout.splitlines()[0]}")
    return True


def main() -> int:
    """Main entry point."""
    print("TinyTeX Setup for PromptGrimoire PDF Export")
    print("=" * 50)

    if is_tinytex_installed():
        print(f"TinyTeX already installed at {TINYTEX_DIR}")
    else:
        install_tinytex()

        if not is_tinytex_installed():
            print("ERROR: TinyTeX installation failed - binaries not found")
            return 1

    install_packages()

    if not verify_installation():
        return 1

    print()
    print("Setup complete!")
    print(f"latexmk path: {LATEXMK}")
    print()
    print("Note: First compilation with CJK fonts may use ~6GB RAM")
    print("for font cache generation. Subsequent compilations are faster.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
