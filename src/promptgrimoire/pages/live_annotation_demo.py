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

from nicegui import ui

from promptgrimoire.crdt import AnnotationDocumentRegistry
from promptgrimoire.models import TAG_COLORS, TAG_SHORTCUTS, BriefTag
from promptgrimoire.parsers import parse_rtf

if TYPE_CHECKING:
    from nicegui.events import GenericEventArguments

# Path to fixtures for demo
_FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures"

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
    /* Document container */
    .doc-container {
        font-family: "Times New Roman", Times, serif;
        font-size: 12pt;
        line-height: 1.6;
        padding: 1rem;
        background: white;
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

    /* Two-column layout */
    .main-layout {
        display: flex;
        gap: 1rem;
        height: calc(100vh - 150px);
    }
    .doc-column {
        flex: 7;
        overflow-y: auto;
        border: 1px solid #ddd;
        border-radius: 4px;
    }
    .ann-column {
        flex: 3;
        min-width: 280px;
        overflow-y: auto;
        background: #f8f8f8;
        border-radius: 4px;
        padding: 0.5rem;
    }

    /* Mobile: stacked layout */
    @media (max-width: 768px) {
        .main-layout {
            flex-direction: column;
        }
        .doc-column, .ann-column {
            flex: none;
            height: 50vh;
        }
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
"""

# JavaScript for selection handling (minimal: only emits events)
_SELECTION_JS = """
    const container = document.getElementById('doc-container');
    if (!container) return;

    // Helper to find word span from a node (handles text nodes and elements)
    function findWordSpan(node) {
        if (!node) return null;
        // If it's a text node, get parent element
        const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
        if (!el) return null;
        // Try to find closest word span
        return el.closest('[data-w]') || el.querySelector('[data-w]');
    }

    // Find all word spans that intersect with a range
    function getWordRangeFromSelection(selection) {
        if (!selection.rangeCount) return null;

        const range = selection.getRangeAt(0);

        // Get all word spans in the container
        const allWordSpans = container.querySelectorAll('[data-w]');
        let minWord = Infinity;
        let maxWord = -Infinity;

        // Check which word spans intersect with the selection range
        for (const span of allWordSpans) {
            if (selection.containsNode(span, true)) {
                const wordIdx = parseInt(span.dataset.w);
                minWord = Math.min(minWord, wordIdx);
                maxWord = Math.max(maxWord, wordIdx);
            }
        }

        if (minWord === Infinity || maxWord === -Infinity) {
            // Fallback: try anchor/focus method for single-element selections
            const anchorSpan = findWordSpan(selection.anchorNode);
            const focusSpan = findWordSpan(selection.focusNode);
            if (anchorSpan && focusSpan) {
                const start = parseInt(anchorSpan.dataset.w);
                const end = parseInt(focusSpan.dataset.w);
                return { start: Math.min(start, end), end: Math.max(start, end) };
            }
            return null;
        }

        return { start: minWord, end: maxWord };
    }

    // Track selection changes
    document.addEventListener('selectionchange', () => {
        const selection = window.getSelection();
        if (!selection || selection.isCollapsed) {
            emitEvent('selection_cleared', {});
            return;
        }

        // Check if selection is within our container
        if (!container.contains(selection.anchorNode) ||
            !container.contains(selection.focusNode)) {
            return;
        }

        const wordRange = getWordRangeFromSelection(selection);
        if (wordRange) {
            // Get bounding rect for menu positioning
            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();

            emitEvent('words_selected', {
                start: wordRange.start,
                end: wordRange.end,
                clientX: rect.left + rect.width / 2,
                clientY: rect.bottom
            });
        }
    });

    // Track mouse position for cursor sharing
    let lastCursorWord = null;
    container.addEventListener('mousemove', (e) => {
        const span = e.target.closest('[data-w]');
        if (span) {
            const wordIndex = parseInt(span.dataset.w);
            if (wordIndex !== lastCursorWord) {
                lastCursorWord = wordIndex;
                emitEvent('cursor_moved', { word: wordIndex });
            }
        }
    });
"""

_KEYBOARD_JS = """
    document.addEventListener('keydown', (e) => {
        if (['1','2','3','4','5','6','7','8','9','0'].includes(e.key)) {
            emitEvent('keydown', { key: e.key });
        }
    });
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
    _PUA_PATTERN = re.compile(r"[\ue000-\uf8ff]")

    def __init__(self) -> None:
        self.words: list[str] = []
        self.word_to_para: dict[int, int] = {}
        self._para_index = 0
        self._word_index = 0

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
            result = f'<span class="w" data-w="{self._word_index}">{word}</span>'
            self._word_index += 1
            return result

        def restore_entity(m: re.Match) -> str:
            return entities[ord(m.group(0)) - 0xE000]

        protected = self._ENTITY_PATTERN.sub(save_entity, text)
        wrapped = self._WORD_PATTERN.sub(replace_word, protected)
        return self._PUA_PATTERN.sub(restore_entity, wrapped)

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
                # Increment paragraph index for block-level tags
                tag_match = self._TAG_NAME_PATTERN.match(tag)
                if tag_match and tag_match.group(1).lower() in self._PARA_TAGS:
                    self._para_index += 1
                i = tag_end + 1
            else:
                next_tag = html.find("<", i)
                if next_tag == -1:
                    result.append(self._wrap_text(html[i:]))
                    break
                result.append(self._wrap_text(html[i:next_tag]))
                i = next_tag
        return "".join(result)


def _html_to_word_spans(html: str) -> tuple[str, list[str], dict[int, int]]:
    """Convert HTML content to word-wrapped spans for CSS-based highlighting.

    Args:
        html: Raw HTML from RTF conversion.

    Returns:
        Tuple of:
        - Modified HTML with each word wrapped in <span data-w="N">
        - List of words (for mapping word index to text)
        - Dict mapping word index to paragraph index
    """
    processor = _WordSpanProcessor()
    processed_html = processor.process(html)
    return processed_html, processor.words, processor.word_to_para


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


@ui.page("/demo/live-annotation")
async def live_annotation_demo_page() -> None:  # noqa: PLR0915
    """Live annotation demo page with CRDT-based collaboration."""
    # Wait for client connection
    await ui.context.client.connected()

    client = ui.context.client
    client_id = str(id(client))
    username = _get_username()

    # Use a fixed document ID for the demo
    doc_id = "demo-case-183"

    # Get or create the annotation document
    ann_doc = _doc_registry.get_or_create(doc_id)

    # Register client and get assigned color
    client_color = ann_doc.register_client(client_id, username)

    # Track for broadcasting
    if doc_id not in _connected_clients:
        _connected_clients[doc_id] = {}

    # Page state
    current_selection: dict[str, int | None] = {"start": None, "end": None}

    # Load and parse the case document
    case_path = _FIXTURES_DIR / "183.rtf"
    if not case_path.exists():
        ui.label("Demo case file not found").classes("text-red")
        return

    parsed = parse_rtf(case_path)
    processed_html, words, _word_to_para = _html_to_word_spans(parsed.html)

    # --- CSS ---
    # Tailwind overrides must use add_head_html with type="text/tailwindcss"
    ui.add_head_html(_TAILWIND_OVERRIDES)
    ui.add_css(_PAGE_CSS)

    # Register custom colors for tag buttons (must be called before using colors)
    # Use hyphens instead of underscores for CSS color names
    custom_tag_colors = {
        tag.value.replace("_", "-"): color for tag, color in TAG_COLORS.items()
    }
    ui.colors(**custom_tag_colors)

    # --- Fixed Tag Toolbar using ui.header() (Quasar's built-in sticky header) ---
    with (
        ui.header().classes("bg-gray-100 q-py-xs"),
        ui.row().classes("tag-toolbar-compact w-full"),
    ):
        for i, tag in enumerate(BriefTag):
            shortcut = list(TAG_SHORTCUTS.keys())[i] if i < len(TAG_SHORTCUTS) else ""
            tag_name = tag.value.replace("_", " ").title()
            label = f"[{shortcut}] {tag_name}"

            async def apply_tag(t: BriefTag = tag) -> None:
                await _apply_tag_to_selection(t)

            # Use custom color registered with ui.colors() (hyphens for CSS)
            color_name = tag.value.replace("_", "-")
            ui.button(label, on_click=apply_tag, color=color_name).classes(
                "text-xs compact-btn"
            )

    # --- Header info (below sticky header) ---
    with ui.row().classes("w-full items-center gap-4 py-2"):
        ui.label("Live Annotation Demo").classes("text-h5")
        ui.label(f"You are: {username}").classes("text-caption").style(
            f"color: {client_color}; font-weight: bold;"
        )
        client_count_label = ui.label("1 user online").classes("text-caption text-grey")

    # --- Main layout ---
    with ui.element("div").classes("main-layout"):
        # Document column
        doc_column = ui.element("div").classes("doc-column")
        with doc_column:
            doc_container = ui.element("div").classes("doc-container")
            doc_container.props('id="doc-container"')

            # Render the processed HTML with word spans
            # SECURITY: RTF files must come from trusted sources
            with doc_container:
                ui.html(processed_html, sanitize=False)

        # Annotation column
        ann_column = ui.element("div").classes("ann-column")
        with ann_column:
            ui.label("Annotations").classes("text-h6 mb-2")
            annotations_container = ui.column().classes("w-full gap-2")

    # --- Floating tag menu ---
    floating_menu = ui.element("div").classes("floating-menu")
    floating_menu.props('id="floating-tag-menu"')
    with floating_menu, ui.column().classes("gap-1").style("min-width: 180px"):
        for i, tag in enumerate(BriefTag):
            shortcut = list(TAG_SHORTCUTS.keys())[i] if i < len(TAG_SHORTCUTS) else ""
            tag_name = tag.value.replace("_", " ").title()
            label = f"[{shortcut}] {tag_name}" if shortcut else tag_name

            async def apply_tag_floating(t: BriefTag = tag) -> None:
                await _apply_tag_to_selection(t)
                await ui.run_javascript(
                    'document.getElementById("floating-tag-menu")'
                    '.classList.remove("visible")'
                )

            color_name = tag.value.replace("_", "-")
            ui.button(label, on_click=apply_tag_floating, color=color_name).classes(
                "w-full text-xs"
            )

    # --- Dynamic highlight CSS element ---
    highlight_style = ui.element("style")
    highlight_style.props('id="highlight-styles"')

    # --- Dynamic selection CSS element for remote users ---
    selection_style = ui.element("style")
    selection_style.props('id="selection-styles"')

    # --- Dynamic cursor CSS element for remote users ---
    cursor_style = ui.element("style")
    cursor_style.props('id="cursor-styles"')

    def update_highlight_css() -> None:
        """Update the CSS for all current highlights."""
        highlights = ann_doc.get_all_highlights()
        css = _build_highlight_css(highlights, TAG_COLORS)
        # Update the style element content
        highlight_style._props["innerHTML"] = css
        highlight_style.update()

    async def refresh_annotations() -> None:
        """Refresh the annotation sidebar."""
        annotations_container.clear()
        highlights = ann_doc.get_all_highlights()

        if not highlights:
            with annotations_container:
                ui.label("No annotations yet").classes("text-grey")
            return

        with annotations_container:
            for h in highlights:
                tag = BriefTag(h.get("tag", "jurisdiction"))
                tag_name = tag.value.replace("_", " ").title()
                color = TAG_COLORS.get(tag, "#666")
                author = h.get("author", "Unknown")
                text = h.get("text", "")[:100]
                if len(h.get("text", "")) > 100:
                    text += "..."
                comments = h.get("comments", [])
                highlight_id = h.get("id", "")
                start_word = h.get("start_word", 0)

                # Click handler to scroll document to highlighted text
                async def scroll_to_highlight(sw: int = start_word) -> None:
                    js = f"""
                        const el = document.querySelector('[data-w="{sw}"]');
                        if (el) {{
                            el.scrollIntoView({{behavior:'smooth',block:'center'}});
                            el.style.transition = 'background-color 0.3s';
                            el.style.backgroundColor = '#ffff00';
                            setTimeout(() => {{el.style.backgroundColor = '';}}, 500);
                        }}
                    """
                    await ui.run_javascript(js)

                with (
                    ui.element("div")
                    .classes("ann-card")
                    .style(
                        f"background-color: {color}20; border-left: 3px solid {color};"
                    )
                    .on("click", scroll_to_highlight)
                ):
                    with ui.row().classes("justify-between items-center"):
                        ui.label(author).classes("font-semibold text-sm").style(
                            f"color: {color};"
                        )
                        ui.label(tag_name).classes("text-xs").style(
                            f"background: {color}; color: white; "
                            "padding: 2px 6px; border-radius: 3px;"
                        )

                    ui.label(f'"{text}"').classes("text-sm italic text-grey mt-1")

                    # Comment thread (expandable)
                    comment_label = (
                        f"{len(comments)} comment(s)" if comments else "Add comment"
                    )
                    with ui.expansion(comment_label, icon="comment").classes("mt-1"):
                        # Show existing comments
                        if comments:
                            for comment in comments:
                                c_author = comment.get("author", "Unknown")
                                c_text = comment.get("text", "")
                                with ui.element("div").classes(
                                    "bg-gray-100 p-2 rounded mb-1"
                                ):
                                    ui.label(c_author).classes(
                                        "text-xs font-semibold text-grey-8"
                                    )
                                    ui.label(c_text).classes("text-sm")

                        # New comment input
                        comment_input = ui.input(placeholder="Your comment...").classes(
                            "w-full mt-2"
                        )

                        async def add_comment(
                            hid: str = highlight_id, inp: ui.input = comment_input
                        ) -> None:
                            if inp.value.strip():
                                ann_doc.add_comment(
                                    hid, username, inp.value, origin_client_id=client_id
                                )
                                inp.value = ""
                                await refresh_annotations()
                                await broadcast_update()

                        ui.button("Post", on_click=add_comment).classes("mt-1")

    async def _apply_tag_to_selection(tag: BriefTag) -> None:
        """Apply a tag to the current selection."""
        start = current_selection.get("start")
        end = current_selection.get("end")

        if start is None or end is None:
            ui.notify("No text selected", type="warning")
            return

        # Ensure start < end
        if start > end:
            start, end = end, start

        # Get the selected text
        selected_words = words[start : end + 1]
        text = " ".join(selected_words)

        # Add highlight to CRDT
        ann_doc.add_highlight(
            start_word=start,
            end_word=end + 1,  # exclusive
            tag=tag.value,
            text=text,
            author=username,
            origin_client_id=client_id,
        )

        # Clear selection
        current_selection["start"] = None
        current_selection["end"] = None

        # Update UI
        update_highlight_css()
        await refresh_annotations()
        await broadcast_update()

        ui.notify(f"Tagged as {tag.value.replace('_', ' ').title()}")

    async def broadcast_update() -> None:
        """Broadcast UI update to all connected clients."""
        for cid, state in _connected_clients.get(doc_id, {}).items():
            if cid != client_id and state.callback:
                with contextlib.suppress(Exception):
                    await state.callback()

    async def broadcast_selection_update() -> None:
        """Broadcast selection state to all connected clients."""
        # Update our selection in the state
        my_state = _connected_clients.get(doc_id, {}).get(client_id)
        if my_state:
            my_state.set_selection(
                current_selection.get("start"), current_selection.get("end")
            )
        # Broadcast to others
        await broadcast_update()

    def update_remote_selection_css() -> None:
        """Update CSS for remote users' selections."""
        clients = _connected_clients.get(doc_id, {})
        selections = {cid: state.to_selection_dict() for cid, state in clients.items()}
        css = _build_remote_selection_css(selections, client_id)
        selection_style._props["innerHTML"] = css
        selection_style.update()

    def update_remote_cursor_css() -> None:
        """Update CSS for remote users' cursors."""
        clients = _connected_clients.get(doc_id, {})
        cursors = {cid: state.to_cursor_dict() for cid, state in clients.items()}
        css = _build_remote_cursor_css(cursors, client_id)
        cursor_style._props["innerHTML"] = css
        cursor_style.update()

    async def broadcast_cursor_update(word_index: int | None) -> None:
        """Broadcast cursor position to all connected clients."""
        my_state = _connected_clients.get(doc_id, {}).get(client_id)
        if my_state:
            my_state.set_cursor(word_index)
        await broadcast_update()

    async def handle_update_from_other() -> None:
        """Handle update notification from another client."""
        update_highlight_css()
        update_remote_selection_css()
        update_remote_cursor_css()
        await refresh_annotations()

    # Register callback for this client
    _connected_clients[doc_id][client_id] = ClientState(
        callback=handle_update_from_other,
        color=client_color,
        name=username,
    )

    def update_client_count() -> None:
        """Update the online user count display."""
        count = len(_connected_clients.get(doc_id, {}))
        client_count_label.text = f"{count} user(s) online"

    update_client_count()

    # Cleanup on disconnect
    def on_disconnect() -> None:
        ann_doc.unregister_client(client_id)
        if doc_id in _connected_clients:
            _connected_clients[doc_id].pop(client_id, None)

    client.on_disconnect(on_disconnect)

    # --- JavaScript for selection handling ---
    # Minimal JS: only emits events, doesn't manipulate DOM structure
    await ui.run_javascript(_SELECTION_JS)

    async def handle_selection(e: GenericEventArguments) -> None:
        """Handle word selection event."""
        start = e.args.get("start")
        end = e.args.get("end")
        client_x = e.args.get("clientX", 0)
        client_y = e.args.get("clientY", 0)

        if start is not None and end is not None:
            current_selection["start"] = start
            current_selection["end"] = end

            # Show floating menu
            await ui.run_javascript(f"""
                const menu = document.getElementById('floating-tag-menu');
                menu.style.left = '{client_x}px';
                menu.style.top = '{client_y + 10}px';
                menu.classList.add('visible');
            """)

            # Broadcast selection to other clients
            await broadcast_selection_update()

    async def handle_selection_cleared(_e: GenericEventArguments) -> None:
        """Handle selection cleared event."""
        current_selection["start"] = None
        current_selection["end"] = None
        # Broadcast cleared selection
        await broadcast_selection_update()

    async def handle_cursor_moved(e: GenericEventArguments) -> None:
        """Handle cursor movement for sharing."""
        word = e.args.get("word")
        await broadcast_cursor_update(word)

    ui.on("words_selected", handle_selection)
    ui.on("selection_cleared", handle_selection_cleared)
    ui.on("cursor_moved", handle_cursor_moved)

    # Hide floating menu on click elsewhere
    ui.on(
        "click",
        lambda _: ui.run_javascript(
            'document.getElementById("floating-tag-menu")?.classList.remove("visible")'
        ),
    )

    # Keyboard shortcuts
    async def handle_keydown(e: GenericEventArguments) -> None:
        key = e.args.get("key", "")
        if key in TAG_SHORTCUTS and current_selection.get("start") is not None:
            tag = TAG_SHORTCUTS[key]
            await _apply_tag_to_selection(tag)
            await ui.run_javascript(
                'document.getElementById("floating-tag-menu")?.classList.remove("visible")'
            )

    ui.on("keydown", handle_keydown)

    # Add keyboard listener
    await ui.run_javascript(_KEYBOARD_JS)

    # Initial render
    update_highlight_css()
    await refresh_annotations()
