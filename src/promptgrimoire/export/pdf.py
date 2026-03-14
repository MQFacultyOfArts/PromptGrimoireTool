"""LaTeX to PDF compilation via TinyTeX/latexmk.

Uses LuaLaTeX for better font support (fontspec) and highlighting (lua-ul).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from promptgrimoire.config import get_settings

logger = structlog.get_logger()


class LaTeXCompilationError(Exception):
    """LaTeX compilation failed with paths to debug files."""

    def __init__(self, message: str, tex_path: Path, log_path: Path) -> None:
        self.tex_path = tex_path
        self.log_path = log_path
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.args[0]}\n  TeX: {self.tex_path}\n  Log: {self.log_path}"


class LaTeXCompileStageShortCircuit(Exception):
    """Sentinel raised by the test harness before spawning latexmk."""

    def __init__(self, tex_path: Path) -> None:
        self.tex_path = tex_path
        super().__init__(f"latexmk stage short-circuited for {tex_path}")


# TinyTeX installation paths
TINYTEX_DIR = Path.home() / ".TinyTeX"
TINYTEX_BIN = TINYTEX_DIR / "bin" / "x86_64-linux"
TINYTEX_LATEXMK = TINYTEX_BIN / "latexmk"
_TEST_FLAGS = {"short_circuit_latexmk": False}


def set_latexmk_short_circuit(enabled: bool) -> None:
    """Enable the test-harness short-circuit before the latexmk subprocess."""
    _TEST_FLAGS["short_circuit_latexmk"] = enabled


def get_latexmk_path() -> str:
    """Resolve path to latexmk executable.

    Resolution order:
    1. APP__LATEXMK_PATH (via Settings)
    2. TinyTeX installation (~/.TinyTeX/bin/x86_64-linux/latexmk)

    Does NOT fall back to system PATH - use TinyTeX only for consistency.

    Returns:
        Path to latexmk executable.

    Raises:
        FileNotFoundError: If latexmk cannot be found.
    """
    # Check Settings override first
    env_path = get_settings().app.latexmk_path
    if env_path:
        path = Path(env_path)
        if path.exists():
            return str(path)
        msg = f"APP__LATEXMK_PATH set to '{env_path}' but file does not exist"
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

    if _TEST_FLAGS["short_circuit_latexmk"]:
        raise LaTeXCompileStageShortCircuit(tex_path)

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
    try:
        _, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    except TimeoutError:
        logger.warning(
            "latex_compilation_timeout",
            operation="compile_latex",
            tex_path=str(tex_path),
        )
        proc.kill()
        raise LaTeXCompilationError(
            "LaTeX compilation timed out after 120s",
            tex_path=tex_path,
            log_path=output_dir / (tex_path.stem + ".log"),
        ) from None
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
