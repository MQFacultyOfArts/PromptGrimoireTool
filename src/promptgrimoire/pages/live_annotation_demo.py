"""Live annotation demo page.

Demonstrates real-time collaborative text annotation using pycrdt CRDTs.
Features word-level CSS highlighting, live cursor/selection sharing,
and comment threading.

Route: /demo/live-annotation
"""

from __future__ import annotations

import contextlib
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nicegui import app, ui

from promptgrimoire.crdt import AnnotationDocumentRegistry
from promptgrimoire.models import TAG_COLORS, TAG_SHORTCUTS, BriefTag
from promptgrimoire.parsers import parse_rtf

if TYPE_CHECKING:
    from nicegui.events import GenericEventArguments

# Path to fixtures for demo
_FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures"

# Path to assets directory and register static files route
_ASSETS_DIR = Path(__file__).parent.parent / "assets"

# Guard against duplicate registration during hot reload
with contextlib.suppress(ValueError):
    app.add_static_files("/assets", _ASSETS_DIR)

# Global registry for annotation documents
_doc_registry = AnnotationDocumentRegistry()

# Track connected clients per document for broadcasting
# doc_id -> {client_id -> ClientState}
_connected_clients: dict[str, dict[str, ClientState]] = {}


class ClientState:
    """State for a connected client."""

    def __init__(
        self,
        callback: Any,
        color: str,
        name: str,
    ) -> None:
        self.callback = callback
        self.color = color
        self.name = name
        self.selection_start: int | None = None
        self.selection_end: int | None = None
        self.cursor_word: int | None = None

    def set_selection(self, start: int | None, end: int | None) -> None:
        """Update selection range."""
        self.selection_start = start
        self.selection_end = end

    def set_cursor(self, word_index: int | None) -> None:
        """Update cursor position."""
        self.cursor_word = word_index

    def clear_selection(self) -> None:
        """Clear selection."""
        self.selection_start = None
        self.selection_end = None

    def to_selection_dict(self) -> dict[str, Any]:
        """Get selection as dict for CSS generation."""
        return {
            "start_word": self.selection_start,
            "end_word": self.selection_end,
            "name": self.name,
            "color": self.color,
        }

    def to_cursor_dict(self) -> dict[str, Any]:
        """Get cursor as dict for CSS generation."""
        return {
            "word": self.cursor_word,
            "name": self.name,
            "color": self.color,
        }


# Tailwind layer CSS - must use type="text/tailwindcss" via add_head_html
# This overrides Tailwind's preflight reset for lists
_TAILWIND_OVERRIDES = """
<style type="text/tailwindcss">
    .doc-container ol {
        list-style-type: decimal;
        padding-left: 2.5em;
        margin-bottom: 1em;
    }
    .doc-container ol li {
        display: list-item;
    }
    .doc-container ul {
        list-style-type: disc;
        padding-left: 2.5em;
    }
    .doc-container ul li {
        display: list-item;
    }
</style>
"""

# CSS styles for the demo page
_PAGE_CSS = """
    /* Document container - full width now */
    .doc-container {
        font-family: "Times New Roman", Times, serif;
        font-size: 12pt;
        line-height: 1.6;
        padding: 1rem;
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        max-width: 800px;
        margin: 0 auto;
    }

    /* Word spans */
    .w {
        cursor: text;
        transition: background-color 0.1s;
    }

    /* Selection overlay for other users */
    .selection-other {
        background-color: var(--sel-color, #ffeb3b40) !important;
        outline: 2px solid var(--sel-color, #ffeb3b);
    }

    /* Cursor indicator for other users - uses box-shadow to avoid layout shift */
    .cursor-other::after {
        content: attr(data-cursor-name);
        position: absolute;
        top: -1.2em;
        left: 0;
        font-size: 0.7rem;
        background: var(--cursor-color, #2196f3);
        color: white;
        padding: 1px 4px;
        border-radius: 2px;
        white-space: nowrap;
        pointer-events: none;
    }
    .cursor-other {
        position: relative;
        /* Use inset box-shadow instead of border to avoid displacing text */
        box-shadow: inset 2px 0 0 0 var(--cursor-color, #2196f3);
    }

    /* Annotation card */
    .ann-card {
        border-radius: 4px;
        padding: 8px 12px;
        margin-bottom: 8px;
        cursor: pointer;
        transition: box-shadow 0.2s;
    }
    .ann-card:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
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

    /* Floating tag menu */
    .floating-menu {
        position: fixed;
        background: white;
        border: 1px solid #ccc;
        border-radius: 8px;
        padding: 0.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 1000;
        display: none;
    }
    .floating-menu.visible {
        display: block;
    }

    /* Annotation sidebar - relative container for absolute cards */
    .annotations-sidebar {
        position: relative !important;
        min-height: 100%;
    }

    /* Annotation cards - absolutely positioned within sidebar */
    .ann-card-positioned {
        left: 0;
        right: 0;
        transition: top 0.15s ease-out;
    }
"""

# Quasar override CSS - @layer quasar_importants to beat Quasar's !important
# Note: This doesn't actually work - we use JS inline styles instead
_QUASAR_OVERRIDES = """
    @layer quasar_importants {
        .ann-card-positioned {
            position: absolute !important;
        }
    }
"""


def _get_username() -> str:
    """Get display name for current user."""
    adjectives = ["Happy", "Clever", "Swift", "Bright", "Calm"]
    nouns = ["Panda", "Eagle", "Tiger", "Dolphin", "Fox"]
    return f"{random.choice(adjectives)}{random.choice(nouns)}"


class _WordSpanProcessor:
    """Stateful processor for wrapping HTML text nodes in word spans."""

    # Tags that start a new paragraph for word-to-para mapping
    _PARA_TAGS = frozenset(("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"))
    # Regex patterns
    _ENTITY_PATTERN = re.compile(r"&[a-zA-Z]+;|&#\d+;|&#x[0-9a-fA-F]+;")
    _WORD_PATTERN = re.compile(r'["\'\(\[]*[\w\'\-]+[.,;:!?"\'\)\]]*')
    _TAG_NAME_PATTERN = re.compile(r"<(\w+)")
    _CLOSING_TAG_PATTERN = re.compile(r"</(\w+)")
    _PUA_PATTERN = re.compile(r"[\ue000-\uf8ff]")

    def __init__(self) -> None:
        self.words: list[str] = []
        self.word_to_para: dict[int, int] = {}
        self.para_word_ranges: dict[int, tuple[int, int]] = {}  # para -> (start, end)
        self._para_index = 0
        self._word_index = 0
        self._para_start_word: int | None = None

    def _wrap_text(self, text: str) -> str:
        """Wrap words in spans, preserving HTML entities via PUA placeholders."""
        entities: list[str] = []

        def save_entity(m: re.Match) -> str:
            idx = len(entities)
            entities.append(m.group(0))
            return chr(0xE000 + idx)  # Unicode Private Use Area

        def replace_word(m: re.Match) -> str:
            word = m.group(0)
            self.words.append(word)
            self.word_to_para[self._word_index] = self._para_index
            # Track first word of this paragraph
            if self._para_start_word is None:
                self._para_start_word = self._word_index
            result = f'<span class="w" data-w="{self._word_index}">{word}</span>'
            self._word_index += 1
            return result

        def restore_entity(m: re.Match) -> str:
            return entities[ord(m.group(0)) - 0xE000]

        protected = self._ENTITY_PATTERN.sub(save_entity, text)
        wrapped = self._WORD_PATTERN.sub(replace_word, protected)
        return self._PUA_PATTERN.sub(restore_entity, wrapped)

    def _finalize_paragraph(self) -> None:
        """Record word range for the current paragraph."""
        if self._para_start_word is not None:
            self.para_word_ranges[self._para_index] = (
                self._para_start_word,
                self._word_index,
            )
            self._para_start_word = None

    def process(self, html: str) -> str:
        """Process HTML content, wrapping text nodes in word spans."""
        # Extract body content if full HTML document
        body_match = re.search(
            r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE
        )
        if body_match:
            html = body_match.group(1)

        result: list[str] = []
        i = 0
        while i < len(html):
            if html[i] == "<":
                tag_end = html.find(">", i)
                if tag_end == -1:
                    result.append(html[i:])
                    break
                tag = html[i : tag_end + 1]
                result.append(tag)

                # Check for closing tags - finalize paragraph
                close_match = self._CLOSING_TAG_PATTERN.match(tag)
                if close_match and close_match.group(1).lower() in self._PARA_TAGS:
                    self._finalize_paragraph()

                # Check for opening tags - increment paragraph index
                tag_match = self._TAG_NAME_PATTERN.match(tag)
                if (
                    tag_match
                    and tag_match.group(1).lower() in self._PARA_TAGS
                    and not tag.startswith("</")
                ):
                    self._para_index += 1

                i = tag_end + 1
            else:
                next_tag = html.find("<", i)
                if next_tag == -1:
                    result.append(self._wrap_text(html[i:]))
                    break
                result.append(self._wrap_text(html[i:next_tag]))
                i = next_tag

        # Finalize any remaining paragraph
        self._finalize_paragraph()
        return "".join(result)


class _ProcessedDocument:
    """Result of processing HTML into word spans."""

    def __init__(
        self,
        html: str,
        words: list[str],
        word_to_para: dict[int, int],
        para_word_ranges: dict[int, tuple[int, int]],
    ) -> None:
        self.html = html
        self.words = words
        self.word_to_para = word_to_para
        self.para_word_ranges = para_word_ranges  # para_idx -> (start_word, end_word)


def _html_to_word_spans(html: str) -> _ProcessedDocument:
    """Convert HTML content to word-wrapped spans for CSS-based highlighting.

    Args:
        html: Raw HTML from RTF conversion.

    Returns:
        ProcessedDocument with HTML, words, and paragraph mappings.
    """
    processor = _WordSpanProcessor()
    processed_html = processor.process(html)
    return _ProcessedDocument(
        html=processed_html,
        words=processor.words,
        word_to_para=processor.word_to_para,
        para_word_ranges=processor.para_word_ranges,
    )


def _build_highlight_css(
    highlights: list[dict], tag_colors: dict[BriefTag, str]
) -> str:
    """Build CSS rules for highlighting word spans.

    Args:
        highlights: List of highlight dicts with start_word, end_word, tag.
        tag_colors: Mapping of BriefTag to color hex.

    Returns:
        CSS string with highlight rules.
    """
    rules = []
    for h in highlights:
        # Convert to int (pycrdt may store as float)
        start = int(h.get("start_word", 0))
        end = int(h.get("end_word", 0))
        tag = h.get("tag", "")
        color = tag_colors.get(BriefTag(tag), "#ffff00") if tag else "#ffff00"

        # Create selector for all words in range
        # Use box-shadow to extend highlight into trailing whitespace
        selectors = [f'[data-w="{i}"]' for i in range(start, end)]
        if selectors:
            selector_str = ", ".join(selectors)
            # box-shadow extends the background color to cover the space after each word
            rules.append(
                f"{selector_str} {{ "
                f"background-color: {color}40; "
                f"box-shadow: 0.3em 0 0 {color}40; "
                f"}}"
            )
            # Last word shouldn't extend into next content
            rules.append(f'[data-w="{end - 1}"] {{ box-shadow: none; }}')

    return "\n".join(rules)


def _build_remote_cursor_css(
    cursors: dict[str, dict[str, Any]], exclude_client_id: str
) -> str:
    """Build CSS rules for remote users' cursors.

    Args:
        cursors: Dict of client_id -> {word, name, color}.
        exclude_client_id: Current client to exclude from CSS.

    Returns:
        CSS string with cursor indicator rules.
    """
    rules = []
    for cid, cursor in cursors.items():
        if cid == exclude_client_id:
            continue
        word = cursor.get("word")
        color = cursor.get("color", "#2196f3")
        name = cursor.get("name", "User")

        if word is None:
            continue

        # Style for cursor position - use box-shadow to avoid layout shift
        # The cursor indicator floats above the document without affecting layout
        rules.append(
            f'[data-w="{word}"] {{ '
            f"position: relative; "
            f"box-shadow: inset 2px 0 0 0 {color}; "
            f"}}"
        )

        # Add floating name label using ::before pseudo-element
        rules.append(
            f'[data-w="{word}"]::before {{ '
            f'content: "{name}"; '
            f"position: absolute; "
            f"top: -1.2em; left: 0; "
            f"font-size: 0.6rem; "
            f"background: {color}; "
            f"color: white; "
            f"padding: 1px 3px; "
            f"border-radius: 2px; "
            f"white-space: nowrap; "
            f"z-index: 20; "
            f"pointer-events: none; "
            f"}}"
        )

    return "\n".join(rules)


def _build_remote_selection_css(
    selections: dict[str, dict[str, Any]], exclude_client_id: str
) -> str:
    """Build CSS rules for remote users' selections.

    Args:
        selections: Dict of client_id -> {start_word, end_word, name, color}.
        exclude_client_id: Current client to exclude from CSS.

    Returns:
        CSS string with selection overlay rules.
    """
    rules = []
    for cid, sel in selections.items():
        if cid == exclude_client_id:
            continue
        start = sel.get("start_word")
        end = sel.get("end_word")
        color = sel.get("color", "#ffeb3b")
        name = sel.get("name", "User")

        if start is None or end is None:
            continue

        # Ensure start < end
        if start > end:
            start, end = end, start

        # Create selector for all words in range
        # Use box-shadow to extend highlight into trailing whitespace
        selectors = [f'[data-w="{i}"]' for i in range(start, end + 1)]
        if selectors:
            selector_str = ", ".join(selectors)
            rules.append(
                f"{selector_str} {{ "
                f"background-color: {color}30 !important; "
                f"box-shadow: 0.3em 0 0 {color}30; "
                f"}}"
            )
            # Last word shouldn't extend into next content
            rules.append(f'[data-w="{end}"] {{ box-shadow: none !important; }}')

            # Add name label to first word only
            rules.append(f'[data-w="{start}"] {{ position: relative; }}')
            rules.append(
                f'[data-w="{start}"]::before {{ '
                f'content: "{name}"; '
                f"position: absolute; "
                f"top: -1.2em; left: 0; "
                f"font-size: 0.65rem; "
                f"background: {color}; "
                f"color: white; "
                f"padding: 1px 4px; "
                f"border-radius: 2px; "
                f"white-space: nowrap; "
                f"z-index: 10; "
                f"pointer-events: none; "
                f"}}"
            )

    return "\n".join(rules)


class _PageContext:
    """Holds per-page state for the live annotation demo.

    Note: UI element attributes are typed as non-None because they're always
    set immediately after construction in `live_annotation_demo_page()`.
    """

    def __init__(
        self,
        client_id: str,
        username: str,
        client_color: str,
        doc_id: str,
        ann_doc: Any,
        words: list[str],
    ) -> None:
        self.client_id = client_id
        self.username = username
        self.client_color = client_color
        self.doc_id = doc_id
        self.ann_doc = ann_doc
        self.words = words
        self.current_selection: dict[str, int | None] = {"start": None, "end": None}
        self.annotation_cards: dict[str, ui.element] = {}
        # UI elements set during page build (typed as non-None for convenience)
        self.highlight_style: ui.element = None
        self.selection_style: ui.element = None
        self.cursor_style: ui.element = None
        self.annotations_container: ui.element = None
        self.client_count_label: ui.label = None


def _setup_page_css() -> None:
    """Add CSS styles for the page."""
    ui.add_head_html(_TAILWIND_OVERRIDES)
    ui.add_css(_PAGE_CSS)
    ui.add_css(_QUASAR_OVERRIDES)
    # Register custom colors for tag buttons
    custom_tag_colors = {
        tag.value.replace("_", "-"): color for tag, color in TAG_COLORS.items()
    }
    ui.colors(**custom_tag_colors)


def _build_tag_toolbar(apply_tag_callback: Any) -> None:
    """Build the fixed tag toolbar header."""
    with (
        ui.header().classes("bg-gray-100 q-py-xs"),
        ui.row().classes("tag-toolbar-compact w-full"),
    ):
        for i, tag in enumerate(BriefTag):
            shortcut = list(TAG_SHORTCUTS.keys())[i] if i < len(TAG_SHORTCUTS) else ""
            tag_name = tag.value.replace("_", " ").title()
            label = f"[{shortcut}] {tag_name}"

            async def apply_tag(t: BriefTag = tag) -> None:
                await apply_tag_callback(t)

            color_name = tag.value.replace("_", "-")
            ui.button(label, on_click=apply_tag, color=color_name).classes(
                "text-xs compact-btn"
            )


def _build_header_info(username: str, client_color: str) -> ui.label:
    """Build the header info row, return the client count label."""
    with ui.row().classes("w-full items-center gap-4 py-2"):
        ui.label("Live Annotation Demo").classes("text-h5")
        ui.label(f"You are: {username}").classes("text-caption").style(
            f"color: {client_color}; font-weight: bold;"
        )
        return ui.label("1 user online").classes("text-caption text-grey")


def _build_main_layout(
    processed_doc: _ProcessedDocument,
) -> tuple[ui.element, ui.element]:
    """Build the main layout with document and annotations container."""
    layout_wrapper = ui.element("div").style(
        "position: relative; display: flex; gap: 1rem; "
        "max-width: 1200px; margin: 0 auto;"
    )
    with layout_wrapper:
        doc_container = ui.element("div").classes("doc-container").style("flex: 7;")
        doc_container.props('id="doc-container"')
        with doc_container:
            ui.html(processed_doc.html, sanitize=False)

        annotations_container = (
            ui.element("div")
            .classes("annotations-sidebar")
            .style("flex: 3; min-width: 280px; position: relative;")
            .props('id="annotations-container"')
        )
    return doc_container, annotations_container


def _build_floating_menu(apply_tag_callback: Any) -> ui.element:
    """Build the floating tag menu."""
    floating_menu = ui.element("div").classes("floating-menu")
    floating_menu.props('id="floating-tag-menu"')
    with floating_menu, ui.column().classes("gap-1").style("min-width: 180px"):
        for i, tag in enumerate(BriefTag):
            shortcut = list(TAG_SHORTCUTS.keys())[i] if i < len(TAG_SHORTCUTS) else ""
            tag_name = tag.value.replace("_", " ").title()
            label = f"[{shortcut}] {tag_name}" if shortcut else tag_name

            async def apply_tag_floating(t: BriefTag = tag) -> None:
                await apply_tag_callback(t)
                await ui.run_javascript(
                    'document.getElementById("floating-tag-menu")'
                    '.classList.remove("visible")'
                )

            color_name = tag.value.replace("_", "-")
            ui.button(label, on_click=apply_tag_floating, color=color_name).classes(
                "w-full text-xs"
            )
    return floating_menu


def _build_dynamic_style_elements() -> tuple[ui.element, ui.element, ui.element]:
    """Build the dynamic CSS style elements for highlights, selections, cursors."""
    highlight_style = ui.element("style")
    highlight_style.props('id="highlight-styles"')
    selection_style = ui.element("style")
    selection_style.props('id="selection-styles"')
    cursor_style = ui.element("style")
    cursor_style.props('id="cursor-styles"')
    return highlight_style, selection_style, cursor_style


def _create_annotation_card(
    ctx: _PageContext,
    h: dict,
    update_highlight_css: Any,
    broadcast_update: Any,
    refresh_annotations: Any,
) -> None:
    """Create an annotation card for a highlight."""
    highlight_id = h.get("id", "")
    tag = BriefTag(h.get("tag", "jurisdiction"))
    tag_name = tag.value.replace("_", " ").title()
    color = TAG_COLORS.get(tag, "#666")
    author = h.get("author", "Unknown")
    text = h.get("text", "")[:80]
    if len(h.get("text", "")) > 80:
        text += "..."
    comments = h.get("comments", [])
    start_word = int(h.get("start_word", 0))
    end_word = int(h.get("end_word", start_word))

    with ctx.annotations_container:
        card = (
            ui.card()
            .classes("ann-card-positioned")
            .style(f"border-left: 4px solid {color};")
            .props(f'data-start-word="{start_word}" data-end-word="{end_word}"')
        )
        ctx.annotation_cards[highlight_id] = card

        with card:
            _build_card_header(
                ctx,
                highlight_id,
                card,
                tag_name,
                color,
                update_highlight_css,
                broadcast_update,
            )
            ui.label(f"by {author}").classes("text-xs text-grey")
            ui.label(f'"{text}"').classes("text-sm italic")
            _build_go_to_text_button(start_word, end_word)
            _build_card_comments(comments)
            _build_card_comment_input(
                ctx, highlight_id, refresh_annotations, broadcast_update
            )


def _build_card_header(
    ctx: _PageContext,
    highlight_id: str,
    card: ui.card,
    tag_name: str,
    color: str,
    update_highlight_css: Any,
    broadcast_update: Any,
) -> None:
    """Build the header row of an annotation card."""
    with ui.row().classes("w-full justify-between items-center"):
        ui.label(tag_name).classes("text-sm font-bold").style(f"color: {color};")

        async def close_card(hid: str = highlight_id, c: ui.card = card) -> None:
            ctx.ann_doc.remove_highlight(hid, origin_client_id=ctx.client_id)
            c.delete()
            del ctx.annotation_cards[hid]
            update_highlight_css()
            await broadcast_update()

        ui.button(icon="close", on_click=close_card).props("flat dense size=xs")


def _build_go_to_text_button(start_word: int, end_word: int) -> None:
    """Build the 'Go to text' button with scroll and highlight."""

    async def scroll_to_source(sw: int = start_word, ew: int = end_word) -> None:
        outline_on = "s.style.outline='3px solid yellow';s.style.outlineOffset='2px';"
        js = (
            f"const el = document.querySelector('[data-w=\"{sw}\"]');"
            "if (!el) return;"
            "el.scrollIntoView({behavior:'smooth', block:'center'});"
            f"for (let i = {sw}; i < {ew}; i++) {{"
            "const s = document.querySelector('[data-w=\"'+i+'\"]');"
            f"if (s) {{ {outline_on} }}"
            "}"
            "setTimeout(() => {"
            f"for (let i = {sw}; i < {ew}; i++) {{"
            "const s = document.querySelector('[data-w=\"'+i+'\"]');"
            "if (s) { s.style.outline=''; }"
            "}"
            "}, 1500);"
        )
        await ui.run_javascript(js)

    ui.button("Go to text", icon="visibility", on_click=scroll_to_source).props(
        "flat dense size=sm"
    )


def _build_card_comments(comments: list) -> None:
    """Build the comments section of an annotation card."""
    if comments:
        ui.separator()
        for comment in comments:
            c_author = comment.get("author", "Unknown")
            c_text = comment.get("text", "")
            with ui.element("div").classes("bg-gray-100 p-2 rounded"):
                ui.label(c_author).classes("text-xs font-bold")
                ui.label(c_text).classes("text-sm")


def _build_card_comment_input(
    ctx: _PageContext,
    highlight_id: str,
    refresh_annotations: Any,
    broadcast_update: Any,
) -> None:
    """Build the comment input for an annotation card."""
    comment_input = (
        ui.input(placeholder="Add comment...").props("dense").classes("w-full")
    )

    async def add_comment(
        hid: str = highlight_id, inp: ui.input = comment_input
    ) -> None:
        if inp.value.strip():
            ctx.ann_doc.add_comment(
                hid, ctx.username, inp.value, origin_client_id=ctx.client_id
            )
            inp.value = ""
            if hid in ctx.annotation_cards:
                ctx.annotation_cards[hid].delete()
                del ctx.annotation_cards[hid]
            await refresh_annotations()
            await broadcast_update()

    ui.button("Post", on_click=add_comment).props("dense size=sm")


def _make_refresh_annotations(
    ctx: _PageContext,
    update_highlight_css: Any,
    broadcast_update: Any,
) -> Any:
    """Create the refresh_annotations function with closures."""

    async def refresh_annotations() -> None:
        """Refresh annotation cards in the sidebar."""
        highlights = ctx.ann_doc.get_all_highlights()
        current_ids = {h.get("id", "") for h in highlights}

        # Remove cards for deleted highlights
        for hid in list(ctx.annotation_cards.keys()):
            if hid not in current_ids:
                ctx.annotation_cards[hid].delete()
                del ctx.annotation_cards[hid]

        # Create cards for each highlight
        for h in highlights:
            highlight_id = h.get("id", "")
            if highlight_id not in ctx.annotation_cards:
                _create_annotation_card(
                    ctx, h, update_highlight_css, broadcast_update, refresh_annotations
                )

    return refresh_annotations


def _make_css_updaters(ctx: _PageContext) -> tuple[Any, Any, Any]:
    """Create CSS update functions."""

    def update_highlight_css() -> None:
        highlights = ctx.ann_doc.get_all_highlights()
        css = _build_highlight_css(highlights, TAG_COLORS)
        ctx.highlight_style._props["innerHTML"] = css
        ctx.highlight_style.update()

    def update_remote_selection_css() -> None:
        clients = _connected_clients.get(ctx.doc_id, {})
        selections = {cid: state.to_selection_dict() for cid, state in clients.items()}
        css = _build_remote_selection_css(selections, ctx.client_id)
        ctx.selection_style._props["innerHTML"] = css
        ctx.selection_style.update()

    def update_remote_cursor_css() -> None:
        clients = _connected_clients.get(ctx.doc_id, {})
        cursors = {cid: state.to_cursor_dict() for cid, state in clients.items()}
        css = _build_remote_cursor_css(cursors, ctx.client_id)
        ctx.cursor_style._props["innerHTML"] = css
        ctx.cursor_style.update()

    return update_highlight_css, update_remote_selection_css, update_remote_cursor_css


def _make_broadcast_functions(ctx: _PageContext) -> tuple[Any, Any, Any]:
    """Create broadcast functions."""

    async def broadcast_update() -> None:
        for cid, state in _connected_clients.get(ctx.doc_id, {}).items():
            if cid != ctx.client_id and state.callback:
                with contextlib.suppress(Exception):
                    await state.callback()

    async def broadcast_selection_update() -> None:
        my_state = _connected_clients.get(ctx.doc_id, {}).get(ctx.client_id)
        if my_state:
            my_state.set_selection(
                ctx.current_selection.get("start"), ctx.current_selection.get("end")
            )
        await broadcast_update()

    async def broadcast_cursor_update(word_index: int | None) -> None:
        my_state = _connected_clients.get(ctx.doc_id, {}).get(ctx.client_id)
        if my_state:
            my_state.set_cursor(word_index)
        await broadcast_update()

    return broadcast_update, broadcast_selection_update, broadcast_cursor_update


def _setup_event_handlers(
    ctx: _PageContext,
    apply_tag_to_selection: Any,
    broadcast_selection_update: Any,
    broadcast_cursor_update: Any,
) -> None:
    """Set up event handlers for the page."""

    async def handle_selection(e: GenericEventArguments) -> None:
        start = e.args.get("start")
        end = e.args.get("end")
        client_x = e.args.get("clientX", 0)
        client_y = e.args.get("clientY", 0)

        if start is not None and end is not None:
            ctx.current_selection["start"] = start
            ctx.current_selection["end"] = end
            await ui.run_javascript(
                f"const menu = document.getElementById('floating-tag-menu');"
                f"menu.style.left = '{client_x}px';"
                f"menu.style.top = '{client_y + 10}px';"
                "menu.classList.add('visible');"
            )
            await broadcast_selection_update()

    async def handle_selection_cleared(_e: GenericEventArguments) -> None:
        ctx.current_selection["start"] = None
        ctx.current_selection["end"] = None
        await broadcast_selection_update()

    async def handle_cursor_moved(e: GenericEventArguments) -> None:
        word = e.args.get("word")
        await broadcast_cursor_update(word)

    async def handle_keydown(e: GenericEventArguments) -> None:
        key = e.args.get("key", "")
        if key in TAG_SHORTCUTS and ctx.current_selection.get("start") is not None:
            await apply_tag_to_selection(TAG_SHORTCUTS[key])
            await ui.run_javascript(
                'document.getElementById("floating-tag-menu")?.classList.remove("visible")'
            )

    ui.on("words_selected", handle_selection)
    ui.on("selection_cleared", handle_selection_cleared)
    ui.on("cursor_moved", handle_cursor_moved)
    ui.on(
        "click",
        lambda _: ui.run_javascript(
            'document.getElementById("floating-tag-menu")?.classList.remove("visible")'
        ),
    )
    ui.on("keydown", handle_keydown)


@ui.page("/demo/live-annotation")
async def live_annotation_demo_page() -> None:  # noqa: PLR0915  # TODO: refactor further
    """Live annotation demo page with CRDT-based collaboration."""
    await ui.context.client.connected()

    client = ui.context.client
    client_id = str(id(client))
    username = _get_username()
    doc_id = "demo-case-183"

    ann_doc = _doc_registry.get_or_create(doc_id)
    client_color = ann_doc.register_client(client_id, username)

    if doc_id not in _connected_clients:
        _connected_clients[doc_id] = {}

    # Load and parse the case document
    case_path = _FIXTURES_DIR / "183.rtf"
    if not case_path.exists():
        ui.label("Demo case file not found").classes("text-red")
        return

    parsed = parse_rtf(case_path)
    processed_doc = _html_to_word_spans(parsed.html)

    # Create page context
    ctx = _PageContext(
        client_id, username, client_color, doc_id, ann_doc, processed_doc.words
    )

    # Create functions that need ctx
    (
        update_highlight_css,
        update_remote_selection_css,
        update_remote_cursor_css,
    ) = _make_css_updaters(ctx)
    (
        broadcast_update,
        broadcast_selection_update,
        broadcast_cursor_update,
    ) = _make_broadcast_functions(ctx)
    refresh_annotations = _make_refresh_annotations(
        ctx, update_highlight_css, broadcast_update
    )

    async def apply_tag_to_selection(tag: BriefTag) -> None:
        start = ctx.current_selection.get("start")
        end = ctx.current_selection.get("end")
        if start is None or end is None:
            ui.notify("No text selected", type="warning")
            return
        if start > end:
            start, end = end, start
        text = " ".join(ctx.words[start : end + 1])
        ctx.ann_doc.add_highlight(
            start_word=start,
            end_word=end + 1,
            tag=tag.value,
            text=text,
            author=username,
            origin_client_id=client_id,
        )
        ctx.current_selection["start"] = None
        ctx.current_selection["end"] = None
        update_highlight_css()
        await refresh_annotations()
        await broadcast_update()
        ui.notify(f"Tagged as {tag.value.replace('_', ' ').title()}")

    async def handle_update_from_other() -> None:
        update_highlight_css()
        update_remote_selection_css()
        update_remote_cursor_css()
        await refresh_annotations()

    # Build UI
    _setup_page_css()
    _build_tag_toolbar(apply_tag_to_selection)
    ctx.client_count_label = _build_header_info(username, client_color)
    _, ctx.annotations_container = _build_main_layout(processed_doc)
    _build_floating_menu(apply_tag_to_selection)
    (
        ctx.highlight_style,
        ctx.selection_style,
        ctx.cursor_style,
    ) = _build_dynamic_style_elements()

    # Register client
    _connected_clients[doc_id][client_id] = ClientState(
        callback=handle_update_from_other, color=client_color, name=username
    )

    def update_client_count() -> None:
        count = len(_connected_clients.get(doc_id, {}))
        ctx.client_count_label.text = f"{count} user(s) online"

    update_client_count()

    def on_disconnect() -> None:
        ann_doc.unregister_client(client_id)
        if doc_id in _connected_clients:
            _connected_clients[doc_id].pop(client_id, None)

    client.on_disconnect(on_disconnect)

    # Set up event handlers
    _setup_event_handlers(
        ctx, apply_tag_to_selection, broadcast_selection_update, broadcast_cursor_update
    )

    # Initial render
    update_highlight_css()
    await refresh_annotations()

    # Load JavaScript
    js_file = _ASSETS_DIR / "js" / "live-annotation.js"
    js_code = js_file.read_text()
    await ui.run_javascript(f"{js_code}\nwindow.LiveAnnotation.init(emitEvent);")
