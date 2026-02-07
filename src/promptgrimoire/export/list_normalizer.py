"""Normalize HTML lists for Pandoc compatibility.

Pandoc ignores `value` attributes on `<li>` elements, which breaks continuous
paragraph numbering in legal documents. This preprocessor converts `<li value="N">`
to `<ol start="N">` which Pandoc does support.

Also handles preservation of leading whitespace in legal-style numbered paragraphs
like "(1)    the offender must..." where multiple spaces indicate nesting level.

This is a pre-processor that runs before Pandoc conversion.
"""

from __future__ import annotations

import re


def _add_start(match: re.Match[str]) -> str:
    """Add start attribute to <ol> based on first <li value>."""
    ol_tag = match.group(1)
    li_part = match.group(2)
    value_str = match.group(3)

    try:
        start_value = int(value_str)
    except ValueError, TypeError:
        return match.group(0)

    # Don't add start=1 (it's the default)
    if start_value == 1:
        return match.group(0)

    # Insert start attribute before the closing >
    new_ol = ol_tag.rstrip(">") + f' start="{start_value}">'
    return new_ol + li_part


def normalize_list_values(html: str) -> str:
    """Convert <li value="N"> to <ol start="N"> for Pandoc compatibility.

    For each <ol>, checks the first <li>'s value attribute and sets it as
    the start attribute on the <ol>. This preserves continuous numbering
    across multiple <ol> elements (common in legal documents).

    Uses regex rather than DOM parsing to avoid HTML normalisation side-effects
    (e.g. lexbor inserting <tbody> into <table> elements).

    Args:
        html: HTML content to process.

    Returns:
        HTML with <ol start> attributes set based on first <li value>.
    """
    if "<ol" not in html:
        return html

    # Match <ol...> followed (possibly with whitespace) by <li value="N">
    # Groups: (1) full <ol> tag, (2) whitespace + <li> prefix, (3) value number
    return re.sub(
        r"(<ol[^>]*>)(\s*<li\s+value=[\"'](\d+)[\"'])",
        _add_start,
        html,
    )
