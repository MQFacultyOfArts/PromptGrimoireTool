"""LaTeX to PDF compilation via TinyTeX/latexmk.

Uses LuaLaTeX for better font support (fontspec) and highlighting (lua-ul).
"""

from __future__ import annotations

import asyncio
import os
import signal
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

# Cap concurrent LaTeX compilations to prevent OOM from stacked processes.
# Each lualatex process uses 200-500MB; on an 8GB VM, 2 concurrent is safe.
_compile_semaphore = asyncio.Semaphore(2)


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

    async with _compile_semaphore:
        return await _run_latexmk(tex_path, output_dir)


async def _run_latexmk(tex_path: Path, output_dir: Path) -> Path:
    """Run latexmk subprocess with process group isolation."""
    latexmk = get_latexmk_path()

    # Resolve to absolute paths before changing cwd
    tex_path = tex_path.resolve()
    output_dir = output_dir.resolve()

    cmd = [
        latexmk,
        "-lualatex",  # Use LuaLaTeX engine
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={output_dir}",
        str(tex_path),
    ]

    # cwd=output_dir: luaotfload's color-emoji harf shaper writes PNG
    # cache files via os.tmpdir(). Under systemd ProtectSystem=strict,
    # the service WorkingDirectory is read-only, causing a nil-index
    # crash in harf-plug.lua:721. Setting cwd to the writable output
    # directory resolves this.
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        cwd=str(output_dir),
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=120
        )
    except TimeoutError:
        logger.warning(
            "latex_compilation_timeout",
            operation="compile_latex",
            tex_path=str(tex_path),
        )
        os.killpg(proc.pid, signal.SIGKILL)
        raise LaTeXCompilationError(
            "LaTeX compilation timed out after 120s",
            tex_path=tex_path,
            log_path=output_dir / (tex_path.stem + ".log"),
        ) from None
    returncode = proc.returncode or 0
    stdout_text = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
    stderr_text = stderr_bytes.decode(errors="replace") if stderr_bytes else ""

    # Return path to generated PDF
    pdf_name = tex_path.stem + ".pdf"
    pdf_path = output_dir / pdf_name

    log_file = output_dir / (tex_path.stem + ".log")

    # On failure, log subprocess output and extract LaTeX error lines
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        # Log captured subprocess output (truncated to last 4K chars)
        logger.error(
            "latex_subprocess_output",
            export_stage="latex_compile",
            latex_stdout=stdout_text[-4096:],
            latex_stderr=stderr_text[-4096:],
            return_code=returncode,
        )

        # Extract !-prefixed error lines from the .log file
        _log_latex_errors(log_file, tex_path)

        if not pdf_path.exists():
            raise LaTeXCompilationError(
                f"LaTeX compilation failed (exit {returncode}): PDF not created",
                tex_path=tex_path,
                log_path=log_file,
            )
        raise LaTeXCompilationError(
            f"LaTeX compilation failed (exit {returncode}): PDF is empty",
            tex_path=tex_path,
            log_path=log_file,
        )

    # On success, optionally log stderr at DEBUG level
    if stderr_text:
        logger.debug(
            "latex_compile_stderr",
            export_stage="latex_compile",
            latex_stderr=stderr_text[-4096:],
        )

    return pdf_path


def _log_latex_errors(log_file: Path, tex_path: Path) -> None:
    """Extract and log !-prefixed error lines from a LaTeX log file."""
    if log_file.exists():
        log_content = log_file.read_text(errors="replace")
        error_lines = [
            line.strip() for line in log_content.splitlines() if line.startswith("!")
        ]
    else:
        error_lines = []

    logger.error(
        "latex_compilation_failed",
        export_stage="latex_compile",
        latex_errors=error_lines,
        tex_path=str(tex_path),
        log_path=str(log_file),
    )
