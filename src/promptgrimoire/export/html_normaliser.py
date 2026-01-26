"""HTML normaliser for Pandoc preprocessing.

Wraps styled <p> tags in <div> wrappers so Pandoc preserves the style attributes.
Pandoc's HTML reader converts <p> to Para and discards style attributes, but
preserves attributes on <div> elements when using +native_divs.

Also fixes mid-word font tag splits from LibreOffice RTF export, e.g.:
  "(S</font><font><i>entencing" -> "(<i>Sentencing"
"""

from __future__ import annotations

import re

from lxml import html as lxml_html
from lxml.html import HtmlElement


def _wrap_styled_paragraph(p: HtmlElement) -> HtmlElement:
    """Wrap a single styled <p> element in a <div> with the style.

    Moves the style attribute from the <p> to a new wrapper <div>.

    Args:
        p: A <p> element with a style attribute.

    Returns:
        The wrapper <div> element containing the modified <p>.
    """
    style = p.get("style")

    # Create wrapper div with the style
    wrapper = lxml_html.Element("div")
    wrapper.set("style", style)

    # Remove style from p (other attributes like class, id, lang stay)
    del p.attrib["style"]

    # Copy tail text (whitespace after the element) to wrapper
    wrapper.tail = p.tail
    p.tail = None

    wrapper.append(p)
    return wrapper


def normalise_styled_paragraphs(html_content: str) -> str:
    """Wrap <p style="..."> in <div style="..."> for Pandoc attribute preservation.

    LibreOffice HTML puts CSS styles on <p> tags, but Pandoc discards these
    during HTML-to-AST conversion. By wrapping styled paragraphs in divs,
    the styles are preserved and can be processed by Lua filters.

    Args:
        html_content: HTML string, possibly from LibreOffice export.

    Returns:
        HTML with styled <p> tags wrapped in <div style="..."> elements.
        The style attribute is moved from <p> to the wrapper <div>.
    """
    if not html_content or not html_content.strip():
        return html_content

    # Parse HTML - lxml handles malformed HTML gracefully
    try:
        tree = lxml_html.fromstring(html_content)
    except Exception:
        # If parsing fails, return unchanged
        return html_content

    # Handle case where the root element itself is a styled <p>
    if tree.tag == "p" and tree.get("style"):
        wrapper = _wrap_styled_paragraph(tree)
        return lxml_html.tostring(wrapper, encoding="unicode")

    # Find all <p> elements with style attributes (descendants only now)
    # Use list() to avoid modifying tree during iteration
    styled_paragraphs = list(tree.xpath("//p[@style]"))

    for p in styled_paragraphs:
        if not isinstance(p, HtmlElement):
            continue

        style = p.get("style")
        if not style:
            continue

        parent = p.getparent()
        if parent is None:
            # This shouldn't happen after the root check above, but be safe
            continue

        # Get index of p in parent before removing
        idx = list(parent).index(p)

        # Create wrapper and do the swap
        wrapper = _wrap_styled_paragraph(p)

        # Insert wrapper where p was
        parent.insert(idx, wrapper)

    # Serialize back to HTML string
    result = lxml_html.tostring(tree, encoding="unicode")
    return result


def fix_midword_font_splits(html_content: str) -> str:
    """Fix mid-word font tag splits from LibreOffice RTF export.

    LibreOffice sometimes splits words across font tags, e.g.:
      "(S</font><font color="..."><i>entencing"
    This breaks word boundary detection. We fix by moving the partial
    word fragment inside the next tag.

    Args:
        html_content: HTML string with potential mid-word splits.

    Returns:
        HTML with mid-word font splits merged.
    """
    if not html_content:
        return html_content

    # Pattern: partial word ending before </font>, followed by <font...> or <font...><i>
    # and continuing with letters (no space between)
    # Captures: (partial_word)(</font><font[^>]*>(?:<i>)?)(rest_of_word)
    # Pattern: partial_word</font><font...>rest_of_word (maybe with <i>)
    pattern = re.compile(
        r"(\w+)"  # partial word before closing tag
        r"(</font><font[^>]*>(?:<i>)?)"  # closing + opening font tags
        r"(\w+)"  # rest of word continuing without space
    )

    def merge_word(m: re.Match[str]) -> str:
        # Move partial word inside the new font tag
        partial = m.group(1)
        tags = m.group(2)
        rest = m.group(3)
        return f"{tags}{partial}{rest}"

    return pattern.sub(merge_word, html_content)
