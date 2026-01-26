"""LaTeX to PDF compilation via TinyTeX/latexmk.

Uses LuaLaTeX for better font support (fontspec) and highlighting (lua-ul).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def compile_latex(tex_path: Path, output_dir: Path | None = None) -> Path:
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
    """
    tex_path = Path(tex_path)
    output_dir = tex_path.parent if output_dir is None else Path(output_dir)

    cmd = [
        "latexmk",
        "-lualatex",  # Use LuaLaTeX engine
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={output_dir}",
        str(tex_path),
    ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)

    # Return path to generated PDF
    pdf_name = tex_path.stem + ".pdf"
    return output_dir / pdf_name
