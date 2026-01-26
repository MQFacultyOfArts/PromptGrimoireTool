#!/usr/bin/env python3
"""Convert HTML to PDF via Pandoc and LaTeX.

Usage:
    uv run python scripts/html_to_pdf.py input.html [output.pdf]
    uv run python scripts/html_to_pdf.py --filter libreoffice input.html
    uv run python scripts/html_to_pdf.py --latex-only input.html  # Generate .tex only
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
FILTERS_DIR = PROJECT_ROOT / "src" / "promptgrimoire" / "export" / "filters"
OUTPUT_DIR = PROJECT_ROOT / "output"

# TinyTeX paths
TINYTEX_BIN = Path.home() / ".TinyTeX" / "bin" / "x86_64-linux"


def find_latexmk() -> Path | None:
    """Find latexmk executable."""
    # Check TinyTeX first
    tinytex_latexmk = TINYTEX_BIN / "latexmk"
    if tinytex_latexmk.exists():
        return tinytex_latexmk

    # Check system PATH
    system_latexmk = shutil.which("latexmk")
    if system_latexmk:
        return Path(system_latexmk)

    return None


def find_pdflatex() -> Path | None:
    """Find pdflatex executable."""
    tinytex_pdflatex = TINYTEX_BIN / "pdflatex"
    if tinytex_pdflatex.exists():
        return tinytex_pdflatex

    system_pdflatex = shutil.which("pdflatex")
    if system_pdflatex:
        return Path(system_pdflatex)

    return None


def html_to_latex(
    input_html: Path,
    output_tex: Path,
    *,
    filter_name: str | None = None,
    standalone: bool = True,
) -> None:
    """Convert HTML to LaTeX using Pandoc.

    Args:
        input_html: Path to input HTML file.
        output_tex: Path to output .tex file.
        filter_name: Name of Lua filter in filters/ directory (e.g., "libreoffice").
        standalone: If True, generate complete document with preamble.
    """
    cmd = ["pandoc"]

    if standalone:
        cmd.append("-s")
        # Add packages needed by our custom LaTeX output
        cmd.extend(
            [
                "-V",
                "header-includes=\\usepackage{longtable}",
                "-V",
                "header-includes=\\usepackage{changepage}",  # For adjustwidth
            ]
        )

    cmd.extend(["-f", "html", "-t", "latex"])

    if filter_name:
        filter_path = FILTERS_DIR / f"{filter_name}.lua"
        if not filter_path.exists():
            raise FileNotFoundError(f"Filter not found: {filter_path}")
        cmd.extend(["--lua-filter", str(filter_path)])

    cmd.extend([str(input_html), "-o", str(output_tex)])

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        print(f"Pandoc stderr:\n{result.stderr}", file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd)

    print(f"Generated: {output_tex}")


def clean_latex_artifacts(tex_path: Path, output_dir: Path) -> None:
    """Remove LaTeX auxiliary files from previous runs.

    Cleans up: .aux, .log, .fls, .fdb_latexmk, .out, .toc, .pdf
    """
    stem = tex_path.stem
    extensions = [".aux", ".log", ".fls", ".fdb_latexmk", ".out", ".toc", ".pdf"]

    for ext in extensions:
        artifact = output_dir / (stem + ext)
        if artifact.exists():
            artifact.unlink()


def latex_to_pdf(tex_path: Path, output_dir: Path | None = None) -> Path:
    """Compile LaTeX to PDF.

    Tries latexmk first (handles multi-pass), falls back to pdflatex.

    Args:
        tex_path: Path to .tex file.
        output_dir: Output directory (defaults to tex_path's parent).

    Returns:
        Path to generated PDF.
    """
    output_dir = output_dir or tex_path.parent
    pdf_path = output_dir / (tex_path.stem + ".pdf")

    # Clean up artifacts from previous runs
    clean_latex_artifacts(tex_path, output_dir)

    latexmk = find_latexmk()
    if latexmk:
        cmd = [
            str(latexmk),
            "-pdf",
            "-interaction=nonstopmode",
            f"-output-directory={output_dir}",
            str(tex_path),
        ]
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        # latexmk may return non-zero even on success with warnings
        if pdf_path.exists():
            print(f"Generated: {pdf_path}")
            if result.returncode != 0:
                print("Note: latexmk reported warnings/errors but PDF was generated")
            return pdf_path

        print(f"latexmk failed:\n{result.stderr}", file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd)

    pdflatex = find_pdflatex()
    if pdflatex:
        # Run pdflatex twice for references
        cmd = [
            str(pdflatex),
            "-interaction=nonstopmode",
            f"-output-directory={output_dir}",
            str(tex_path),
        ]
        print(f"Running: {' '.join(cmd)} (x2 for references)")

        for i in range(2):
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0 and not pdf_path.exists():
                print(
                    f"pdflatex pass {i + 1} failed:\n{result.stderr}", file=sys.stderr
                )
                raise subprocess.CalledProcessError(result.returncode, cmd)

        print(f"Generated: {pdf_path}")
        return pdf_path

    raise RuntimeError("No LaTeX compiler found. Install TinyTeX or TeX Live.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert HTML to PDF via Pandoc and LaTeX"
    )
    parser.add_argument("input", type=Path, help="Input HTML file")
    parser.add_argument("output", type=Path, nargs="?", help="Output PDF file")
    parser.add_argument(
        "--filter",
        choices=["libreoffice", "legal"],
        help="Lua filter to apply (from src/promptgrimoire/export/filters/)",
    )
    parser.add_argument(
        "--latex-only",
        action="store_true",
        help="Generate .tex file only, don't compile to PDF",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Output directory (default: {OUTPUT_DIR})",
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    # Determine output paths
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tex_path = args.output_dir / (args.input.stem + "_filtered.tex")

    try:
        # Step 1: HTML → LaTeX
        html_to_latex(args.input, tex_path, filter_name=args.filter)

        if args.latex_only:
            return 0

        # Step 2: LaTeX → PDF
        latex_to_pdf(tex_path, args.output_dir)

        return 0

    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}", file=sys.stderr)
        return e.returncode
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
