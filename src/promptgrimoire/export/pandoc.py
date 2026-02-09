"""Pandoc HTML-to-LaTeX conversion and orchestration (P3 functions).

Handles the Pandoc subprocess call for HTML-to-LaTeX conversion and the
top-level annotation conversion orchestrator that coordinates the full
marker-insertion -> Pandoc -> marker-replacement pipeline.

Extracted from latex.py during the module split (Issue #134, Phase 1).
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from promptgrimoire.export.html_normaliser import (
    fix_midword_font_splits,
    normalise_styled_paragraphs,
    strip_scripts_and_styles,
)
from promptgrimoire.export.latex import (
    _move_annots_outside_restricted,
    _replace_markers_with_annots,
    _strip_texorpdfstring,
)
from promptgrimoire.export.list_normalizer import normalize_list_values
from promptgrimoire.export.unicode_latex import _strip_control_chars
from promptgrimoire.input_pipeline.html_input import insert_markers_into_dom

logger = logging.getLogger(__name__)


def _fix_invalid_newlines(latex: str) -> str:
    """Remove \\newline{} commands in invalid table contexts.

    Pandoc converts <br> tags to \\newline{}, but this is invalid in LaTeX when:
    - At the start of a table row (no paragraph to end)
    - Right before a column separator (&)
    - Consecutive \\newline{} with no content between

    Args:
        latex: Raw LaTeX content from Pandoc.

    Returns:
        LaTeX with invalid \\newline{} removed.
    """
    # Remove consecutive \newline{} first - leave none (they're all invalid here)
    latex = re.sub(r"(\\newline\{\}\s*){2,}", "", latex)

    # Remove \newline{} at start of longtable (after column spec, possibly on next line)
    # Pattern: \begin{longtable}{...}\n\newline{}
    latex = re.sub(
        r"(\\begin\{longtable\}\{[^}]+\})\s*\\newline\{\}",
        r"\1\n",
        latex,
    )

    # Remove \newline{} right before & (column separator)
    latex = re.sub(r"\\newline\{\}\s*&", " &", latex)

    # Remove \newline{} right after \\ (row end)
    latex = re.sub(r"\\\\\s*\\newline\{\}", r"\\\\", latex)

    # Remove standalone \newline{} at the very start of table content
    # (after longtable row ends with \\)
    latex = re.sub(r"(\\\\\s*\n)\s*\\newline\{\}", r"\1", latex)

    # Remove \newline{} that appears alone on a line at table start
    # (line starting with \newline{} followed by optional whitespace and &)
    latex = re.sub(r"^\s*\\newline\{\}\s*$", "", latex, flags=re.MULTILINE)

    return latex


async def convert_html_to_latex(html: str, filter_path: Path | None = None) -> str:
    """Convert HTML to LaTeX using Pandoc with optional Lua filter.

    Preprocesses HTML to wrap styled <p> tags in <div> wrappers so Pandoc
    preserves style attributes (via +native_divs). The Lua filter can then
    process these styles for LaTeX output.

    Args:
        html: HTML content to convert.
        filter_path: Optional path to Lua filter for legal document fixes.

    Returns:
        LaTeX body content (no preamble).

    Raises:
        subprocess.CalledProcessError: If Pandoc fails.
    """
    # Preprocess HTML: convert <li value="N"> to <ol start="N"> for Pandoc
    html = normalize_list_values(html)

    # Preprocess HTML to wrap styled <p> tags for Pandoc attribute preservation
    normalised_html = normalise_styled_paragraphs(html)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False
    ) as html_file:
        html_file.write(normalised_html)
        html_path = Path(html_file.name)

    try:
        # Use +native_divs to preserve div attributes in Pandoc AST
        # Use --no-highlight to avoid undefined syntax highlighting macros (\VERB, etc.)
        cmd = [
            "pandoc",
            "-f",
            "html+native_divs",
            "-t",
            "latex",
            "--no-highlight",
            str(html_path),
        ]
        if filter_path is not None:
            cmd.extend(["--lua-filter", str(filter_path)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        # returncode is guaranteed to be set after communicate() returns
        assert proc.returncode is not None
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, stderr_bytes.decode()
            )
        # Post-process Pandoc output
        latex = stdout_bytes.decode()
        latex = _fix_invalid_newlines(latex)  # Fix \newline{} in table contexts
        latex = _strip_texorpdfstring(latex)  # Strip for luatexja compatibility
        return latex
    finally:
        html_path.unlink(missing_ok=True)


async def convert_html_with_annotations(
    html: str,
    highlights: list[dict],
    tag_colours: dict[str, str],  # noqa: ARG001 - colours used in preamble generation
    filter_path: Path | None = None,
    word_to_legal_para: dict[int, int | None] | None = None,
) -> str:
    """Convert HTML to LaTeX with annotations inserted as marginnote+soul.

    This is the main entry point for PDF export. It:
    1. Inserts markers into HTML at annotation positions
    2. Converts HTML to LaTeX via Pandoc
    3. Replaces markers with \\annot{} commands

    Args:
        html: Raw HTML content (not word-span processed).
        highlights: List of highlight dicts with start_char, end_char, tag, author.
        tag_colours: Mapping of tag names to hex colours.
        filter_path: Optional Lua filter for legal document fixes.
        word_to_legal_para: Optional mapping of word index to legal paragraph number.

    Returns:
        LaTeX body with marginnote+soul annotations at correct positions.
    """
    logger.debug(
        "[LATEX] convert_html_with_annotations: count=%d, ids=%s",
        len(highlights),
        [h.get("id", "")[:8] for h in highlights],
    )

    # Strip script/style tags from browser copy-paste content
    html = strip_scripts_and_styles(html)

    # Fix mid-word font tag splits from LibreOffice RTF export
    html = fix_midword_font_splits(html)

    # Insert markers at character positions matching extract_text_from_html
    marked_html, marker_highlights = insert_markers_into_dom(html, highlights)

    # Strip control characters that are invalid in LaTeX AFTER markers are placed
    # (e.g., BLNS contains 0x01-0x1F non-whitespace controls)
    marked_html = _strip_control_chars(marked_html)

    # Convert to LaTeX
    latex = await convert_html_to_latex(marked_html, filter_path=filter_path)

    # Replace markers with annots
    result = _replace_markers_with_annots(latex, marker_highlights, word_to_legal_para)

    # Move \annot commands outside sectioning commands (\section{}, etc.)
    # where \par is forbidden -- see Issue #132
    return _move_annots_outside_restricted(result)
