"""Case Brief Tool annotation page.

Displays RTF court judgments with text selection and tagging for case briefs.

Route: /case-tool
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from nicegui import app, ui

from promptgrimoire.db import (
    Highlight as DBHighlight,
)
from promptgrimoire.db import (
    HighlightComment,
    create_comment,
    create_highlight,
    get_comments_for_highlight,
    get_highlight_by_id,
    get_highlights_for_case,
)
from promptgrimoire.db import (
    delete_highlight as db_delete_highlight,
)
from promptgrimoire.models import (
    TAG_COLORS,
    TAG_SHORTCUTS,
    BriefTag,
    ParsedRTF,
)
from promptgrimoire.parsers import parse_rtf


def _get_current_user() -> dict | None:
    """Get current authenticated user from session storage."""
    return app.storage.user.get("auth_user")


def _get_username() -> str:
    """Get display name for current user, or 'Unknown Author' if not logged in."""
    user = _get_current_user()
    if user and user.get("email"):
        # Use email prefix as display name
        email = user["email"]
        return email.split("@")[0] if "@" in email else email
    return "Unknown Author"


if TYPE_CHECKING:
    from nicegui.events import GenericEventArguments

# Path to fixtures for demo
_FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures"


def _get_available_cases() -> list[tuple[str, str]]:
    """Get list of available RTF cases from fixtures."""
    cases = []
    for rtf_file in _FIXTURES_DIR.glob("*.rtf"):
        cases.append((rtf_file.stem, rtf_file.name))
    return sorted(cases)


def _load_case(case_id: str) -> ParsedRTF | None:
    """Load and parse a case RTF file.

    Validates case_id to prevent path traversal attacks.
    """
    # Sanitize: only allow alphanumeric, underscore, hyphen
    if not re.match(r"^[\w-]+$", case_id):
        return None
    rtf_path = _FIXTURES_DIR / f"{case_id}.rtf"
    # Verify resolved path is under fixtures dir
    if not rtf_path.resolve().is_relative_to(_FIXTURES_DIR.resolve()):
        return None
    if not rtf_path.exists():
        return None
    return parse_rtf(rtf_path)


@ui.page("/case-tool")
async def case_tool_page() -> None:
    """Case Brief Tool main page."""
    # Register custom colors for each tag type using Quasar's color system
    # kwargs use underscores, but color= parameter uses hyphens (Quasar convention)
    # e.g., tag_jurisdiction in Python -> color="tag-jurisdiction" in usage
    custom_tag_colors = {f"tag_{tag.value}": TAG_COLORS[tag] for tag in BriefTag}
    ui.colors(**custom_tag_colors)

    def color_name(tag: BriefTag) -> str:
        """Convert tag to Quasar color name (underscores -> hyphens)."""
        return f"tag-{tag.value.replace('_', '-')}"

    # Page-local state
    current_case: dict[str, ParsedRTF | str | None] = {
        "id": None,
        "data": None,
    }
    selection_state: dict[str, str | int | None] = {
        "text": "",
        "start": 0,
        "end": 0,
        "para_num": None,
        "header": None,
    }
    editing_highlight: dict[str, DBHighlight | None] = {"highlight": None}
    # Cache for loaded comments (highlight_id -> list of comments)
    comments_cache: dict[str, list[HighlightComment]] = {}

    # CSS for case tool - tag color classes for non-button elements
    tag_color_css = "\n".join(
        f"""
        .tag-{tag.value} {{
            --tag-color: {TAG_COLORS.get(tag, "#666")};
            --tag-color-light: {TAG_COLORS.get(tag, "#666")}22;
            --tag-color-border: {TAG_COLORS.get(tag, "#666")}66;
        }}
        """
        for tag in BriefTag
    )

    ui.add_css(f"""
        /* Tag color classes */
        {tag_color_css}

        /* Case content viewer */
        .case-content {{
            font-family: "Times New Roman", Times, serif;
            font-size: 12pt;
            line-height: 1.5;
            max-height: 80vh;
            overflow-y: auto;
            padding: 1rem;
            background: white;
        }}
        /* Restore ordered list numbering (Tailwind/Quasar resets these) */
        .case-content ol {{
            list-style-type: decimal;
            padding-left: 2.5em;
            margin-left: 0;
        }}
        .case-content ol li {{
            display: list-item;
        }}
        .case-content table {{
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 1em;
        }}
        .case-content td, .case-content th {{
            border: 1px solid #ccc;
            padding: 0.5em;
            vertical-align: top;
        }}

        /* Tag toolbar */
        .tag-toolbar {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            padding: 0.5rem;
            background: #f5f5f5;
            border-radius: 4px;
        }}

        /* Floating tag menu */
        .floating-menu {{
            position: fixed;
            background: white;
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 0.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            display: none;
        }}
        .floating-menu.visible {{
            display: block;
        }}

        /* Annotation sidebar */
        .annotation-sidebar {{
            max-height: 80vh;
            overflow-y: auto;
            background: #f8f8f8;
        }}

        /* Word-style comment card (base styles, colors applied inline) */
        .comment-card {{
            border-radius: 2px;
            padding: 8px 10px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: box-shadow 0.2s;
        }}
        .comment-card:hover {{
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }}

        /* Comment header with author name */
        .comment-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 4px;
            font-size: 0.75rem;
        }}
        .comment-timestamp {{
            color: #888;
            font-size: 0.7rem;
        }}

        /* Quoted text from document */
        .comment-quote {{
            font-style: italic;
            color: #444;
            font-size: 0.85rem;
            line-height: 1.3;
            margin-bottom: 6px;
            padding-left: 8px;
        }}

        /* User's note/comment */
        .comment-note {{
            font-size: 0.85rem;
            color: #222;
            line-height: 1.4;
            margin-top: 6px;
            padding: 4px;
            background: rgba(255,255,255,0.5);
            border-radius: 2px;
        }}
    """)

    # Header
    with ui.row().classes("w-full items-center gap-4 mb-4"):
        ui.label("Case Brief Tool").classes("text-h5")

        # Case selector
        cases = _get_available_cases()
        case_select = ui.select(
            options={c[0]: c[1] for c in cases},
            label="Select Case",
            value=cases[0][0] if cases else None,
        ).classes("w-48")

    # Tag toolbar with colored buttons (using Quasar color system)
    with ui.row().classes("tag-toolbar w-full mb-2"):
        ui.label("Tags:").classes("text-caption self-center mr-2")
        for i, tag in enumerate(BriefTag):
            shortcut = list(TAG_SHORTCUTS.keys())[i] if i < len(TAG_SHORTCUTS) else ""
            tag_name = tag.value.replace("_", " ").title()
            label = f"[{shortcut}] {tag_name}" if shortcut else tag_name

            async def apply_tag(t: BriefTag = tag) -> None:
                await _apply_tag_to_selection(t)

            # Use Quasar color parameter with custom tag color
            ui.button(label, on_click=apply_tag, color=color_name(tag)).classes(
                "text-xs"
            )

    # Main layout: content + sidebar
    with ui.row().classes("w-full gap-0").style("flex-wrap: nowrap"):
        # Main content area (left side, 70%)
        content_container = (
            ui.element("div").classes("case-content border").style("flex: 7")
        )
        content_container.props('data-testid="case-content"')

        # Annotations sidebar (right side, 30%)
        sidebar = (
            ui.column()
            .classes("annotation-sidebar p-2")
            .style("flex: 3; min-width: 280px")
        )
        with sidebar:
            ui.label("Annotations").classes("text-h6 mb-2")
            annotations_container = ui.column().classes("w-full gap-2")

    # Floating tag menu (hidden by default) - with full names
    floating_menu = ui.element("div").classes("floating-menu")
    floating_menu.props('id="floating-tag-menu"')
    with floating_menu:
        with ui.column().classes("gap-1").style("min-width: 200px"):
            for i, tag in enumerate(BriefTag):
                shortcut = (
                    list(TAG_SHORTCUTS.keys())[i] if i < len(TAG_SHORTCUTS) else ""
                )
                tag_name = tag.value.replace("_", " ").title()
                # Show full name with shortcut
                label = f"[{shortcut}] {tag_name}" if shortcut else tag_name

                async def apply_tag_floating(t: BriefTag = tag) -> None:
                    await _apply_tag_to_selection(t)
                    await ui.run_javascript(
                        'document.getElementById("floating-tag-menu").classList.remove("visible")'
                    )

                # Use Quasar color parameter with custom tag color
                ui.button(
                    label, on_click=apply_tag_floating, color=color_name(tag)
                ).classes("w-full text-xs")

    # Comment thread dialog
    comment_dialog = ui.dialog()
    with comment_dialog, ui.card().classes("w-[450px]"):
        ui.label("Discussion").classes("text-h6")
        dialog_tag_label = ui.label().classes("mb-2")
        dialog_text_preview = ui.label().classes("annotation-text mb-2 italic text-sm")

        # Container for existing comments (will be populated dynamically)
        comments_container = ui.column().classes(
            "w-full gap-2 max-h-64 overflow-y-auto"
        )

        # New comment input
        ui.separator().classes("my-2")
        comment_input = ui.textarea(label="Add a reply...").classes("w-full")

        with ui.row().classes("w-full justify-between mt-2"):

            async def delete_current_highlight() -> None:
                if editing_highlight["highlight"]:
                    h = editing_highlight["highlight"]
                    await db_delete_highlight(h.id)
                    ui.notify("Annotation deleted")
                    comment_dialog.close()
                    # Re-render to remove the highlight marker
                    await _render_case_content(content_container)
                    await _setup_selection_handlers(content_container)
                    await refresh_sidebar()

            async def add_reply() -> None:
                if editing_highlight["highlight"] and comment_input.value.strip():
                    h = editing_highlight["highlight"]
                    await create_comment(h.id, _get_username(), comment_input.value)
                    # Clear cache for this highlight
                    comments_cache.pop(str(h.id), None)
                    comment_input.value = ""
                    ui.notify("Reply added")
                    # Refresh the dialog to show new comment
                    await _populate_comment_dialog(h)
                    await refresh_sidebar()

            ui.button(
                "Delete Highlight", on_click=delete_current_highlight, color="red"
            )
            ui.button("Add Reply", on_click=add_reply, color="primary")

    async def _populate_comment_dialog(highlight: DBHighlight) -> None:
        """Populate the comment dialog with existing comments."""
        comments_container.clear()
        tag = BriefTag(highlight.tag)
        tag_name = tag.value.replace("_", " ").title()
        tag_color = TAG_COLORS.get(tag, "#666")
        dialog_tag_label.set_text(f"Tag: {tag_name}")

        # Truncate preview text
        preview = highlight.text[:150]
        if len(highlight.text) > 150:
            preview += "..."
        dialog_text_preview.set_text(f'"{preview}"')

        # Load comments from database (or cache)
        hid = str(highlight.id)
        if hid not in comments_cache:
            comments_cache[hid] = await get_comments_for_highlight(highlight.id)
        comments = comments_cache[hid]

        with comments_container:
            if not comments:
                ui.label("No comments yet. Be the first to reply!").classes(
                    "text-grey text-sm"
                )
            else:
                for comment in comments:
                    timestamp = comment.created_at.strftime("%d/%m/%Y %H:%M")
                    with (
                        ui.element("div")
                        .classes("p-2 rounded")
                        .style(f"background-color: {tag_color}10;")
                    ):
                        with ui.row().classes("justify-between items-center"):
                            ui.label(comment.author).classes("font-semibold text-sm")
                            ui.label(timestamp).classes("text-xs text-grey")
                        ui.label(comment.text).classes("text-sm mt-1")

    async def _apply_tag_to_selection(tag: BriefTag) -> None:
        """Apply a tag to the current selection."""
        text = selection_state.get("text")
        case_id = current_case.get("id")
        if not text or not case_id:
            ui.notify("No text selected", type="warning")
            return

        # Extract offsets (guaranteed to be ints when text is present)
        start_offset = selection_state.get("start")
        end_offset = selection_state.get("end")
        if not isinstance(start_offset, int) or not isinstance(end_offset, int):
            ui.notify("Invalid selection offsets", type="warning")
            return

        # Extract para_num as int if present
        para_num_raw = selection_state.get("para_num")
        para_num = int(para_num_raw) if para_num_raw is not None else None

        # Extract section_header as str if present
        header = selection_state.get("header")
        section_header = str(header) if header else None

        await create_highlight(
            case_id=str(case_id),
            tag=tag.value,
            start_offset=start_offset,
            end_offset=end_offset,
            text=str(text),
            created_by=_get_username(),
            para_num=para_num,
            section_header=section_header,
        )

        # Clear selection
        selection_state.update(
            {
                "text": "",
                "start": 0,
                "end": 0,
                "para_num": None,
                "header": None,
            }
        )

        ui.notify(f"Tagged as {tag.value.replace('_', ' ').title()}")

        # Re-render content to show the new highlight marker
        await _render_case_content(content_container)
        await _setup_selection_handlers(content_container)
        await refresh_sidebar()

    async def refresh_sidebar() -> None:
        """Refresh the annotations sidebar."""
        annotations_container.clear()
        if not current_case.get("id"):
            return

        case_id = str(current_case["id"])
        case_highlights = await get_highlights_for_case(case_id)

        if not case_highlights:
            with annotations_container:
                ui.label("No annotations yet").classes("text-grey")
            return

        # Preload comments for all highlights
        for h in case_highlights:
            hid = str(h.id)
            if hid not in comments_cache:
                comments_cache[hid] = await get_comments_for_highlight(h.id)

        with annotations_container:
            for h in case_highlights:
                tag = BriefTag(h.tag)
                tag_name = tag.value.replace("_", " ").title()
                timestamp = h.created_at.strftime("%d/%m/%Y %H:%M")
                tag_color = TAG_COLORS.get(tag, "#666")
                highlight_id = str(h.id)
                comments = comments_cache.get(highlight_id, [])

                # Word-style comment card with tag color via inline style
                # Define handlers before creating the card element
                async def scroll_to_highlight(hid: str = highlight_id) -> None:
                    # Scroll to highlight and flash it
                    await ui.run_javascript(f"""
                        const mark = document.querySelector(
                            'mark[data-highlight-id="{hid}"]'
                        );
                        if (mark) {{
                            const container = mark.closest('.case-content');
                            if (container) {{
                                const markRect = mark.getBoundingClientRect();
                                const containerRect = container.getBoundingClientRect();
                                const scrollTop = markRect.top - containerRect.top
                                    + container.scrollTop - container.clientHeight / 2;
                                container.scrollTo({{
                                    top: Math.max(0, scrollTop),
                                    behavior: 'smooth'
                                }});
                            }}
                            mark.style.outline = '3px solid #ff0';
                            setTimeout(() => mark.style.outline = '', 1500);
                        }}
                    """)

                async def open_thread(highlight: DBHighlight = h) -> None:
                    editing_highlight["highlight"] = highlight
                    comment_input.value = ""
                    await _populate_comment_dialog(highlight)
                    comment_dialog.open()

                # Card with click-to-scroll on entire background
                with (
                    ui.element("div")
                    .classes("comment-card cursor-pointer")
                    .style(
                        f"background-color: {tag_color}15; "
                        f"border-left: 3px solid {tag_color};"
                    )
                    .props(f'data-highlight-id="{highlight_id}"')
                    .on("click", scroll_to_highlight)
                ):
                    # Author and timestamp header row
                    with ui.element("div").classes("comment-header"):
                        ui.label(h.created_by).classes("comment-author").style(
                            f"color: {tag_color}; font-weight: 600;"
                        )
                        ui.label(timestamp).classes("comment-timestamp")

                    # Tag badge and location info row
                    with ui.row().classes("items-center gap-2 mb-1"):
                        ui.label(tag_name).classes("comment-tag-badge").style(
                            f"background-color: {tag_color}; "
                            "color: white; padding: 2px 6px; border-radius: 3px; "
                            "font-size: 0.7rem; display: inline-block;"
                        )
                        # Location context: paragraph number and section header
                        location_parts = []
                        if h.para_num is not None:
                            location_parts.append(f"[{h.para_num}]")
                        if h.section_header:
                            location_parts.append(h.section_header)
                        if location_parts:
                            ui.label(" · ".join(location_parts)).classes(
                                "text-xs text-grey"
                            )

                    # Quoted text from document
                    preview = h.text[:120]
                    if len(h.text) > 120:
                        preview += "..."
                    ui.label(preview).classes("comment-quote").style(
                        f"border-left: 2px solid {tag_color}80;"
                    )

                    # Show comment count and latest reply preview
                    comment_count = len(comments)
                    if comment_count > 0:
                        latest = comments[-1]
                        preview_text = latest.text[:80]
                        if len(latest.text) > 80:
                            preview_text += "..."
                        with ui.element("div").classes("comment-note"):
                            ui.label(f"{latest.author}: {preview_text}").classes(
                                "text-sm"
                            )
                            if comment_count > 1:
                                ui.label(f"({comment_count} replies)").classes(
                                    "text-xs text-grey"
                                )

                    # Thread action button
                    action_text = (
                        f"View Thread ({comment_count})"
                        if comment_count > 0
                        else "Start Discussion"
                    )
                    ui.label(action_text).classes("cursor-pointer underline").style(
                        f"color: {tag_color}; font-size: 0.75rem;"
                    ).on("click", open_thread)

    async def _apply_highlights_to_content(container: ui.element) -> None:
        """Apply visual highlight markers to the document content."""
        case_id = current_case.get("id")
        if not case_id:
            return

        case_highlights = await get_highlights_for_case(str(case_id))
        if not case_highlights:
            return

        # Build highlight data for JavaScript
        # Sort by start offset descending so we apply from end to start
        # (to avoid offset shifting issues)
        highlight_data = [
            {
                "id": str(h.id),
                "start": h.start_offset,
                "end": h.end_offset,
                "color": TAG_COLORS.get(BriefTag(h.tag), "#666"),
                "tag": h.tag,
            }
            for h in sorted(case_highlights, key=lambda x: x.start_offset, reverse=True)
        ]

        container_id = container.id
        # Use longer timeout for large documents with many text nodes
        await ui.run_javascript(
            f"""
            const container = getHtmlElement({container_id});
            if (!container) return;

            const highlights = {highlight_data};

            // Find text node and offset for a given character position
            function findTextPosition(root, targetOffset) {{
                const walker = document.createTreeWalker(
                    root, NodeFilter.SHOW_TEXT, null
                );
                let currentOffset = 0;
                let node;

                while ((node = walker.nextNode())) {{
                    const nodeLength = node.textContent.length;
                    if (currentOffset + nodeLength >= targetOffset) {{
                        return {{
                            node: node,
                            offset: targetOffset - currentOffset
                        }};
                    }}
                    currentOffset += nodeLength;
                }}
                return null;
            }}

            // Apply each highlight
            highlights.forEach(h => {{
                try {{
                    const startPos = findTextPosition(container, h.start);
                    const endPos = findTextPosition(container, h.end);

                    if (!startPos || !endPos) return;

                    const range = document.createRange();
                    range.setStart(startPos.node, startPos.offset);
                    range.setEnd(endPos.node, endPos.offset);

                    // Create highlight mark element
                    const mark = document.createElement('mark');
                    mark.className = 'case-highlight';
                    mark.dataset.highlightId = h.id;
                    mark.dataset.tag = h.tag;
                    mark.style.backgroundColor = h.color + '40';
                    mark.style.borderBottom = '2px solid ' + h.color;
                    mark.style.cursor = 'pointer';

                    // Wrap the range
                    range.surroundContents(mark);

                    // Add click handler to open editor
                    mark.addEventListener('click', function(e) {{
                        e.stopPropagation();
                        emitEvent('highlight_clicked', {{ highlightId: h.id }});
                    }});
                }} catch (e) {{
                    // Range may cross element boundaries - skip this highlight
                    console.warn('Could not apply highlight:', h.id, e);
                }}
            }});
        """,
            timeout=5.0,
        )

    async def _render_case_content(container: ui.element) -> None:
        """Render case HTML."""
        container.clear()

        data = current_case.get("data")
        if not data or not isinstance(data, ParsedRTF):
            with container:
                ui.label("Select a case to view").classes("text-grey")
            return

        parsed = data

        # SECURITY: RTF files must come from trusted sources (CaseLaw NSW).
        # If user uploads are ever allowed, implement allowlist-based sanitization.
        with container:
            ui.html(parsed.html, sanitize=False)

        # Apply highlight markers after rendering
        await _apply_highlights_to_content(container)

    async def load_selected_case() -> None:
        """Load the currently selected case."""
        case_id = case_select.value
        if not case_id:
            return

        parsed = _load_case(case_id)
        if not parsed:
            ui.notify(f"Failed to load case: {case_id}", type="negative")
            return

        current_case.update({"id": case_id, "data": parsed})
        await _render_case_content(content_container)
        await refresh_sidebar()

        # Set up JS event handlers after content is rendered
        await _setup_selection_handlers(content_container)

    case_select.on("update:model-value", lambda _: load_selected_case())

    def handle_selection(e: GenericEventArguments) -> None:
        """Handle text selection event."""
        text = e.args.get("text", "")
        start = e.args.get("start", 0)
        end = e.args.get("end", 0)
        client_x = e.args.get("clientX", 0)
        client_y = e.args.get("clientY", 0)
        para_num = e.args.get("paraNum")
        header = e.args.get("header")

        if not isinstance(text, str) or not text.strip():
            return
        if not isinstance(start, int) or not isinstance(end, int):
            return

        selection_state.update(
            {
                "text": text,
                "start": start,
                "end": end,
                "para_num": para_num,
                "header": header,
            }
        )

        # Show floating menu near selection
        ui.run_javascript(f"""
            const menu = document.getElementById('floating-tag-menu');
            menu.style.left = '{client_x}px';
            menu.style.top = '{client_y + 10}px';
            menu.classList.add('visible');
        """)

    async def handle_highlight_click(e: GenericEventArguments) -> None:
        """Handle click on existing highlight."""
        highlight_id = e.args.get("highlightId")
        if not highlight_id or not current_case.get("id"):
            return

        h = await get_highlight_by_id(UUID(highlight_id))
        if h:
            editing_highlight["highlight"] = h
            comment_input.value = ""
            await _populate_comment_dialog(h)
            comment_dialog.open()

    ui.on("text_selected", handle_selection)
    ui.on("highlight_clicked", handle_highlight_click)

    # Hide floating menu on click elsewhere
    ui.on(
        "click",
        lambda _: ui.run_javascript(
            'document.getElementById("floating-tag-menu").classList.remove("visible")'
        ),
    )

    # Keyboard shortcuts
    async def handle_keydown(e: GenericEventArguments) -> None:
        key = e.args.get("key", "")
        if key in TAG_SHORTCUTS and selection_state.get("text"):
            tag = TAG_SHORTCUTS[key]
            await _apply_tag_to_selection(tag)
            await ui.run_javascript(
                'document.getElementById("floating-tag-menu").classList.remove("visible")'
            )

    ui.on("keydown", handle_keydown)

    # Wait for connection and load initial case
    await ui.context.client.connected()

    if cases:
        await load_selected_case()


async def _setup_selection_handlers(container: ui.element) -> None:
    """Set up JavaScript selection handlers on the content container."""
    container_id = container.id
    await ui.run_javascript(rf"""
        const container = getHtmlElement({container_id});
        if (!container) return;

        // Remove existing handlers
        if (container._selectionHandler) {{
            container.removeEventListener('mouseup', container._selectionHandler);
        }}

        container._selectionHandler = function(e) {{
            setTimeout(() => {{
                const selection = window.getSelection();
                if (selection.isCollapsed) return;

                const text = selection.toString().trim();
                if (!text) return;

                if (selection.rangeCount === 0) return;
                const range = selection.getRangeAt(0);
                if (!container.contains(range.commonAncestorContainer)) return;

                // Calculate offsets
                const preRange = document.createRange();
                preRange.selectNodeContents(container);
                preRange.setEnd(range.startContainer, range.startOffset);
                const start = preRange.toString().length;

                // Save range for potential highlighting
                window._savedRange = range.cloneRange();

                // Find paragraph number: look for ancestor <li> in an <ol>
                let paraNum = null;
                let node = range.startContainer;
                while (node && node !== container) {{
                    if (node.nodeName === 'LI') {{
                        const ol = node.closest('ol');
                        if (ol) {{
                            const start = ol.getAttribute('start') || '1';
                            const startNum = parseInt(start, 10);
                            const idx = Array.from(ol.children).indexOf(node);
                            paraNum = startNum + idx;
                        }}
                        break;
                    }}
                    node = node.parentNode;
                }}

                // Fallback: manual paragraph numbers [1], (1), or 1.
                if (paraNum === null) {{
                    let pNode = range.startContainer;
                    while (pNode && pNode !== container) {{
                        if (pNode.nodeName === 'P' || pNode.nodeName === 'DIV') {{
                            const pText = pNode.textContent.trim();
                            const re = /^(?:\[(\d+)\]|\((\d+)\)|(\d+)\.)\s/;
                            const match = pText.match(re);
                            if (match) {{
                                const num = match[1] || match[2] || match[3];
                                paraNum = parseInt(num, 10);
                            }}
                            break;
                        }}
                        pNode = pNode.parentNode;
                    }}
                }}

                // Find nearest preceding header (bold uppercase)
                let header = null;
                const sel = 'b, h1, h2, h3, h4, h5, h6';
                const headers = container.querySelectorAll(sel);
                for (const h of headers) {{
                    const hText = h.textContent.trim();
                    // Uppercase heading like JUDGMENT, GROUNDS OF APPEAL
                    if (hText === hText.toUpperCase() && hText.length > 3) {{
                        // Check if header comes before our selection
                        const hRange = document.createRange();
                        hRange.selectNodeContents(h);
                        const cmp = range.compareBoundaryPoints(
                            Range.START_TO_START, hRange);
                        if (cmp >= 0) {{
                            header = hText;
                        }} else {{
                            break;
                        }}
                    }}
                }}

                emitEvent('text_selected', {{
                    text: text,
                    start: start,
                    end: start + text.length,
                    clientX: e.clientX,
                    clientY: e.clientY,
                    paraNum: paraNum,
                    header: header
                }});
            }}, 10);
        }};

        container.addEventListener('mouseup', container._selectionHandler);

        // Only add keydown listener once
        if (!window._caseToolKeydownAdded) {{
            window._caseToolKeydownAdded = true;
            document.addEventListener('keydown', function(e) {{
                if (['1','2','3','4','5','6','7','8','9','0'].includes(e.key)) {{
                    emitEvent('keydown', {{ key: e.key }});
                }}
            }});
        }}
    """)
