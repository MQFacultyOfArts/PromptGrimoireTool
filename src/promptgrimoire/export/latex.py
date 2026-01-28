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

import re
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

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
    current_annots: list[int] = []

    def flush_region() -> None:
        """Emit current region if there's accumulated text."""
        nonlocal current_text, current_annots
        if current_text:
            regions.append(
                Region(
                    text=current_text,
                    active=frozenset(active),
                    annots=current_annots,
                )
            )
            current_text = ""
            current_annots = []

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
            current_annots.append(token.index)

    # Flush any remaining text
    flush_region()

    return regions


# Lark grammar for marker tokenization
# Literals have higher priority than regex, so markers match first
# TEXT catches everything else with negative lookahead
#
# Note: TEXT uses a full-marker lookahead (not just prefix) so incomplete
# marker-like text (e.g., "HLSTART{123 ") is correctly treated as TEXT.
_MARKER_GRAMMAR = (
    'HLSTART: "HLSTART{" /[0-9]+/ "}ENDHL"\n'
    'HLEND: "HLEND{" /[0-9]+/ "}ENDHL"\n'
    'ANNMARKER: "ANNMARKER{" /[0-9]+/ "}ENDMARKER"\n'
    r"TEXT: /(?:(?!"
    r"HLSTART\{[0-9]+\}ENDHL|"
    r"HLEND\{[0-9]+\}ENDHL|"
    r"ANNMARKER\{[0-9]+\}ENDMARKER"
    r").)+/s"
)

# Compile once at module load
_marker_lexer = Lark(_MARKER_GRAMMAR, parser=None, lexer="basic")

# Regex to extract index from marker value
_INDEX_EXTRACT_PATTERN = re.compile(r"\{(\d+)\}")


def tokenize_markers(latex: str) -> list[MarkerToken]:
    """Tokenize LaTeX text containing highlight markers.

    Converts a string containing HLSTART{n}ENDHL, HLEND{n}ENDHL, and
    ANNMARKER{n}ENDMARKER markers into a list of MarkerToken objects.
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

# Base LaTeX preamble for LuaLaTeX with marginnote+lua-ul annotation approach
# Note: The \annot command takes 2 parameters: colour name and margin content.
# It places a superscript number at the insertion point with a coloured margin note.
# Highlighting uses lua-ul's \highLight for robust cross-line-break backgrounds.
ANNOTATION_PREAMBLE_BASE = r"""
\usepackage{fontspec}
\setmainfont{TeX Gyre Termes}  % Times New Roman equivalent
\usepackage{microtype}         % Better typography (kerning, protrusion)
\usepackage{marginnote}
\usepackage{longtable}
\usepackage{booktabs}
\usepackage{array}
\usepackage{calc}
\usepackage{hyperref}
\usepackage{changepage}
\usepackage{luacolor}  % Required by lua-ul for coloured highlights
\usepackage{lua-ul}    % LuaLaTeX highlighting (robust across line breaks)
\usepackage[a4paper,left=2.5cm,right=6cm,top=2.5cm,bottom=2.5cm]{geometry}

% Annotation counter and macro
% Usage: \annot{colour-name}{margin content}
% Uses footnotesize for compact margin notes
\newcounter{annotnum}
\newcommand{\annot}[2]{%
  \stepcounter{annotnum}%
  \textsuperscript{\textcolor{#1}{\textbf{\theannotnum}}}%
  \marginnote{%
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

                # Insert END markers after this word (HLEND then ANNMARKER)
                # ANNMARKER AFTER HLEND so \annot{} (with \par) is outside \highLight{}
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

    Uses lua-ul's \\highLight[color]{text} for highlighting.
    The marker structure is: HLSTART{n}ANNMARKER{n}...text...HLEND{n}

    Processing order:
    1. Replace ANNMARKER{n} with \\annot commands
    2. Wrap HLSTART{n}...HLEND{n} spans with \\highLight[color]{...}

    Args:
        latex: LaTeX content with markers.
        marker_highlights: List of highlights in marker order.
        word_to_legal_para: Optional mapping of word index to legal paragraph number.

    Returns:
        LaTeX with markers replaced by commands.
    """

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

    def annot_replacer(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if idx < len(marker_highlights):
            highlight = marker_highlights[idx]
            para_ref = build_para_ref(highlight)
            return _format_annot(highlight, para_ref)
        return ""

    # Step 1: Replace ANNMARKER{n} with \annot commands
    result = _MARKER_PATTERN.sub(annot_replacer, latex)

    # Step 2: Extract environment boundaries for splitting highlights
    # This must happen AFTER annot replacement so positions are correct
    env_boundaries = _extract_env_boundaries(result)

    # Step 3: Wrap HLSTART{n}...HLEND{n} with \highLight[color]{...}
    # Pattern captures: HLSTART{index}...content...HLEND{index}
    # Using non-greedy match and backreference to match paired markers
    def highlight_wrapper(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        content = match.group(2)
        if idx >= len(marker_highlights):
            return content

        highlight = marker_highlights[idx]
        tag = highlight.get("tag", "jurisdiction")
        colour_name = f"tag-{tag.replace('_', '-')}-light"

        # Calculate absolute position of content in the string
        marker_prefix = f"HLSTART{idx}ENDHL"
        marker_suffix = f"HLEND{idx}ENDHL"
        content_start = match.start() + len(marker_prefix)
        content_end = match.end() - len(marker_suffix)

        # Find environment boundaries within this content span
        boundaries_in_content = [
            (abs_start - content_start, abs_end - content_start, text)
            for abs_start, abs_end, text in env_boundaries
            if content_start < abs_start < content_end
        ]

        return _wrap_content_with_highlight(content, colour_name, boundaries_in_content)

    # Match HLSTART{n}...HLEND{n} with same index (backreference)
    highlight_pattern = re.compile(r"HLSTART(\d+)ENDHL(.*?)HLEND\1ENDHL", re.DOTALL)
    result = highlight_pattern.sub(highlight_wrapper, result)

    return result


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
    # Preprocess HTML to wrap styled <p> tags for Pandoc attribute preservation
    normalised_html = normalise_styled_paragraphs(html)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False
    ) as html_file:
        html_file.write(normalised_html)
        html_path = Path(html_file.name)

    try:
        # Use +native_divs to preserve div attributes in Pandoc AST
        cmd = ["pandoc", "-f", "html+native_divs", "-t", "latex", str(html_path)]
        if filter_path is not None:
            cmd.extend(["--lua-filter", str(filter_path)])

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
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
    # Fix mid-word font tag splits from LibreOffice RTF export
    html = fix_midword_font_splits(html)

    # Insert markers
    marked_html, marker_highlights = _insert_markers_into_html(html, highlights)

    # Convert to LaTeX
    latex = convert_html_to_latex(marked_html, filter_path=filter_path)

    # Replace markers with annots
    return _replace_markers_with_annots(latex, marker_highlights, word_to_legal_para)
