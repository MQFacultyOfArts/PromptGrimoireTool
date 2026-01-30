"""HTML to LaTeX conversion with annotation insertion.

Uses Pandoc for HTML-to-LaTeX conversion with marker-based annotation insertion.
Annotations are inserted as text markers before Pandoc conversion, then replaced
with LaTeX marginnote+soul commands after conversion.

Pipeline:
1. HTML normalisation (wrap styled <p> tags for Pandoc attribute preservation)
2. Marker insertion (annotation positions)
3. Pandoc conversion (HTML → LaTeX with Lua filter)
4. Marker replacement (→ \\annot{} commands)
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from lark import Lark
from pylatexenc.latexwalker import (
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexWalker,
)

from promptgrimoire.export.html_normaliser import (
    fix_midword_font_splits,
    normalise_styled_paragraphs,
)
from promptgrimoire.export.list_normalizer import normalize_list_values

logger = logging.getLogger(__name__)


class MarkerTokenType(Enum):
    """Token types for marker lexer."""

    TEXT = "TEXT"
    HLSTART = "HLSTART"
    HLEND = "HLEND"
    ANNMARKER = "ANNMARKER"


@dataclass(frozen=True, slots=True)
class MarkerToken:
    """A token from the marker lexer.

    Attributes:
        type: The token type (TEXT, HLSTART, HLEND, ANNMARKER)
        value: The raw string value matched
        index: For marker tokens, the highlight index (e.g., 1 from HLSTART{1}ENDHL).
               None for TEXT tokens.
        start_pos: Start byte position in input
        end_pos: End byte position in input
    """

    type: MarkerTokenType
    value: str
    index: int | None
    start_pos: int
    end_pos: int


@dataclass(frozen=True, slots=True)
class Region:
    """A contiguous span of text with a constant set of active highlights.

    Attributes:
        text: The text content of this region
        active: Frozenset of highlight indices currently active in this region
        annots: List of annotation marker indices that appeared in this region
    """

    text: str
    active: frozenset[int]
    annots: list[int]


def build_regions(tokens: list[MarkerToken]) -> list[Region]:
    """Convert a token stream into regions with active highlight tracking.

    Implements a linear state machine that tracks which highlights are
    currently active as we scan through the tokens. Each time the active
    set changes (at HLSTART or HLEND), a new region boundary is created.

    Args:
        tokens: List of MarkerToken from tokenize_markers()

    Returns:
        List of Region objects, each with constant active highlight set

    Example:
        >>> tokens = tokenize_markers("a HLSTART{1}ENDHL b HLEND{1}ENDHL c")
        >>> regions = build_regions(tokens)
        >>> [(r.text, r.active) for r in regions]
        [('a ', frozenset()), ('b ', frozenset({1})), ('c', frozenset())]
    """
    if not tokens:
        return []

    regions: list[Region] = []
    active: set[int] = set()
    current_text = ""

    def flush_region() -> None:
        """Emit current region if there's accumulated text."""
        nonlocal current_text
        if current_text:
            regions.append(
                Region(
                    text=current_text,
                    active=frozenset(active),
                    annots=[],  # Annotations added by ANNMARKER after flush
                )
            )
            current_text = ""

    for token in tokens:
        if token.type == MarkerTokenType.TEXT:
            current_text += token.value

        elif token.type == MarkerTokenType.HLSTART:
            flush_region()
            if token.index is not None:
                active.add(token.index)

        elif token.type == MarkerTokenType.HLEND:
            flush_region()
            if token.index is not None:
                active.discard(token.index)

        elif token.type == MarkerTokenType.ANNMARKER and token.index is not None:
            # Attach annotation to the PREVIOUS region (highlight just ended).
            # ANNMARKER appears after HLEND, so belongs to the flushed region.
            # If no region exists yet but we have text, flush it first.
            if not regions and current_text:
                flush_region()
            if regions:
                regions[-1].annots.append(token.index)

    # Flush any remaining text
    flush_region()

    return regions


def generate_underline_wrapper(
    active: frozenset[int],
    highlights: dict[int, dict[str, Any]],
) -> Callable[[str], str]:
    """Create a function that wraps text in underline commands.

    Based on overlap count:
    - 0 highlights: identity function (no underlines)
    - 1 highlight: single 1pt underline in tag's dark colour
    - 2 highlights: stacked 2pt + 1pt underlines (outer is lower index)
    - 3+ highlights: single 4pt underline in many-dark colour

    Args:
        active: Frozenset of highlight indices currently active
        highlights: Mapping from highlight index to highlight dict

    Returns:
        Function that takes text and returns text wrapped in underlines
    """
    if not active:
        return lambda text: text

    count = len(active)

    if count >= 3:
        # Many overlapping: single thick line
        def wrap_many(text: str) -> str:
            return rf"\underLine[color=many-dark, height=4pt, bottom=-5pt]{{{text}}}"

        return wrap_many

    # Sort indices for deterministic ordering (lower index = outer)
    sorted_indices = sorted(active)

    def get_dark_colour(idx: int) -> str:
        tag = highlights.get(idx, {}).get("tag", "unknown")
        safe_tag = tag.replace("_", "-")
        return f"tag-{safe_tag}-dark"

    if count == 1:
        colour = get_dark_colour(sorted_indices[0])

        def wrap_single(text: str) -> str:
            return rf"\underLine[color={colour}, height=1pt, bottom=-3pt]{{{text}}}"

        return wrap_single

    # count == 2: stacked underlines
    outer_colour = get_dark_colour(sorted_indices[0])
    inner_colour = get_dark_colour(sorted_indices[1])

    def wrap_double(text: str) -> str:
        inner = rf"\underLine[color={inner_colour}, height=1pt, bottom=-3pt]{{{text}}}"
        return rf"\underLine[color={outer_colour}, height=2pt, bottom=-3pt]{{{inner}}}"

    return wrap_double


def generate_highlight_wrapper(
    active: frozenset[int],
    highlights: dict[int, dict[str, Any]],
) -> Callable[[str], str]:
    """Create a function that wraps text in highLight commands.

    Each active highlight adds a nested \\highLight[tag-X-light]{...} wrapper.
    Lower indices are outer (sorted for deterministic output).

    Args:
        active: Frozenset of highlight indices currently active
        highlights: Mapping from highlight index to highlight dict

    Returns:
        Function that takes text and returns text wrapped in highlights
    """
    if not active:
        return lambda text: text

    # Sort indices for deterministic ordering (lower index = outer)
    sorted_indices = sorted(active)

    def get_light_colour(idx: int) -> str:
        tag = highlights.get(idx, {}).get("tag", "unknown")
        safe_tag = tag.replace("_", "-")
        return f"tag-{safe_tag}-light"

    def wrap(text: str) -> str:
        result = text
        # Wrap from innermost (highest index) to outermost (lowest index)
        for idx in reversed(sorted_indices):
            colour = get_light_colour(idx)
            result = rf"\highLight[{colour}]{{{result}}}"
        return result

    return wrap


def _wrap_content_with_nested_highlights(
    content: str,
    active: frozenset[int],
    highlights: dict[int, dict[str, Any]],
) -> str:
    """Wrap content in nested highlights, splitting at environment boundaries.

    Similar to _wrap_content_with_highlight but handles multiple nested
    highlight layers and underlines.

    Args:
        content: Text content that may contain environment boundaries
        active: Frozenset of active highlight indices
        highlights: Mapping from highlight index to highlight dict

    Returns:
        LaTeX with properly split and wrapped highlight commands
    """
    underline_wrap = generate_underline_wrapper(active, highlights)
    highlight_wrap = generate_highlight_wrapper(active, highlights)

    # Inline delimiters that require splitting
    inline_delimiters = [r"\par", r"\\", r"\tabularnewline", "&"]

    # Find all split points from inline delimiters
    split_points: list[tuple[int, int, str]] = []

    for delim in inline_delimiters:
        start = 0
        while True:
            pos = content.find(delim, start)
            if pos == -1:
                break
            split_points.append((pos, pos + len(delim), delim))
            start = pos + 1

    # Also split on environment boundaries (\begin{...} and \end{...})
    # Use regex instead of pylatexenc to catch partial environments
    # (e.g., \end{enumerate} without matching \begin in this content)
    env_pattern = re.compile(r"(\\(?:begin|end)\{[^}]+\}(?:\{[^}]*\})*)")
    for match in env_pattern.finditer(content):
        split_points.append((match.start(), match.end(), match.group(0)))

    # Sort by position
    split_points.sort(key=lambda x: x[0])

    if not split_points:
        # No splits needed
        return highlight_wrap(underline_wrap(content))

    # Build result by iterating through segments
    result_parts: list[str] = []
    pos = 0

    for start, end, boundary_text in split_points:
        if start > pos:
            # Text before this boundary
            segment = content[pos:start]
            if segment.strip():
                result_parts.append(highlight_wrap(underline_wrap(segment)))
            else:
                result_parts.append(segment)  # Preserve whitespace-only

        # The boundary itself (not wrapped in highlight)
        result_parts.append(boundary_text)
        pos = end

    # Text after last boundary
    if pos < len(content):
        segment = content[pos:]
        if segment.strip():
            result_parts.append(highlight_wrap(underline_wrap(segment)))
        else:
            result_parts.append(segment)

    return "".join(result_parts)


def generate_highlighted_latex(
    regions: list[Region],
    highlights: dict[int, dict[str, Any]],
    env_boundaries: list[tuple[int, int, str]],  # noqa: ARG001 - kept for API
) -> str:
    """Generate LaTeX with highlight and underline commands from regions.

    For each region:
    1. If active highlights: wrap in nested \\highLight commands
    2. If active highlights: wrap in \\underLine commands (based on overlap count)
    3. Split at environment boundaries using _wrap_content_with_nested_highlights
    4. Emit \\annot commands for any annotation markers in the region

    Args:
        regions: List of Region objects from build_regions()
        highlights: Mapping from highlight index to highlight dict
        env_boundaries: Environment boundaries from _extract_env_boundaries()
                       (not currently used - boundaries are detected per-region)

    Returns:
        Complete LaTeX string with all highlight/underline/annot commands
    """
    if not regions:
        return ""

    result_parts: list[str] = []

    for region in regions:
        if not region.active:
            # No highlights - pass through unchanged
            result_parts.append(region.text)
        else:
            # Get wrappers for this region's active set
            underline_wrap = generate_underline_wrapper(region.active, highlights)
            highlight_wrap = generate_highlight_wrapper(region.active, highlights)

            # Check for inline delimiters or env boundaries that require splitting
            inline_delimiters = [r"\par", r"\\", r"\tabularnewline", "&"]
            has_inline = any(delim in region.text for delim in inline_delimiters)
            has_env = r"\begin{" in region.text or r"\end{" in region.text

            if has_inline or has_env:
                # Has boundaries - use splitting logic
                wrapped = _wrap_content_with_nested_highlights(
                    region.text, region.active, highlights
                )
            else:
                # No boundaries - simple wrap
                wrapped = highlight_wrap(underline_wrap(region.text))

            result_parts.append(wrapped)

        # Emit annotation commands for this region
        for annot_idx in region.annots:
            if annot_idx in highlights:
                hl = highlights[annot_idx]
                para_ref = hl.get("para_ref", "")
                annot_latex = _format_annot(hl, para_ref)
                result_parts.append(annot_latex)

    return "".join(result_parts)


# Lark grammar for marker tokenization
# Literals have higher priority than regex, so markers match first
# TEXT catches everything else with negative lookahead
#
# Note: The marker format is HLSTART0ENDHL (no braces around index),
# matching the production templates _HLSTART_TEMPLATE, _HLEND_TEMPLATE, etc.
_MARKER_GRAMMAR = (
    'HLSTART: "HLSTART" /[0-9]+/ "ENDHL"\n'
    'HLEND: "HLEND" /[0-9]+/ "ENDHL"\n'
    'ANNMARKER: "ANNMARKER" /[0-9]+/ "ENDMARKER"\n'
    r"TEXT: /(?:(?!"
    r"HLSTART[0-9]+ENDHL|"
    r"HLEND[0-9]+ENDHL|"
    r"ANNMARKER[0-9]+ENDMARKER"
    r").)+/s"
)

# Compile once at module load
_marker_lexer = Lark(_MARKER_GRAMMAR, parser=None, lexer="basic")

# Regex to extract index from marker value
# Matches HLSTART0ENDHL, HLEND0ENDHL, ANNMARKER0ENDMARKER formats
_INDEX_EXTRACT_PATTERN = re.compile(r"(\d+)")


def tokenize_markers(latex: str) -> list[MarkerToken]:
    """Tokenize LaTeX text containing highlight markers.

    Converts a string containing HLSTARTnENDHL, HLENDnENDHL, and
    ANNMARKERnENDMARKER markers into a list of MarkerToken objects.
    All text between markers becomes TEXT tokens.

    Args:
        latex: LaTeX string potentially containing markers

    Returns:
        List of MarkerToken objects preserving order and positions

    Example:
        >>> tokens = tokenize_markers("Hello HLSTART{1}ENDHL world")
        >>> [(t.type.value, t.value) for t in tokens]
        [('TEXT', 'Hello '), ('HLSTART', 'HLSTART{1}ENDHL'), ('TEXT', ' world')]
    """
    if not latex:
        return []

    tokens: list[MarkerToken] = []

    for lark_token in _marker_lexer.lex(latex):
        token_type = MarkerTokenType[lark_token.type]

        # Extract index for marker tokens
        index: int | None = None
        if token_type != MarkerTokenType.TEXT:
            match = _INDEX_EXTRACT_PATTERN.search(lark_token.value)
            if match:
                index = int(match.group(1))

        # Lark lexer always provides start_pos and end_pos for tokens
        start_pos = lark_token.start_pos if lark_token.start_pos is not None else 0
        end_pos = lark_token.end_pos if lark_token.end_pos is not None else 0

        tokens.append(
            MarkerToken(
                type=token_type,
                value=lark_token.value,
                index=index,
                start_pos=start_pos,
                end_pos=end_pos,
            )
        )

    return tokens


# Unique marker format that survives Pandoc conversion
# Format: ANNMARKER{index}ENDMARKER for annotation insertion point
# Format: HLSTART{index}ENDHL and HLEND{index}ENDHL for highlight boundaries
_MARKER_TEMPLATE = "ANNMARKER{}ENDMARKER"
_MARKER_PATTERN = re.compile(r"ANNMARKER(\d+)ENDMARKER")
_HLSTART_TEMPLATE = "HLSTART{}ENDHL"
_HLEND_TEMPLATE = "HLEND{}ENDHL"
_HLSTART_PATTERN = re.compile(r"HLSTART(\d+)ENDHL")
_HLEND_PATTERN = re.compile(r"HLEND(\d+)ENDHL")

# Pattern for words - matches _WordSpanProcessor._WORD_PATTERN
_WORD_PATTERN = re.compile(r'["\'\(\[]*[\w\'\-]+[.,;:!?"\'\)\]]*')

# Base LaTeX preamble for LuaLaTeX with marginalia+lua-ul annotation approach
# Note: The \annot command takes 2 parameters: colour name and margin content.
# It places a superscript number at the insertion point with a coloured margin note.
# Highlighting uses lua-ul's \highLight for robust cross-line-break backgrounds.
# marginalia package auto-stacks overlapping margin notes (requires 2+ lualatex runs).
ANNOTATION_PREAMBLE_BASE = r"""
\usepackage{fontspec}
\setmainfont{TeX Gyre Termes}  % Times New Roman equivalent
\usepackage{microtype}         % Better typography (kerning, protrusion)
\usepackage{marginalia}        % Auto-stacking margin notes for LuaLaTeX
\usepackage{longtable}
\usepackage{booktabs}
\usepackage{array}
\usepackage{calc}
\usepackage[hidelinks]{hyperref}
\usepackage{changepage}
\usepackage{luacolor}  % Required by lua-ul for coloured highlights
\usepackage{lua-ul}    % LuaLaTeX highlighting (robust across line breaks)
\usepackage{luabidi}   % Bidirectional text support for LuaLaTeX
\usepackage{fancyvrb}  % Verbatim/code blocks from Pandoc syntax highlighting
\usepackage[a4paper,left=2.5cm,right=6cm,top=2.5cm,bottom=2.5cm]{geometry}

% Pandoc compatibility
\providecommand{\tightlist}{%
  \setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\setlength{\emergencystretch}{3em}  % prevent overfull lines
\setcounter{secnumdepth}{-\maxdimen}  % no section numbering

% Annotation counter and macro
% Usage: \annot{colour-name}{margin content}
% Uses footnotesize for compact margin notes
% marginalia auto-stacks overlapping notes with ysep spacing
\newcounter{annotnum}
\newcommand{\annot}[2]{%
  \stepcounter{annotnum}%
  \textsuperscript{\textcolor{#1}{\textbf{\theannotnum}}}%
  \marginalia[ysep=3pt]{%
    \fcolorbox{#1}{#1!20}{%
      \parbox{4.3cm}{\footnotesize\textbf{\theannotnum.} #2}%
    }%
  }%
}
"""


def generate_tag_colour_definitions(tag_colours: dict[str, str]) -> str:
    """Generate LaTeX \\definecolor commands from tag→colour mapping.

    Generates full-strength, light (30%), and dark (70% black mix) versions
    of each colour. The light versions are used for text highlighting backgrounds,
    and dark versions are used for underlines.

    Args:
        tag_colours: Dict of tag_name → hex colour (e.g., {"jurisdiction": "#1f77b4"})

    Returns:
        LaTeX \\definecolor commands for each tag (full, light, and dark variants),
        plus the many-dark colour for 3+ overlapping highlights.
    """
    definitions: list[str] = []
    for tag, colour in tag_colours.items():
        hex_code = colour.lstrip("#")
        safe_name = tag.replace("_", "-")  # LaTeX-safe name
        # Full colour for borders and text
        definitions.append(f"\\definecolor{{tag-{safe_name}}}{{HTML}}{{{hex_code}}}")
        # Light colour (30% strength) for highlight backgrounds
        # Using xcolor's mixing: 30% of tag colour + 70% white
        definitions.append(f"\\colorlet{{tag-{safe_name}-light}}{{tag-{safe_name}!30}}")
        # Dark variant for underlines (70% base, 30% black)
        definitions.append(
            f"\\colorlet{{tag-{safe_name}-dark}}{{tag-{safe_name}!70!black}}"
        )

    # many-dark colour for 3+ overlapping highlights
    definitions.append(r"\definecolor{many-dark}{HTML}{333333}")

    return "\n".join(definitions)


def build_annotation_preamble(tag_colours: dict[str, str]) -> str:
    """Build complete annotation preamble with tag colour definitions.

    Args:
        tag_colours: Dict of tag_name → hex colour.

    Returns:
        Complete LaTeX preamble string.
    """
    colour_defs = generate_tag_colour_definitions(tag_colours)
    return f"\\usepackage{{xcolor}}\n{colour_defs}\n{ANNOTATION_PREAMBLE_BASE}"


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in text."""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for char, escaped in replacements:
        text = text.replace(char, escaped)
    return text


def _format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp to human-readable format (e.g., '26 Jan 2026 14:30')."""
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y %H:%M")
    except (ValueError, AttributeError):
        return ""


def _strip_test_uuid(name: str) -> str:
    """Strip test UUID suffix from display names.

    E.g., 'Alice Jones 1664E02D' -> 'Alice Jones'.
    """
    # Match trailing hex UUID (8+ hex chars at end after space)
    return re.sub(r"\s+[A-Fa-f0-9]{6,}$", "", name)


def _format_annot(
    highlight: dict[str, Any],
    para_ref: str = "",
) -> str:
    """Format a highlight as a LaTeX \\annot command.

    Layout in margin note:
    **Tag** [para]
    name, date
    ---
    comment text...

    Args:
        highlight: Highlight dict with tag, author, text, comments, created_at.
        para_ref: Paragraph reference string (e.g., "[45]" or "[45]-[48]").

    Returns:
        LaTeX \\annot{colour}{margin_content} command.
    """
    tag = highlight.get("tag", "jurisdiction")
    author = _strip_test_uuid(highlight.get("author", "Unknown"))
    comments = highlight.get("comments", [])
    created_at = highlight.get("created_at", "")

    # Tag colour name (matches \definecolor name)
    colour_name = f"tag-{tag.replace('_', '-')}"

    # Build margin content with footnotesize
    tag_display = tag.replace("_", " ").title()
    timestamp = _format_timestamp(created_at)

    # Line 1: **Tag** [para]
    if para_ref:
        margin_parts = [f"\\textbf{{{_escape_latex(tag_display)}}} {para_ref}"]
    else:
        margin_parts = [f"\\textbf{{{_escape_latex(tag_display)}}}"]

    # Line 2: name, date (tiny)
    if timestamp:
        margin_parts.append(
            f"\\par{{\\scriptsize {_escape_latex(author)}, {timestamp}}}"
        )
    else:
        margin_parts.append(f"\\par{{\\scriptsize {_escape_latex(author)}}}")

    # Add separator and comments if present
    if comments:
        margin_parts.append("\\par\\hrulefill")
        for comment in comments:
            c_author = _strip_test_uuid(comment.get("author", "Unknown"))
            c_text = comment.get("text", "")
            c_timestamp = _format_timestamp(comment.get("created_at", ""))
            # Comment: name, date: text (all small)
            if c_timestamp:
                margin_parts.append(
                    f"\\par{{\\scriptsize \\textbf{{{_escape_latex(c_author)}}}, "
                    f"{c_timestamp}:}} {_escape_latex(c_text)}"
                )
            else:
                margin_parts.append(
                    f"\\par{{\\scriptsize \\textbf{{{_escape_latex(c_author)}:}}}} "
                    f"{_escape_latex(c_text)}"
                )

    margin_content = "".join(margin_parts)

    return f"\\annot{{{colour_name}}}{{{margin_content}}}"


def _insert_markers_into_html(
    html: str, highlights: list[dict]
) -> tuple[str, list[dict]]:
    """Insert annotation and highlight markers into HTML at correct word positions.

    Uses the same word pattern as _WordSpanProcessor to ensure word indices match.
    Inserts three types of markers:
    - HLSTART{n} at start_word (before the word)
    - HLEND{n} after end_word (after the last highlighted word)
    - ANNMARKER{n} after HLEND (so \\annot{} with \\par is outside \\highLight{})

    Args:
        html: Raw HTML content.
        highlights: List of highlight dicts with start_word and end_word.

    Returns:
        Tuple of (html with markers, list of highlights in marker order).
    """
    if not highlights:
        return html, []

    # Sort by start_word, then by tag
    sorted_highlights = sorted(
        highlights, key=lambda h: (h.get("start_word", 0), h.get("tag", ""))
    )

    # Build lookups for marker positions
    # start_markers: word_index -> list of (marker_index, highlight)
    # end_markers: word_index -> list of marker_index for HLEND
    start_markers: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    end_markers: dict[int, list[int]] = defaultdict(list)
    marker_to_highlight: list[dict] = []

    for h in sorted_highlights:
        start = int(h.get("start_word", 0))
        end = int(h.get("end_word", start + 1))
        last_word = end - 1 if end > start else start

        marker_idx = len(marker_to_highlight)
        marker_to_highlight.append(h)
        start_markers[start].append((marker_idx, h))
        end_markers[last_word].append(marker_idx)

    # Process HTML, inserting markers at word positions
    result: list[str] = []
    word_idx = 0
    i = 0

    while i < len(html):
        if html[i] == "<":
            # Skip HTML tags
            tag_end = html.find(">", i)
            if tag_end == -1:
                result.append(html[i:])
                break
            result.append(html[i : tag_end + 1])
            i = tag_end + 1
        else:
            # Text content - check for words
            next_tag = html.find("<", i)
            if next_tag == -1:
                next_tag = len(html)

            text = html[i:next_tag]
            text_result: list[str] = []
            text_pos = 0

            for match in _WORD_PATTERN.finditer(text):
                # Add text before this word
                text_result.append(text[text_pos : match.start()])

                # Insert HLSTART markers before this word
                if word_idx in start_markers:
                    for marker_idx, _ in start_markers[word_idx]:
                        text_result.append(_HLSTART_TEMPLATE.format(marker_idx))

                # Add the word
                text_result.append(match.group(0))

                # Insert HLEND then ANNMARKER after this word
                # (ANNMARKER after HLEND so annotation appears after highlight ends)
                if word_idx in end_markers:
                    for marker_idx in end_markers[word_idx]:
                        text_result.append(_HLEND_TEMPLATE.format(marker_idx))
                        text_result.append(_MARKER_TEMPLATE.format(marker_idx))

                text_pos = match.end()
                word_idx += 1

            # Add remaining text
            text_result.append(text[text_pos:])
            result.append("".join(text_result))
            i = next_tag

    return "".join(result), marker_to_highlight


def _extract_env_boundaries(latex: str) -> list[tuple[int, int, str]]:
    """Extract environment boundary positions from LaTeX using AST parsing.

    Uses pylatexenc to parse the LaTeX and find all \\begin{...} and \\end{...}
    commands with their exact positions. This is more robust than regex because
    it correctly handles \\begin{env}{args} with arguments.

    Args:
        latex: LaTeX content to parse.

    Returns:
        List of (start_pos, end_pos, boundary_text) tuples, sorted by position.
        boundary_text is the full command (e.g., "\\begin{adjustwidth}{0.94in}{}").
    """
    boundaries: list[tuple[int, int, str]] = []

    try:
        walker = LatexWalker(latex, tolerant_parsing=True)
        nodelist, _, _ = walker.get_latex_nodes(pos=0)
    except Exception:
        # If parsing fails, return empty list - fall back to regex splitting
        return []

    def collect_from_nodes(nodes: list) -> None:
        for node in nodes:
            if isinstance(node, LatexEnvironmentNode):
                env_name = node.environmentname
                begin_pos = node.pos

                # Find where \begin{env}{args...} ends
                # Start with just the \begin{name} part
                begin_end = begin_pos + len(f"\\begin{{{env_name}}}")

                # Check nodeargd for known arguments
                if node.nodeargd and node.nodeargd.argnlist:
                    for arg in node.nodeargd.argnlist:
                        if arg is not None:
                            begin_end = arg.pos + arg.len

                # Check for leading LatexGroupNodes in nodelist (unknown arguments)
                # pylatexenc doesn't know argument specs for all environments,
                # so it puts arguments like {0.5in}{} in nodelist as children
                if node.nodelist:
                    for child in node.nodelist:
                        if isinstance(child, LatexGroupNode):
                            # This GroupNode is likely an argument
                            begin_end = child.pos + child.len
                        else:
                            # First non-GroupNode child - stop looking for args
                            break

                begin_text = latex[begin_pos:begin_end]
                boundaries.append((begin_pos, begin_end, begin_text))

                # \end{env} position: at end of environment node
                env_total_end = node.pos + node.len
                end_text = f"\\end{{{env_name}}}"
                end_start = env_total_end - len(end_text)
                boundaries.append((end_start, env_total_end, end_text))

                # Recurse into environment content
                if node.nodelist:
                    collect_from_nodes(node.nodelist)

            elif isinstance(node, LatexGroupNode) and node.nodelist:
                collect_from_nodes(node.nodelist)

    collect_from_nodes(nodelist)
    boundaries.sort(key=lambda x: x[0])
    return boundaries


def _wrap_content_with_highlight(
    content: str,
    colour_name: str,
    boundaries_in_content: list[tuple[int, int, str]],
) -> str:
    """Wrap content in \\highLight commands, splitting at boundaries.

    Splits content at environment boundaries and inline delimiters (\\par, \\\\, etc.),
    wrapping text segments in \\highLight while keeping delimiters outside.

    Args:
        content: The text content to highlight.
        colour_name: LaTeX colour name for highlighting.
        boundaries_in_content: List of (rel_start, rel_end, text) for env boundaries.

    Returns:
        LaTeX with \\highLight commands wrapping text segments.
    """
    # Split content at environment boundaries first
    if boundaries_in_content:
        boundaries_in_content = sorted(boundaries_in_content, key=lambda x: x[0])
        segments: list[str] = []
        prev_end = 0
        for rel_start, rel_end, boundary_text in boundaries_in_content:
            if rel_start > prev_end:
                segments.append(content[prev_end:rel_start])
            segments.append(boundary_text)  # Keep boundary as delimiter
            prev_end = rel_end
        if prev_end < len(content):
            segments.append(content[prev_end:])
    else:
        segments = [content]

    # Further split each segment on paragraph/table delimiters and wrap in \highLight
    inline_split_pattern = re.compile(r"(\\par\b|\\\\|\\tabularnewline\b|(?<!\\)&)")
    boundary_texts = {text for _, _, text in boundaries_in_content}
    result_parts: list[str] = []

    for seg in segments:
        # Environment boundaries stay outside highlight
        if seg in boundary_texts:
            result_parts.append(seg)
            continue

        # Split on inline delimiters
        for subseg in inline_split_pattern.split(seg):
            if subseg in ("\\par", "\\\\", "\\tabularnewline", "&"):
                result_parts.append(subseg)
            elif subseg.strip():
                result_parts.append(f"\\highLight[{colour_name}]{{{subseg}}}")
            else:
                result_parts.append(subseg)

    return "".join(result_parts)


def _replace_markers_with_annots(
    latex: str,
    marker_highlights: list[dict],
    word_to_legal_para: dict[int, int | None] | None = None,
) -> str:
    """Replace markers in LaTeX with \\annot and \\highLight commands.

    Handles arbitrarily interleaved highlights by:
    1. Tokenizing markers with lark lexer
    2. Building regions with active highlight sets
    3. Generating nested LaTeX for each region using generate_highlighted_latex()

    Args:
        latex: LaTeX content with HLSTART{n}ENDHL, HLEND{n}ENDHL, ANNMARKER{n}ENDMARKER
        marker_highlights: List of highlights in marker order (index = position).
        word_to_legal_para: Optional mapping of word index to legal paragraph number.

    Returns:
        LaTeX with \\highLight and \\underLine commands.
    """
    if not latex:
        return latex

    def build_para_ref(highlight: dict) -> str:
        """Build paragraph reference string for a highlight."""
        if word_to_legal_para is None:
            return ""

        start_word = int(highlight.get("start_word", 0))
        end_word = int(highlight.get("end_word", start_word))
        last_word = end_word - 1 if end_word > start_word else start_word

        start_para = word_to_legal_para.get(start_word)
        end_para = word_to_legal_para.get(last_word)

        if start_para is None and end_para is None:
            return ""
        if start_para is None:
            return f"[{end_para}]"
        if end_para is None or start_para == end_para:
            return f"[{start_para}]"
        # Use en-dash for ranges
        return f"[{start_para}]–[{end_para}]"  # noqa: RUF001

    # Step 1: Tokenize markers using lark lexer
    tokens = tokenize_markers(latex)

    # Step 2: Build regions with active highlight tracking
    regions = build_regions(tokens)

    # Step 3: Convert list to dict and ensure para_refs exist
    # marker_highlights is indexed by position (list), convert to dict[int, dict]
    highlights: dict[int, dict[str, Any]] = {}
    for idx, hl in enumerate(marker_highlights):
        hl_copy = dict(hl)
        # Use stored para_ref if present, otherwise calculate (fallback for old data)
        if not hl_copy.get("para_ref"):
            hl_copy["para_ref"] = build_para_ref(hl)
        highlights[idx] = hl_copy

    # Step 4: Generate LaTeX using the region-based generator
    # env_boundaries parameter kept for API compatibility but not used
    # (inline delimiters are detected per-region in generate_highlighted_latex)
    return generate_highlighted_latex(regions, highlights, [])


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


def convert_html_to_latex(html: str, filter_path: Path | None = None) -> str:
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

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Post-process to fix invalid \newline{} in table contexts
        return _fix_invalid_newlines(result.stdout)
    finally:
        html_path.unlink(missing_ok=True)


def convert_html_with_annotations(
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
        highlights: List of highlight dicts with start_word, end_word, tag, author.
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
    # Fix mid-word font tag splits from LibreOffice RTF export
    html = fix_midword_font_splits(html)

    # Insert markers
    marked_html, marker_highlights = _insert_markers_into_html(html, highlights)

    # Convert to LaTeX
    latex = convert_html_to_latex(marked_html, filter_path=filter_path)

    # Replace markers with annots
    return _replace_markers_with_annots(latex, marker_highlights, word_to_legal_para)
