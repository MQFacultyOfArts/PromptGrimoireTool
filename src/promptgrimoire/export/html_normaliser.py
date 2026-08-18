"""HTML normaliser for Pandoc preprocessing.

Provides HTML sanitization and normalization for the PDF export pipeline:
- strip_scripts_and_styles: Remove <script>, <style>, and noscript content
- normalise_styled_paragraphs: Wrap styled <p> tags for Pandoc attribute preservation
- fix_midword_font_splits: Fix LibreOffice RTF mid-word font tag splits
- promote_code_block_highlights: Preserve metadata Pandoc drops inside CodeBlock

These functions handle browser copy-paste content which may contain JavaScript,
CSS, and other non-content elements that shouldn't appear in PDFs.
"""

from __future__ import annotations

import re

import structlog
from lxml import html as lxml_html
from lxml.html import HtmlElement

logger = structlog.get_logger()

_CODE_LINES_ATTR = "data-pg-code-lines"
_CODE_COLOR_ATTR = "data-pg-code-color"
_CODE_ANNOTS_ATTR = "data-pg-code-annots"
_CODE_METADATA_ATTRS = (_CODE_LINES_ATTR, _CODE_COLOR_ATTR, _CODE_ANNOTS_ATTR)


_NON_CONTENT_TAGS = ("script", "style", "noscript")


def strip_scripts_and_styles(html_content: str) -> str:
    """Remove script, style, and noscript elements from HTML.

    When users copy-paste from browsers, the HTML may include:
    - <script> tags with JavaScript code
    - <style> tags with CSS
    - <noscript> fallback content
    - Inline event handlers (onclick, etc.)

    This function removes these non-content elements before PDF export.

    Args:
        html_content: HTML string, potentially from browser copy-paste.

    Returns:
        HTML with script/style elements and their content removed.
    """
    if not html_content or not html_content.strip():
        return html_content

    try:
        # Parse HTML - lxml handles malformed HTML gracefully
        tree = lxml_html.fromstring(html_content)
    except Exception:
        # If parsing fails completely, try regex fallback
        logger.warning(
            "html_parse_failed_fallback_regex", operation="strip_scripts_and_styles"
        )
        return _strip_scripts_regex_fallback(html_content)

    _remove_non_content_elements(tree)
    _strip_event_handler_attributes(tree)

    return lxml_html.tostring(tree, encoding="unicode")


def _remove_non_content_elements(tree: HtmlElement) -> None:
    """Remove script/style/noscript elements from *tree*, preserving tail text."""
    for tag in _NON_CONTENT_TAGS:
        for element in tree.xpath(f"//{tag}"):
            _remove_element_preserving_tail(element)


def _remove_element_preserving_tail(element: HtmlElement) -> None:
    """Detach *element* from its parent, reattaching any tail text.

    Tail text (text after the element, before the next sibling) would
    otherwise be lost along with the element. It is appended to the
    previous sibling's tail, or to the parent's own text if there is no
    previous sibling.
    """
    parent = element.getparent()
    if parent is None:
        return
    if element.tail:
        prev = element.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + element.tail
        else:
            parent.text = (parent.text or "") + element.tail
    parent.remove(element)


def _strip_event_handler_attributes(tree: HtmlElement) -> None:
    """Remove inline event-handler attributes (onclick, onload, etc.) from *tree*."""
    for element in tree.iter():
        if not hasattr(element, "attrib"):
            continue
        attrs_to_remove = [
            attr for attr in element.attrib if attr.lower().startswith("on")
        ]
        for attr in attrs_to_remove:
            del element.attrib[attr]


def _strip_scripts_regex_fallback(html_content: str) -> str:
    """Regex fallback for stripping scripts when lxml parsing fails.

    Less robust than DOM-based stripping but handles severely malformed HTML.
    """
    # Remove script tags and content
    html_content = re.sub(
        r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE
    )
    # Remove style tags and content
    html_content = re.sub(
        r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE
    )
    # Remove noscript tags and content
    html_content = re.sub(
        r"<noscript[^>]*>.*?</noscript>",
        "",
        html_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return html_content


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
        logger.warning("html_parse_failed", operation="normalise_styled_paragraphs")
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


def _highlighted_line_numbers(
    pre: HtmlElement,
) -> tuple[set[int], list[str], list[str]]:
    """Collect highlighted code lines, colours, and annotations from *pre*."""
    line_number = 1
    lines: set[int] = set()
    colours: list[str] = []
    annotations: list[str] = []

    def record_text(text: str | None, *, highlighted: bool) -> None:
        nonlocal line_number
        if not text:
            return
        for character in text:
            if character == "\n":
                line_number += 1
            elif highlighted and character != "\r":
                lines.add(line_number)

    def walk(element: HtmlElement, *, highlighted: bool = False) -> None:
        is_highlight = element.tag == "span" and element.get("data-hl") is not None
        active = highlighted or is_highlight

        if is_highlight:
            for colour in (element.get("data-colors") or "").split(","):
                if colour and colour not in colours:
                    colours.append(colour)
            annotation = element.get("data-annots")
            if annotation:
                annotations.append(annotation)

        record_text(element.text, highlighted=active)
        for child in element:
            if not isinstance(child, HtmlElement):
                continue
            walk(child, highlighted=active)
            record_text(child.tail, highlighted=active)

    walk(pre)
    return lines, colours, annotations


def promote_code_block_highlights(html_content: str) -> str:
    """Move annotated-code metadata onto ``pre`` before Pandoc flattens it.

    Pandoc represents ``<pre><code>`` as a single ``CodeBlock`` and discards
    descendant spans.  The block attributes survive, so this pass records the
    selected line numbers, display colour, and annotation commands there for
    the Lua filter.  Unannotated code blocks are returned unchanged.
    """
    if not html_content:
        return html_content
    if "data-hl" not in html_content and not any(
        attribute in html_content for attribute in _CODE_METADATA_ATTRS
    ):
        return html_content

    try:
        tree = lxml_html.fromstring(html_content)
    except Exception:
        logger.warning("html_parse_failed", operation="promote_code_block_highlights")
        return html_content

    # These attributes are an internal Python→Lua channel.  Remove any
    # source-provided values before deriving them from computed highlight spans.
    for element in tree.xpath("descendant-or-self::*"):
        if not isinstance(element, HtmlElement):
            continue
        for attribute in _CODE_METADATA_ATTRS:
            element.attrib.pop(attribute, None)

    code_blocks = tree.xpath("descendant-or-self::pre[.//span[@data-hl]]")
    for pre in code_blocks:
        if not isinstance(pre, HtmlElement):
            continue
        lines, colours, annotations = _highlighted_line_numbers(pre)
        if lines:
            pre.set(_CODE_LINES_ATTR, ",".join(str(line) for line in sorted(lines)))
        if colours:
            pre.set(_CODE_COLOR_ATTR, colours[0])
        if annotations:
            pre.set(_CODE_ANNOTS_ATTR, "".join(annotations))

    return lxml_html.tostring(tree, encoding="unicode")


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
