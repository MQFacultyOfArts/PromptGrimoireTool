"""CSS styles and tag toolbar for the annotation page.

Contains the page CSS constant, highlight pseudo-element generation,
page style setup, and tag toolbar builder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nicegui import ui

if TYPE_CHECKING:
    from promptgrimoire.pages.annotation.tags import TagInfo

# CSS styles for annotation interface
_PAGE_CSS = """
    /* Document container */
    .doc-container {
        font-family: "Times New Roman", Times, serif;
        font-size: 12pt;
        line-height: 1.6 !important;
        padding: 1rem;
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        /* Allow horizontal scroll for wide content (tables) */
        overflow-x: auto;
    }

    /* Tables: proper table layout, container handles overflow */
    .doc-container table {
        border-collapse: collapse;
        margin: 1em 0;
    }
    .doc-container td,
    .doc-container th {
        vertical-align: top;
        padding: 4px 8px;
        /* Allow text to wrap in cells */
        word-wrap: break-word;
        overflow-wrap: break-word;
    }

    /* Lists: ensure proper rendering */
    .doc-container ol,
    .doc-container ul {
        margin: 0.5em 0;
        padding-left: 2em;
    }
    .doc-container ol {
        list-style-type: decimal;
    }
    .doc-container ul {
        list-style-type: disc;
    }
    .doc-container li {
        margin: 0.25em 0;
        display: list-item;
    }

    /* Paragraphs */
    .doc-container p {
        margin: 0.5em 0;
    }

    /* Normalize headings - prevent oversized inherited styles */
    .doc-container h1 {
        font-size: 1.5em;
        font-weight: bold;
        margin: 1em 0 0.5em 0;
    }
    .doc-container h2 {
        font-size: 1.3em;
        font-weight: bold;
        margin: 0.8em 0 0.4em 0;
    }
    .doc-container h3 {
        font-size: 1.15em;
        font-weight: bold;
        margin: 0.6em 0 0.3em 0;
    }
    .doc-container h4,
    .doc-container h5,
    .doc-container h6 {
        font-size: 1em;
        font-weight: bold;
        margin: 0.5em 0 0.25em 0;
    }

    /* Blockquotes */
    .doc-container blockquote {
        border-left: 3px solid #ccc;
        padding-left: 1em;
        margin: 1em 0 1em 0.5em;
        color: #444;
    }

    /* Preformatted/code blocks */
    .doc-container pre {
        background: #f5f5f5;
        border: 1px solid #ddd;
        border-radius: 3px;
        padding: 0.8em;
        overflow-x: auto;
        white-space: pre;
        font-family: "Courier New", Courier, monospace;
        font-size: 0.9em;
        line-height: 1.4 !important;
    }
    .doc-container code {
        font-family: "Courier New", Courier, monospace;
        font-size: 0.9em;
    }

    /* Speaker turn markers for chatbot exports (data-speaker attribute) */
    .doc-container [data-speaker] {
        display: block;
        margin-top: 1.5em;
        margin-bottom: 0.5em;
    }
    .doc-container [data-speaker="user"]::before {
        content: "User:";
        display: inline-block;
        color: #1a5f7a;
        background: #e3f2fd;
        padding: 2px 8px;
        border-radius: 3px;
        font-weight: bold;
        margin-bottom: 0.3em;
    }
    .doc-container [data-speaker="assistant"]::before {
        content: "Assistant:";
        display: inline-block;
        color: #2e7d32;
        background: #e8f5e9;
        padding: 2px 8px;
        border-radius: 3px;
        font-weight: bold;
        margin-bottom: 0.3em;
    }

    /* Thinking block indicators (Claude thinking) */
    .doc-container [data-thinking] {
        color: #888;
        font-style: italic;
        font-size: 0.9em;
    }

    /* Plain text documents use monospace */
    .doc-container.source-text {
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
            "Liberation Mono", monospace;
        font-size: 11pt;
        white-space: pre-wrap;
    }

    /* Compact tag toolbar in header */
    .tag-toolbar-compact {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        justify-content: center;
    }

    /* Compact buttons */
    .compact-btn {
        padding: 2px 8px !important;
        min-height: 24px !important;
        font-size: 11px !important;
    }

    /* Annotation sidebar - relative container for positioned cards */
    .annotations-sidebar {
        position: relative !important;
        min-height: 100%;
    }

    /* Annotation cards - absolutely positioned within sidebar */
    .ann-card-positioned {
        left: 0;
        right: 0;
        border-radius: 4px;
        padding: 8px 12px;
        margin-bottom: 8px;
        cursor: pointer;
        transition: top 0.15s ease-out, box-shadow 0.2s;
    }
    .ann-card-positioned:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }

    /* Remote cursor indicators */
    .remote-cursor {
        position: absolute;
        width: 2px;
        pointer-events: none;
        z-index: 20;
        transition: left 0.15s ease, top 0.15s ease;
    }
    .remote-cursor-label {
        position: absolute;
        top: -1.4em;
        left: -2px;
        font-size: 0.6rem;
        color: white;
        padding: 1px 4px;
        border-radius: 2px;
        white-space: nowrap;
        pointer-events: none;
        opacity: 0.9;
    }

"""


def _build_highlight_pseudo_css(tag_colours: dict[str, str]) -> str:
    """Generate ::highlight() pseudo-element CSS rules for annotation tags.

    Uses the CSS Custom Highlight API: each tag gets a ``::highlight(hl-<tag>)``
    rule with a semi-transparent background and underline in the tag's colour.
    The JS ``applyHighlights()`` function registers the actual highlight ranges
    in ``CSS.highlights``; this CSS just defines the visual style.

    Note: ``::highlight()`` supports only ``background-color``, ``color``,
    ``text-decoration``, and ``text-shadow``. Properties like
    ``text-decoration-thickness`` and ``text-underline-offset`` are NOT
    supported inside ``::highlight()`` rules.

    Args:
        tag_colours: Mapping of tag key to hex colour string.

    Returns:
        CSS string with ``::highlight()`` rules.
    """
    css_rules: list[str] = []
    for tag_str, hex_color in tag_colours.items():
        r, g, b = (
            int(hex_color[1:3], 16),
            int(hex_color[3:5], 16),
            int(hex_color[5:7], 16),
        )
        bg_rgba = f"rgba({r}, {g}, {b}, 0.4)"
        css_rules.append(
            f"::highlight(hl-{tag_str}) {{\n"
            f"    background-color: {bg_rgba};\n"
            f"    text-decoration: underline;\n"
            f"    text-decoration-color: {hex_color};\n"
            f"}}"
        )

    # Hover and throb highlights for card interaction (Phase 4)
    css_rules.append(
        "::highlight(hl-hover) {\n    background-color: rgba(255, 215, 0, 0.3);\n}"
    )
    css_rules.append(
        "::highlight(hl-throb) {\n    background-color: rgba(255, 215, 0, 0.6);\n}"
    )

    return "\n".join(css_rules)


def _setup_page_styles() -> None:
    """Add page CSS styles."""
    ui.add_css(_PAGE_CSS)


def _build_tag_toolbar(
    tag_info_list: list[TagInfo],
    on_tag_click: Any,
) -> Any:
    """Build fixed tag toolbar from DB-backed tag list.

    Uses a div with fixed positioning for floating toolbar behavior.

    Args:
        tag_info_list: List of TagInfo instances to render as buttons.
        on_tag_click: Async callback receiving a tag key string.

    Returns:
        The toolbar row element.
    """
    toolbar_wrapper = (
        ui.element("div")
        .classes("bg-gray-100 py-2 px-4")
        .style(
            "position: fixed; top: 0; left: 0; right: 0; z-index: 100; "
            "box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
        )
    )
    with (
        toolbar_wrapper,
        ui.row()
        .classes("tag-toolbar-compact w-full")
        .props('data-testid="tag-toolbar"'),
    ):
        for i, ti in enumerate(tag_info_list):
            shortcut = str((i + 1) % 10) if i < 10 else ""
            label = f"[{shortcut}] {ti.name}" if shortcut else ti.name

            async def apply_tag(tag_key: str = ti.raw_key) -> None:
                await on_tag_click(tag_key)

            btn = ui.button(label, on_click=apply_tag).classes("text-xs compact-btn")
            btn.style(
                f"background-color: {ti.colour}; color: white; max-width: 160px; "
                "overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
            )
            btn.tooltip(ti.name)
    return toolbar_wrapper
