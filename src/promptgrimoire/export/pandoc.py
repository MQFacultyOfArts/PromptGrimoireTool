"""Pandoc HTML-to-LaTeX conversion and orchestration (P3 functions).

Handles the Pandoc subprocess call for HTML-to-LaTeX conversion and the
top-level annotation conversion orchestrator that coordinates the full
highlight-span-insertion -> Pandoc+Lua-filter pipeline.

Extracted from latex.py during the module split (Issue #134, Phase 1).
Rewired in Phase 4 to use compute_highlight_spans + highlight.lua instead
of the old marker-insertion -> marker-replacement pipeline.
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
from promptgrimoire.export.list_normalizer import normalize_list_values

logger = logging.getLogger(__name__)

# Path to highlight.lua Pandoc filter (always included for annotation export)
_HIGHLIGHT_FILTER = Path(__file__).parent / "filters" / "highlight.lua"


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


# ---------------------------------------------------------------------------
# Annotation post-processing: move \annot outside restricted contexts
# ---------------------------------------------------------------------------
# \annot contains \marginalia + \parbox which expand \par. LaTeX forbids
# \par inside non-\long command arguments (\textbf, \emph, \section, etc.).
# The Lua filter's Header callback handles headings, but \textbf/\emph are
# inline and cannot be detected in the Lua filter. A lightweight post-
# processing pass moves any \annot at brace depth > 0 to depth 0.


def _brace_depth_at(latex: str, pos: int) -> int:
    """Calculate brace nesting depth at a position in a LaTeX string."""
    depth = 0
    for j in range(pos):
        if latex[j] == "{":
            depth += 1
        elif latex[j] == "}":
            depth -= 1
    return depth


def _find_closing_brace_at_depth(latex: str, start: int, target_depth: int) -> int:
    """Find ``}`` reducing depth to *target_depth* from *start*."""
    depth = _brace_depth_at(latex, start)
    for i in range(start, len(latex)):
        if latex[i] == "{":
            depth += 1
        elif latex[i] == "}":
            depth -= 1
            if depth == target_depth:
                return i
    return -1


def _find_matching_brace(latex: str, open_pos: int) -> int:
    """Find the position of the matching closing brace.

    Args:
        latex: LaTeX string.
        open_pos: Position of the opening '{'.

    Returns:
        Position of the matching '}', or -1 if not found.
    """
    depth = 0
    for i in range(open_pos, len(latex)):
        if latex[i] == "{":
            depth += 1
        elif latex[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_annot_command(latex: str, pos: int) -> str | None:
    r"""Extract a complete ``\annot{...}{...}`` command starting at pos.

    Returns the full command text including both brace groups, or None if
    the structure doesn't match.
    """
    prefix = r"\annot"
    if not latex[pos:].startswith(prefix):
        return None

    cursor = pos + len(prefix)

    # Extract first brace group {colour}
    if cursor >= len(latex) or latex[cursor] != "{":
        return None
    end1 = _find_matching_brace(latex, cursor)
    if end1 == -1:
        return None

    cursor = end1 + 1

    # Extract second brace group {margin content}
    if cursor >= len(latex) or latex[cursor] != "{":
        return None
    end2 = _find_matching_brace(latex, cursor)
    if end2 == -1:
        return None

    return latex[pos : end2 + 1]


def _move_annots_outside_restricted(latex: str) -> str:
    r"""Move ``\annot`` commands out of any brace group where they're nested.

    The ``\annot`` macro uses ``\marginalia`` and ``\parbox`` which contain
    ``\par``. Since ``\par`` is forbidden inside most LaTeX command arguments
    (any non-``\long`` command like ``\textbf``, ``\emph``, ``\section``,
    etc.), ``\annot`` must appear at brace depth 0.

    Uses brace-depth tracking -- no hardcoded command name list.

    Args:
        latex: LaTeX with ``\annot`` commands potentially inside brace groups.

    Returns:
        LaTeX with all ``\annot`` commands at brace depth 0.
    """
    if r"\annot" not in latex:
        return latex

    result = latex
    max_iterations = 50  # Safety limit
    for _ in range(max_iterations):
        moved = False
        pos = 0
        while pos < len(result):
            idx = result.find(r"\annot", pos)
            if idx == -1:
                break

            # Verify it's \annot{ not \annotation or similar
            after = idx + len(r"\annot")
            if after < len(result) and result[after] != "{":
                pos = after
                continue

            depth = _brace_depth_at(result, idx)
            if depth <= 0:
                pos = after
                continue

            # \annot is nested at depth > 0 -- extract and move out
            annot_text = _extract_annot_command(result, idx)
            if not annot_text:
                pos = after
                continue

            annot_end_pos = idx + len(annot_text)
            close_pos = _find_closing_brace_at_depth(
                result, annot_end_pos, target_depth=0
            )
            if close_pos == -1:
                pos = after
                continue

            # Remove \annot from current position, place after outermost }
            result = (
                result[:idx]
                + result[annot_end_pos : close_pos + 1]
                + annot_text
                + result[close_pos + 1 :]
            )
            moved = True
            break  # Restart since positions shifted

        if not moved:
            break

    return result


async def convert_html_to_latex(
    html: str,
    filter_paths: list[Path] | None = None,
) -> str:
    """Convert HTML to LaTeX using Pandoc with optional Lua filters.

    Preprocesses HTML to wrap styled <p> tags in <div> wrappers so Pandoc
    preserves style attributes (via +native_divs). The Lua filters can then
    process these styles for LaTeX output.

    Args:
        html: HTML content to convert.
        filter_paths: Optional list of Lua filter paths to apply.

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
        # Use --no-highlight to avoid undefined syntax highlighting macros
        cmd = [
            "pandoc",
            "-f",
            "html+native_divs",
            "-t",
            "latex",
            "--no-highlight",
            str(html_path),
        ]
        for fp in filter_paths or []:
            cmd.extend(["--lua-filter", str(fp)])

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
        return latex
    finally:
        html_path.unlink(missing_ok=True)


async def convert_html_with_annotations(
    html: str,
    highlights: list[dict],
    tag_colours: dict[str, str],
    filter_paths: list[Path] | None = None,
    word_to_legal_para: dict[int, int | None] | None = None,
) -> str:
    """Convert HTML to LaTeX with annotations via highlight spans + Lua filter.

    This is the main entry point for PDF export. It:
    1. Inserts highlight ``<span>`` elements into HTML (with pre-formatted
       LaTeX annotations in ``data-annots`` attributes)
    2. Converts HTML to LaTeX via Pandoc with ``highlight.lua`` filter
       (which transforms the spans into ``\\highLight`` / ``\\underLine`` /
       ``\\annot`` commands)

    Args:
        html: Raw HTML content (not word-span processed).
        highlights: List of highlight dicts with start_char, end_char,
            tag, author.
        tag_colours: Mapping of tag names to hex colours.
        filter_paths: Optional additional Lua filters (e.g. libreoffice.lua).
        word_to_legal_para: Optional mapping of char index to legal
            paragraph number.

    Returns:
        LaTeX body with highlight + annotation commands.
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

    # Lazy import to avoid circular import:
    # export/__init__ -> pandoc -> highlight_spans -> input_pipeline/html_input
    # -> export/marker_constants -> export/__init__ (cycle)
    from promptgrimoire.export.highlight_spans import compute_highlight_spans  # noqa: PLC0415, I001

    # Insert highlight spans with pre-formatted LaTeX annotations
    span_html = compute_highlight_spans(
        html,
        highlights,
        tag_colours,
        word_to_legal_para=word_to_legal_para,
    )

    # Build filter list: always include highlight.lua, plus caller's filters
    filters: list[Path] = [_HIGHLIGHT_FILTER]
    if filter_paths:
        filters.extend(filter_paths)

    # Convert to LaTeX via Pandoc + Lua filters
    latex = await convert_html_to_latex(span_html, filter_paths=filters)

    # Move \annot commands outside restricted brace groups (\textbf, etc.)
    # where \par is forbidden -- see Issue #132
    return _move_annots_outside_restricted(latex)
