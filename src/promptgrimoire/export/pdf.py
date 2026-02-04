"""LaTeX to PDF compilation via TinyTeX/latexmk.

Uses LuaLaTeX for better font support (fontspec) and highlighting (lua-ul).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


class LaTeXCompilationError(Exception):
    """LaTeX compilation failed with paths to debug files."""

    def __init__(self, message: str, tex_path: Path, log_path: Path) -> None:
        self.tex_path = tex_path
        self.log_path = log_path
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.args[0]}\n  TeX: {self.tex_path}\n  Log: {self.log_path}"


# TinyTeX installation paths
TINYTEX_DIR = Path.home() / ".TinyTeX"
TINYTEX_BIN = TINYTEX_DIR / "bin" / "x86_64-linux"
TINYTEX_LATEXMK = TINYTEX_BIN / "latexmk"


def get_latexmk_path() -> str:
    """Resolve path to latexmk executable.

    Resolution order:
    1. LATEXMK_PATH env var (explicit override)
    2. TinyTeX installation (~/.TinyTeX/bin/x86_64-linux/latexmk)

    Does NOT fall back to system PATH - use TinyTeX only for consistency.

    Returns:
        Path to latexmk executable.

    Raises:
        FileNotFoundError: If latexmk cannot be found.
    """
    # Check env var override first
    env_path = os.environ.get("LATEXMK_PATH")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return str(path)
        msg = f"LATEXMK_PATH set to '{env_path}' but file does not exist"
        raise FileNotFoundError(msg)

    # Check TinyTeX installation
    if TINYTEX_LATEXMK.exists():
        return str(TINYTEX_LATEXMK)

    msg = (
        "latexmk not found. Install TinyTeX with: uv run python scripts/setup_latex.py"
    )
    raise FileNotFoundError(msg)


async def compile_latex(tex_path: Path, output_dir: Path | None = None) -> Path:
    """Compile LaTeX to PDF using latexmk with LuaLaTeX.

    Uses latexmk for automatic multi-pass compilation with LuaLaTeX engine.
    LuaLaTeX provides:
    - fontspec for system fonts (Times New Roman, Arial)
    - lua-ul for robust underlining/highlighting

    Args:
        tex_path: Path to the .tex file.
        output_dir: Optional output directory. Defaults to tex_path's parent.

    Returns:
        Path to the generated PDF file.

    Raises:
        subprocess.CalledProcessError: If compilation fails.
        FileNotFoundError: If latexmk cannot be found.
    """
    tex_path = Path(tex_path)
    output_dir = tex_path.parent if output_dir is None else Path(output_dir)

    latexmk = get_latexmk_path()

    cmd = [
        latexmk,
        "-lualatex",  # Use LuaLaTeX engine
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={output_dir}",
        str(tex_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, _ = await proc.communicate()
    returncode = proc.returncode or 0

    # Return path to generated PDF
    pdf_name = tex_path.stem + ".pdf"
    pdf_path = output_dir / pdf_name

    log_file = output_dir / (tex_path.stem + ".log")

    # Check if PDF was actually created
    if not pdf_path.exists():
        raise LaTeXCompilationError(
            f"LaTeX compilation failed (exit {returncode}): PDF not created",
            tex_path=tex_path,
            log_path=log_file,
        )

    # Check for empty PDF (indicates compilation error even if file exists)
    if pdf_path.stat().st_size == 0:
        raise LaTeXCompilationError(
            f"LaTeX compilation failed (exit {returncode}): PDF is empty",
            tex_path=tex_path,
            log_path=log_file,
        )

    return pdf_path
