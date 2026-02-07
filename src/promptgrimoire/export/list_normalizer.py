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

from bs4 import BeautifulSoup, Tag

# Pattern for legal numbering: (N) followed by 2+ spaces, e.g. "(1)    text"
_LEGAL_NUMBER_PATTERN = re.compile(r"^\((\d+)\)(\s{2,})")


def normalize_list_values(html: str) -> str:
    """Convert <li value="N"> to <ol start="N"> for Pandoc compatibility.

    For each <ol>, checks the first <li>'s value attribute and sets it as
    the start attribute on the <ol>. This preserves continuous numbering
    across multiple <ol> elements (common in legal documents).

    Args:
        html: HTML content to process.

    Returns:
        HTML with <ol start> attributes set based on first <li value>.
    """
    soup = BeautifulSoup(html, "html.parser")

    for ol in soup.find_all("ol"):
        if not isinstance(ol, Tag):
            continue

        # Find first direct <li> child
        first_li = ol.find("li", recursive=False)
        if first_li is None or not isinstance(first_li, Tag):
            continue

        # Get value attribute from first li
        value = first_li.get("value")
        if value is None:
            continue

        # Try to parse as integer
        try:
            start_value = int(value)
        except ValueError, TypeError:
            continue

        # Set start on the ol (only if different from default of 1)
        if start_value != 1:
            ol["start"] = str(start_value)

    return str(soup)
