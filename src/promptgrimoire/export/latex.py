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

import asyncio
import html
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
    LatexCharsNode,
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexWalker,
    get_default_latex_context_db,
)
from pylatexenc.macrospec import MacroSpec

from promptgrimoire.export.html_normaliser import (
    fix_midword_font_splits,
    normalise_styled_paragraphs,
    strip_scripts_and_styles,
)
from promptgrimoire.export.list_normalizer import normalize_list_values
from promptgrimoire.export.unicode_latex import (
    UNICODE_PREAMBLE,
    _strip_control_chars,
    escape_unicode_latex,
)
from promptgrimoire.input_pipeline.html_input import insert_markers_into_dom

logger = logging.getLogger(__name__)


def _escape_html_text_content(html_content: str) -> str:
    """Escape HTML special chars in text content, preserving structural tags.

    This function escapes &, <, >, quotes in text content but leaves the
    structural <p> tags from _plain_text_to_html untouched.
    Used after marker insertion to properly escape text for Pandoc without
    affecting the markers (which are ASCII and don't need escaping).

    Structural tags are identified by data-structural="1" attribute added
    by _plain_text_to_html(escape=False). This prevents false matches where
    user content contains "</p>" text.

    Args:
        html_content: HTML with markers already inserted.

    Returns:
        HTML with text content escaped, structural tags converted to plain <p>.
    """
    if not html_content:
        return html_content

    # Each line from _plain_text_to_html is: <p data-structural="1">content</p>
    # We need to:
    # 1. Match the opening tag with data-structural
    # 2. Find the corresponding closing </p> (the LAST one, as content may have </p>)
    # 3. Escape the content between them

    # Pattern to match a complete paragraph
    para_pattern = re.compile(r'<p data-structural="1">(.*?)</p>(?=\n|$)', re.DOTALL)

    def escape_content(match: re.Match) -> str:
        content = match.group(1)
        return f"<p>{html.escape(content)}</p>"

    # Replace each paragraph, escaping its content
    result = para_pattern.sub(escape_content, html_content)

    # Handle any remaining structural markers (shouldn't happen, but safety)
    result = result.replace('<p data-structural="1">', "<p>")

    return result


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


# ---------------------------------------------------------------------------
# Sectioning macro names where \par is forbidden ("moving arguments")
# ---------------------------------------------------------------------------
_SECTION_MACRO_NAMES = frozenset(
    {"section", "subsection", "subsubsection", "paragraph", "subparagraph"}
)


def walk_and_wrap(
    latex: str,
    highlights: dict[int, dict[str, Any]],
) -> str:
    r"""Replace markers in LaTeX with \highLight, \underLine, and \annot commands.

    Uses pylatexenc to parse the full LaTeX AST and walks it depth-first,
    maintaining a stack of active highlights. At structural boundaries
    (environments, sections, paragraph breaks, blank lines) the active
    highlights are closed and reopened, preventing \par inside lua-ul commands.

    This replaces the tokenize→build_regions→generate_highlighted_latex pipeline
    and the _move_annots_outside_restricted post-processor.

    Args:
        latex: LaTeX content with HLSTART{n}ENDHL, HLEND{n}ENDHL, and
               ANNMARKER{n}ENDMARKER markers from insert_markers_into_dom.
        highlights: Mapping from highlight index to highlight dict with
                   tag, author, created_at, comments, para_ref.

    Returns:
        LaTeX with highlight/underline/annot commands at correct positions.
    """
    if not latex:
        return ""

    # Fast path: no markers at all
    if "HLSTART" not in latex and "ANNMARKER" not in latex:
        return latex

    # Tokenize markers using the existing Lark lexer
    tokens = tokenize_markers(latex)
    regions = build_regions(tokens)

    if not regions:
        return latex

    # Rebuild the full LaTeX from regions, wrapping highlighted text.
    # For each region with active highlights, we need to parse it with
    # pylatexenc to find structural boundaries and split around them.
    #
    # Annots are collected and emitted after the region text. However,
    # if the annot would land inside a restricted context (section argument),
    # it is deferred to _move_annots_outside_restricted().
    result_parts: list[str] = []

    for region in regions:
        if not region.active:
            # No highlights — pass through unchanged
            result_parts.append(region.text)
        else:
            # Wrap the region using AST-aware splitting
            wrapped = _wrap_region_ast(region.text, region.active, highlights)
            result_parts.append(wrapped)

        # Emit annotation commands for this region
        for annot_idx in region.annots:
            if annot_idx in highlights:
                hl = highlights[annot_idx]
                para_ref = hl.get("para_ref", "")
                result_parts.append(_format_annot(hl, para_ref))

    result = "".join(result_parts)

    # Move \annot commands out of restricted contexts (\section{}, etc.)
    return _move_annots_outside_restricted(result)


def _wrap_region_ast(
    content: str,
    active: frozenset[int],
    highlights: dict[int, dict[str, Any]],
) -> str:
    r"""Wrap a highlighted region, splitting at structural boundaries via AST.

    Parses content with pylatexenc and walks the AST. At structural nodes
    (\par, blank lines, environments, sectioning commands), the highlight
    wrapping is closed and reopened around the boundary.

    Args:
        content: LaTeX text of a single region (constant highlight set).
        active: Frozenset of active highlight indices.
        highlights: Full highlight mapping for colour lookup.

    Returns:
        LaTeX with highlight/underline wrapping split at boundaries.
    """
    if not content.strip():
        return content

    underline_wrap = generate_underline_wrapper(active, highlights)
    highlight_wrap = generate_highlight_wrapper(active, highlights)

    # Build a latex context that knows about our custom macros
    latex_context = get_default_latex_context_db()
    latex_context = latex_context.filter_context(keep_categories=["latex-base"])
    latex_context.add_context_category(
        "custom-highlight",
        macros=[
            MacroSpec("highLight", "[{"),
            MacroSpec("underLine", "[{"),
            MacroSpec("annot", "{{"),
            MacroSpec("item", "["),
        ],
    )

    try:
        walker = LatexWalker(
            content, latex_context=latex_context, tolerant_parsing=True
        )
        nodelist, _, _ = walker.get_latex_nodes(pos=0)
    except Exception:
        # Parsing failed — fall back to simple wrapping
        return highlight_wrap(underline_wrap(content))

    # Walk the AST and collect segments
    segments: list[tuple[str, str]] = []
    _walk_nodes(nodelist, content, segments)

    if not segments:
        return highlight_wrap(underline_wrap(content))

    # Wrap each segment: structural boundaries pass through unwrapped,
    # text segments get highlight+underline wrapping.
    result_parts: list[str] = []
    for seg_type, seg_text in segments:
        if seg_type == "boundary" or not seg_text.strip():
            result_parts.append(seg_text)
        else:
            result_parts.append(highlight_wrap(underline_wrap(seg_text)))

    return "".join(result_parts)


def _classify_node(
    node: Any,
    source: str,
    segments: list[tuple[str, str]],
) -> None:
    """Classify a single pylatexenc AST node as 'text' or 'boundary'.

    Args:
        node: A pylatexenc AST node (untyped — pylatexenc v2 has no stubs).
        source: Original LaTeX source string.
        segments: Output list to append to.
    """
    if isinstance(node, LatexCharsNode):
        text = (
            node.chars
            if hasattr(node, "chars")
            else source[node.pos : node.pos + node.len]
        )
        _split_text_at_boundaries(text, segments)
    elif isinstance(node, (LatexEnvironmentNode, LatexGroupNode)):
        node_text = source[node.pos : node.pos + node.len]
        if isinstance(node, LatexEnvironmentNode):
            segments.append(("boundary", node_text))
        else:
            segments.append(("text", node_text))
    elif isinstance(node, LatexMacroNode):
        _classify_macro(node, source, segments)
    elif hasattr(node, "specials_chars"):
        # LatexSpecialsNode — table & separator must be a boundary
        chars = getattr(node, "specials_chars", "")
        p = int(node.pos)
        n = int(node.len)
        node_text = source[p : p + n]
        if chars == "&":
            segments.append(("boundary", node_text))
        else:
            segments.append(("text", node_text))
    elif hasattr(node, "pos") and hasattr(node, "len"):
        p2: int = node.pos
        n2: int = node.len
        segments.append(("text", source[p2 : p2 + n2]))


def _classify_macro(
    node: Any,
    source: str,
    segments: list[tuple[str, str]],
) -> None:
    """Classify a macro node — sectioning/\\par are boundaries, others are text."""
    p: int = node.pos
    n: int = node.len
    node_text = source[p : p + n]
    if node.macroname in _SECTION_MACRO_NAMES | {"par"} or node_text.startswith("\\\\"):
        segments.append(("boundary", node_text))
    else:
        segments.append(("text", node_text))


def _walk_nodes(
    nodes: list,
    source: str,
    segments: list[tuple[str, str]],
) -> None:
    """Walk pylatexenc AST nodes, classifying each as 'text' or 'boundary'.

    Structural boundaries (environments, sectioning commands, \\par, blank lines)
    are emitted as 'boundary' segments. Gaps between nodes (e.g., unmatched
    braces that pylatexenc skips in tolerant mode) are also boundaries.

    Args:
        nodes: List of pylatexenc AST nodes.
        source: Original LaTeX source string (for position-based extraction).
        segments: Output list of (type, text) tuples to append to.
    """
    pos = 0  # Track position to detect gaps
    if nodes and hasattr(nodes[0], "pos"):
        pos = nodes[0].pos  # Start from first node's position

    for node in nodes:
        if node is None or not hasattr(node, "pos") or not hasattr(node, "len"):
            continue

        # Emit any gap between previous node end and this node start
        if node.pos > pos:
            gap_text = source[pos : node.pos]
            if gap_text:
                segments.append(("boundary", gap_text))

        _classify_node(node, source, segments)
        pos = node.pos + node.len

    # Emit any trailing content after the last node
    if nodes:
        total_len = len(source)
        if pos < total_len:
            trailing = source[pos:total_len]
            if trailing:
                segments.append(("boundary", trailing))


def _split_text_at_boundaries(text: str, segments: list[tuple[str, str]]) -> None:
    r"""Split text at \par commands, blank lines, and table separators.

    Table cell separators (``&``) and row terminators (``\\``) must not
    be wrapped inside ``\highLight`` — they are structural LaTeX tokens
    that break when placed inside a group.

    Args:
        text: Raw text from a LatexCharsNode.
        segments: Output list to append (type, text) tuples to.
    """
    # Split at blank lines, explicit \par, table & separators, and \\
    parts = re.split(r"(\n\s*\n|\\par\b|&|\\\\)", text)
    for part in parts:
        if not part:
            continue
        if part.strip() == "" and "\n" in part and part.count("\n") >= 2:
            # Blank line = paragraph break
            segments.append(("boundary", part))
        elif re.match(r"^\\par\b", part) or part in {"&", "\\\\"}:
            segments.append(("boundary", part))
        else:
            segments.append(("text", part))


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

# Character-based tokenization.
# The UI tokenizes by character (including whitespace), so export must match exactly.
# Note: _WORD_PATTERN regex is no longer used - character iteration is inline.

# Base LaTeX preamble for LuaLaTeX with marginalia+lua-ul annotation approach
# Note: The \annot command takes 2 parameters: colour name and margin content.
# It places a superscript number at the insertion point with a coloured margin note.
# Highlighting uses lua-ul's \highLight for robust cross-line-break backgrounds.
# marginalia package auto-stacks overlapping margin notes (requires 2+ lualatex runs).
ANNOTATION_PREAMBLE_BASE = r"""
\usepackage{fontspec}
\setmainfont{TeX Gyre Termes}  % Times New Roman equivalent
\usepackage{amsmath}           % Math extensions (\text{} in math mode)
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
\usepackage[framemethod=tikz]{mdframed}  % For speaker turn borders

% Paragraph formatting for chatbot exports (no indent, paragraph spacing)
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.5\baselineskip}

% Speaker turn environments with left border
\newmdenv[
  topline=false,
  bottomline=false,
  rightline=false,
  linewidth=3pt,
  linecolor=usercolor,
  innerleftmargin=1em,
  innerrightmargin=0pt,
  innertopmargin=0pt,
  innerbottommargin=0pt,
  skipabove=0pt,
  skipbelow=0pt
]{userturn}
\newmdenv[
  topline=false,
  bottomline=false,
  rightline=false,
  linewidth=3pt,
  linecolor=assistantcolor,
  innerleftmargin=1em,
  innerrightmargin=0pt,
  innertopmargin=0pt,
  innerbottommargin=0pt,
  skipabove=0pt,
  skipbelow=0pt
]{assistantturn}

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
    # Speaker colours for chatbot turn distinction
    speaker_colours = r"""
% Speaker colours for chatbot turn markers
\definecolor{usercolor}{HTML}{4A90D9}
\definecolor{assistantcolor}{HTML}{7B68EE}
"""
    return (
        f"\\usepackage{{xcolor}}\n{colour_defs}\n"
        f"{speaker_colours}\n{UNICODE_PREAMBLE}\n{ANNOTATION_PREAMBLE_BASE}"
    )


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
        margin_parts = [f"\\textbf{{{escape_unicode_latex(tag_display)}}} {para_ref}"]
    else:
        margin_parts = [f"\\textbf{{{escape_unicode_latex(tag_display)}}}"]

    # Line 2: name, date (tiny)
    if timestamp:
        margin_parts.append(
            f"\\par{{\\scriptsize {escape_unicode_latex(author)}, {timestamp}}}"
        )
    else:
        margin_parts.append(f"\\par{{\\scriptsize {escape_unicode_latex(author)}}}")

    # Add separator and comments if present
    if comments:
        margin_parts.append("\\par\\hrulefill")
        for comment in comments:
            c_author = _strip_test_uuid(comment.get("author", "Unknown"))
            c_text = comment.get("text", "")
            c_timestamp = _format_timestamp(comment.get("created_at", ""))
            # Comment: name, date: text (all small)
            c_author_esc = escape_unicode_latex(c_author)
            c_text_esc = escape_unicode_latex(c_text)
            if c_timestamp:
                margin_parts.append(
                    f"\\par{{\\scriptsize \\textbf{{{c_author_esc}}}, "
                    f"{c_timestamp}:}} {c_text_esc}"
                )
            else:
                margin_parts.append(
                    f"\\par{{\\scriptsize \\textbf{{{c_author_esc}:}}}} {c_text_esc}"
                )

    margin_content = "".join(margin_parts)

    return f"\\annot{{{colour_name}}}{{{margin_content}}}"


def _insert_markers_into_html(
    html: str, highlights: list[dict]
) -> tuple[str, list[dict]]:
    """Insert annotation and highlight markers into HTML at correct character positions.

    Uses character-by-character iteration to match the UI's character indexing.
    The UI creates character indices by iterating each character (including whitespace),
    so we must match that exactly for highlights to align between UI and export.

    Inserts three types of markers:
    - HLSTART{n} at start_char (before the character)
    - HLEND{n} after end_char (after the last highlighted character)
    - ANNMARKER{n} after HLEND (so \\annot{} with \\par is outside \\highLight{})

    Args:
        html: Raw HTML content.
        highlights: List of highlight dicts with start_char and end_char.

    Returns:
        Tuple of (html with markers, list of highlights in marker order).
    """
    if not highlights:
        return html, []

    # Sort by start_char, then by tag
    # Support both old field names (start_word) and new (start_char) for migration
    sorted_highlights = sorted(
        highlights,
        key=lambda h: (
            h.get("start_char", h.get("start_word", 0)),
            h.get("tag", ""),
        ),
    )

    # Build lookups for marker positions
    # start_markers: char_index -> list of (marker_index, highlight)
    # end_markers: char_index -> list of marker_index for HLEND
    start_markers: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    end_markers: dict[int, list[int]] = defaultdict(list)
    marker_to_highlight: list[dict] = []

    for h in sorted_highlights:
        # Support both old field names (start_word) and new (start_char) for migration
        start = int(h.get("start_char", h.get("start_word", 0)))
        end = int(h.get("end_char", h.get("end_word", start + 1)))
        last_char = end - 1 if end > start else start

        marker_idx = len(marker_to_highlight)
        marker_to_highlight.append(h)
        start_markers[start].append((marker_idx, h))
        end_markers[last_char].append(marker_idx)

    # Process HTML, inserting markers at character positions
    result: list[str] = []
    char_idx = 0
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
            # Text content - iterate characters
            next_tag = html.find("<", i)
            if next_tag == -1:
                next_tag = len(html)

            text = html[i:next_tag]
            text_result: list[str] = []

            for char in text:
                # Newlines aren't indexed by UI (become paragraph breaks)
                if char != "\n":
                    # Insert HLSTART markers before this character
                    for marker_idx, _ in start_markers.get(char_idx, []):
                        text_result.append(_HLSTART_TEMPLATE.format(marker_idx))
                    text_result.append(char)
                    # Insert HLEND then ANNMARKER after this character
                    for marker_idx in end_markers.get(char_idx, []):
                        text_result.append(_HLEND_TEMPLATE.format(marker_idx))
                        text_result.append(_MARKER_TEMPLATE.format(marker_idx))
                    char_idx += 1
                else:
                    text_result.append(char)

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
    r"""Replace markers in LaTeX with \annot and \highLight commands.

    Converts marker_highlights list to dict, builds para_refs, then delegates
    to walk_and_wrap() for AST-aware highlight wrapping.

    Args:
        latex: LaTeX content with HLSTART{n}ENDHL, HLEND{n}ENDHL, ANNMARKER{n}ENDMARKER
        marker_highlights: List of highlights in marker order (index = position).
        word_to_legal_para: Optional mapping of word index to legal paragraph number.

    Returns:
        LaTeX with \highLight and \underLine commands.
    """
    if not latex:
        return latex

    def build_para_ref(highlight: dict) -> str:
        """Build paragraph reference string for a highlight."""
        if word_to_legal_para is None:
            return ""

        # Support both old field names (start_word) and new (start_char) for migration
        # Note: word_to_legal_para mapping still uses character indices
        start_char = int(highlight.get("start_char", highlight.get("start_word", 0)))
        end_char = int(highlight.get("end_char", highlight.get("end_word", start_char)))
        last_char = end_char - 1 if end_char > start_char else start_char

        start_para = word_to_legal_para.get(start_char)
        end_para = word_to_legal_para.get(last_char)

        if start_para is None and end_para is None:
            return ""
        if start_para is None:
            return f"[{end_para}]"
        if end_para is None or start_para == end_para:
            return f"[{start_para}]"
        # Use en-dash for ranges
        return f"[{start_para}]–[{end_para}]"  # noqa: RUF001

    # Convert list to dict and ensure para_refs exist
    # marker_highlights is indexed by position (list), convert to dict[int, dict]
    highlights: dict[int, dict[str, Any]] = {}
    for idx, hl in enumerate(marker_highlights):
        hl_copy = dict(hl)
        # Use stored para_ref if present, otherwise calculate (fallback for old data)
        if not hl_copy.get("para_ref"):
            hl_copy["para_ref"] = build_para_ref(hl)
        highlights[idx] = hl_copy

    return walk_and_wrap(latex, highlights)


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


def _move_annots_outside_restricted(latex: str) -> str:
    r"""Move \annot commands out of any brace group where they're nested.

    The \annot macro uses \marginalia and \parbox which contain \par.
    Since \par is forbidden inside most LaTeX command arguments (any
    non-\long command like \textbf, \emph, \section, etc.), \annot must
    appear at brace depth 0.

    Uses brace-depth tracking — no hardcoded command name list. This
    handles \section{}, \textbf{}, \emph{}, and any future command
    generically.

    Args:
        latex: LaTeX with \annot commands potentially inside brace groups.

    Returns:
        LaTeX with all \annot commands at brace depth 0.
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

            # \annot is nested at depth > 0 — extract and move out
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


def _extract_annot_command(latex: str, pos: int) -> str | None:
    r"""Extract a complete \annot{...}{...} command starting at pos.

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


def _strip_texorpdfstring(latex: str) -> str:
    r"""Strip \texorpdfstring{latex}{pdf} keeping only the LaTeX argument.

    Pandoc generates \texorpdfstring for section headings to provide PDF bookmark
    alternatives. However, luatexja's CJK font context conflicts with hyperref's
    bookmark processing, causing "Missing font identifier" errors.

    Since we disable PDF bookmarks (bookmarks=false), we strip \texorpdfstring
    entirely and keep only the first argument (the LaTeX-formatted text).

    Uses pylatexenc for robust parsing with nested braces.

    Args:
        latex: LaTeX content potentially containing \texorpdfstring commands.

    Returns:
        LaTeX with \texorpdfstring replaced by its first argument.
    """
    # Build a latex context that knows about \texorpdfstring{arg1}{arg2}
    latex_context = get_default_latex_context_db()
    latex_context = latex_context.filter_context(keep_categories=["latex-base"])
    latex_context.add_context_category(
        "pandoc-hyperref",
        macros=[MacroSpec("texorpdfstring", "{{")],  # Two mandatory args
    )

    try:
        walker = LatexWalker(latex, latex_context=latex_context, tolerant_parsing=True)
        nodelist, _, _ = walker.get_latex_nodes(pos=0)
    except Exception:
        # If parsing fails, return unchanged
        return latex

    # Collect positions to replace: (start, end, replacement_text)
    replacements: list[tuple[int, int, str]] = []

    def collect_texorpdfstring(nodes: list) -> None:
        for node in nodes:
            if (
                isinstance(node, LatexMacroNode)
                and node.macroname == "texorpdfstring"
                and node.nodeargd
                and node.nodeargd.argnlist
            ):
                # Get first argument content
                first_arg = node.nodeargd.argnlist[0]
                if first_arg is not None:
                    # Extract the content of first arg (without braces)
                    arg_content = latex[
                        first_arg.pos + 1 : first_arg.pos + first_arg.len - 1
                    ]
                    replacements.append((node.pos, node.pos + node.len, arg_content))
            # Recurse into children
            if (
                isinstance(node, (LatexEnvironmentNode, LatexGroupNode))
                and node.nodelist
            ):
                collect_texorpdfstring(node.nodelist)
            elif isinstance(node, LatexMacroNode) and node.nodeargd:
                for arg in node.nodeargd.argnlist or []:
                    if arg is not None and hasattr(arg, "nodelist") and arg.nodelist:
                        collect_texorpdfstring(arg.nodelist)

    collect_texorpdfstring(nodelist)

    # Apply replacements in reverse order to preserve positions
    result = latex
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]

    return result


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
    # where \par is forbidden — see Issue #132
    return _move_annots_outside_restricted(result)
