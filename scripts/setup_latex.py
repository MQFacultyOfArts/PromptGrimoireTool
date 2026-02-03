#!/usr/bin/env python3
"""Setup TinyTeX for PDF export.

Installs TinyTeX and required LaTeX packages for the annotation PDF export feature.
Run with: uv run python scripts/setup_latex.py

System font requirements (install via OS package manager):
- Noto Serif CJK SC (and other CJK variants)
- Noto Serif (Hebrew, Devanagari, Bengali, Tamil, Thai, Georgian, Armenian, etc.)
- Noto Sans Symbols, Noto Sans Symbols2, Noto Sans Math
- Noto Color Emoji

Ubuntu/Debian:
    sudo apt install fonts-noto fonts-noto-cjk fonts-noto-cjk-extra \\
        fonts-noto-color-emoji tex-gyre

Fedora:
    sudo dnf install google-noto-fonts-all google-noto-emoji-fonts texlive-tex-gyre

Arch:
    sudo pacman -S noto-fonts noto-fonts-cjk noto-fonts-emoji \\
        noto-fonts-extra tex-gyre-fonts
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

# TinyTeX installation paths
TINYTEX_DIR = Path.home() / ".TinyTeX"
TINYTEX_BIN = TINYTEX_DIR / "bin" / "x86_64-linux"
TLMGR = TINYTEX_BIN / "tlmgr"
LATEXMK = TINYTEX_BIN / "latexmk"
LUALATEX = TINYTEX_BIN / "lualatex"

# Packages required for PDF export (from TeX Live)
REQUIRED_PACKAGES = [
    # Core rendering
    "lua-ul",  # Highlighting with LuaLaTeX
    "fontspec",  # System font support
    "luacolor",  # Color support for LuaLaTeX
    "xcolor",  # Color support
    "soul",  # Underlining/highlighting (fallback)
    # Page layout
    "geometry",  # Page layout
    "marginalia",  # Auto-stacking margin notes (LuaLaTeX)
    "todonotes",  # Margin notes (used in tests)
    # Build tools
    "latexmk",  # Build automation
    # Bidirectional text
    "luabidi",  # Bidirectional text for LuaLaTeX (for dir="ltr" HTML elements)
    # Code blocks
    "fancyvrb",  # Verbatim/code blocks from Pandoc syntax highlighting
    # Speaker turns
    "mdframed",  # Framed environments for speaker turns with left border
    "zref",  # Reference system (mdframed dependency)
    "needspace",  # Space checking (mdframed dependency)
    # Unicode/CJK support (Issue #101)
    "emoji",  # Emoji rendering in LuaLaTeX
    "luatexja",  # CJK support for LuaLaTeX
    "haranoaji",  # Default Japanese fonts for luatexja-fontspec
]

# Required system fonts (installed via OS, not TinyTeX)
# These are accessed via fontspec/luatexja-fontspec
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
    # Symbols and emoji
    "Noto Sans Symbols",
    "Noto Sans Symbols2",
    "Noto Color Emoji",
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


def check_system_fonts() -> list[str]:
    """Check for required system fonts using fc-list.

    Returns list of missing font families.
    """
    print("Checking system fonts...")

    # Get list of installed fonts
    result = subprocess.run(
        ["fc-list", ":", "family"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print("  Warning: fc-list not available, skipping font check")
        return []

    installed = set(result.stdout.replace("\n", ",").split(","))
    installed = {f.strip() for f in installed if f.strip()}

    missing = []
    for font in REQUIRED_SYSTEM_FONTS:
        # Check if font family is installed (partial match for variants)
        if not any(font in f for f in installed):
            missing.append(font)
        else:
            print(f"  ✓ {font}")

    return missing


def warm_font_cache() -> bool:
    """Warm LuaLaTeX font cache by compiling a minimal document.

    First compilation with CJK fonts can use ~6GB RAM for font cache generation.
    This function triggers that cache generation so subsequent compilations are fast.

    Returns True if cache warming succeeded, False otherwise.
    """
    print("Warming font cache (this may take a while on first run)...")

    # Minimal document that triggers font cache for CJK and extended Unicode
    test_doc = r"""\documentclass{article}
\usepackage{fontspec}
\usepackage{luatexja-fontspec}
\setmainfont{TeX Gyre Termes}
\setmonofont{DejaVu Sans Mono}[Scale=0.9]
\begin{document}
Hello World. 你好世界。こんにちは。안녕하세요。
\end{document}
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "cache_warm.tex"
        tex_path.write_text(test_doc)

        result = subprocess.run(
            [
                str(LUALATEX),
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-output-directory={tmpdir}",
                str(tex_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmpdir,
        )

        pdf_path = Path(tmpdir) / "cache_warm.pdf"
        if pdf_path.exists():
            print("  ✓ Font cache warmed successfully")
            return True
        else:
            print("  Warning: Font cache warming failed (OK if fonts missing)")
            print(
                f"    Error: {result.stderr[-500:] if result.stderr else 'No stderr'}"
            )
            return False


def main() -> int:
    """Main entry point."""
    print("TinyTeX Setup for PromptGrimoire PDF Export")
    print("=" * 50)

    # Check system fonts first
    print()
    missing_fonts = check_system_fonts()
    if missing_fonts:
        print()
        print("WARNING: Missing system fonts for full Unicode support:")
        for font in missing_fonts:
            print(f"  - {font}")
        print()
        print("Install with your package manager. See docstring for commands.")
        print()

    # Install TinyTeX
    print()
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

    # Warm font cache
    print()
    warm_font_cache()

    print()
    print("Setup complete!")
    print(f"latexmk path: {LATEXMK}")
    print()
    if missing_fonts:
        print("WARNING: Some system fonts are missing - see above for details.")
        print()
    print("Note: First compilation with CJK fonts may use ~6GB RAM")
    print("for font cache generation. Subsequent compilations are faster.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
