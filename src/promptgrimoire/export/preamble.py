"""LaTeX preamble assembly and escape utilities (P5 functions).

Generates the LuaLaTeX preamble for annotated PDF export, including:
- Tag colour definitions (full, light, dark variants)
- Speaker turn environments
- Annotation counter and margin note macro
- LaTeX special character escaping
- Timestamp formatting

Extracted from latex.py during the module split (Issue #134, Phase 1).
"""

from __future__ import annotations

import re
from datetime import datetime

# Note: Static LaTeX preamble content (packages, commands, environments,
# macros, fonts) is now in promptgrimoire-export.sty. The .sty is copied
# to the output directory by pdf_export._ensure_sty_in_dir().


def generate_tag_colour_definitions(tag_colours: dict[str, str]) -> str:
    """Generate LaTeX \\definecolor commands from tag->colour mapping.

    Generates full-strength, light (30%), and dark (70% black mix) versions
    of each colour. The light versions are used for text highlighting backgrounds,
    and dark versions are used for underlines.

    Args:
        tag_colours: Dict of tag_name -> hex colour (e.g., {"jurisdiction": "#1f77b4"})

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

    The .sty file handles all static content (packages, commands, environments,
    macros, fonts, speaker colours). This function emits only the .sty loading
    and per-document dynamic tag colour definitions.

    Args:
        tag_colours: Dict of tag_name -> hex colour.

    Returns:
        Complete LaTeX preamble string.
    """
    colour_defs = generate_tag_colour_definitions(tag_colours)
    return f"\\usepackage{{promptgrimoire-export}}\n{colour_defs}"


def _format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp to human-readable format (e.g., '26 Jan 2026 14:30')."""
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y %H:%M")
    except ValueError, AttributeError:
        return ""


def _strip_test_uuid(name: str) -> str:
    """Strip test UUID suffix from display names.

    E.g., 'Alice Jones 1664E02D' -> 'Alice Jones'.
    """
    # Match trailing hex UUID (8+ hex chars at end after space)
    return re.sub(r"\s+[A-Fa-f0-9]{6,}$", "", name)
