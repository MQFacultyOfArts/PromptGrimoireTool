"""Text selection demo page.

Demonstrates browser text selection capture for annotations.
Users can select text, see selection data, and create visual highlights.

Route: /demo/text-selection
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from nicegui import app, ui

from promptgrimoire.pages.layout import require_demo_enabled
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from nicegui.events import GenericEventArguments

# Path to CSS file
_CSS_FILE = Path(__file__).parent.parent / "static" / "annotations.css"

# Constants
SELECTION_DEBOUNCE_MS = 10  # Debounce to let browser finalize selection
MAX_DISPLAY_LENGTH = 50  # Truncate displayed text for readability

_CREATE_HIGHLIGHT_JS = """
    if (window._savedRange) {
        const span = document.createElement('span');
        span.className = 'annotation-highlight';
        span.setAttribute('data-testid', 'highlight');
        try {
            window._savedRange.surroundContents(span);
            window._savedRange = null;
            return {success: true};
        } catch (e) {
            // surroundContents fails if range spans multiple elements
            console.warn('surroundContents failed:', e.message);
            try {
                // Fall back to extractContents approach
                const fragment = window._savedRange.extractContents();
                span.appendChild(fragment);
                window._savedRange.insertNode(span);
                window._savedRange = null;
                return {success: true};
            } catch (e2) {
                console.error('Highlight fallback failed:', e2.message);
                return {success: false, error: e2.message};
            }
        }
    }
    return {success: false, error: 'No saved range'};
"""


def _get_session_user() -> dict | None:
    """Get the current user from session storage."""
    return app.storage.user.get("auth_user")


async def _create_highlight_from_selection(
    selection_data: dict[str, str | int],
) -> None:
    """Apply highlight CSS to the saved selection range via client-side JS."""
    if not selection_data.get("text"):
        ui.notify("No text selected", type="warning")
        return

    result = await ui.run_javascript(_CREATE_HIGHLIGHT_JS)
    if result and result.get("success"):
        ui.notify("Highlight created!")
    else:
        error = result.get("error", "Unknown error") if result else "No result"
        ui.notify(f"Highlight failed: {error}", type="warning")


def _validate_selection_args(
    text: object, start: object, end: object
) -> tuple[str, int, int, str] | None:
    """Validate raw ``text_selected`` event args and compute the display string.

    Returns None when the event should be ignored: wrong argument types, an
    invalid (negative or inverted) range, or empty text. Otherwise returns
    ``(text, start, end, display)``.
    """
    if (
        not isinstance(text, str)
        or not isinstance(start, int)
        or not isinstance(end, int)
    ):
        return None
    if start < 0 or end < 0 or start > end:
        return None
    if not text:
        return None
    display = (
        f'"{text[:MAX_DISPLAY_LENGTH]}..."'
        if len(text) > MAX_DISPLAY_LENGTH
        else f'"{text}"'
    )
    return text, start, end, display


def _handle_text_selected_event(
    e: GenericEventArguments, selection_data: dict[str, str | int]
) -> None:
    """Update ``selection_data`` and notify from a ``text_selected`` event.

    Expected e.args:
        text (str): Selected text content
        start (int): Start offset within container
        end (int): End offset within container
    """
    parsed = _validate_selection_args(
        e.args.get("text", ""), e.args.get("start", 0), e.args.get("end", 0)
    )
    if parsed is None:
        return
    text, start, end, display = parsed
    selection_data.update(
        {"text": text, "start": start, "end": end, "display": display}
    )
    ui.notify(f"Selected: {display}")


@page_route(
    "/demo/text-selection",
    title="Text Selection",
    icon="text_fields",
    category="demo",
    requires_demo=True,
    order=10,
)
async def text_selection_demo_page() -> None:
    """Demo page: Text selection for annotations."""
    if not require_demo_enabled():
        return

    # Require authentication
    user = _get_session_user()
    if not user:
        ui.navigate.to("/login")
        return

    # Per-page selection state bound to UI
    selection_data: dict[str, str | int] = {
        "text": "",
        "start": 0,
        "end": 0,
        "display": "No selection",
    }

    # Load CSS from external file
    ui.add_css(_CSS_FILE)

    # Page header
    ui.label("Text Selection Demo").classes("text-h5")
    ui.label("Select text below to capture it, then click to highlight.").classes(
        "text-caption text-grey"
    )

    with ui.row().classes("w-full gap-4 mt-4"):
        # Left panel: Selectable content
        with ui.card().classes("w-2/3"):
            ui.label("Sample Content").classes("text-h6")
            # Create container with data-testid for testing
            content_container = (
                ui.element("div")
                .classes("selectable-content")
                .props('data-testid="selectable-content"')
            )
            with content_container:
                # WARNING: sanitize=False is ONLY safe for static/trusted content.
                # NEVER use with user-provided content - enables XSS attacks.
                ui.html(
                    """
                    <p>This is a sample conversation for the PromptGrimoire demo.</p>
                    <p>Human: What is the capital of France?</p>
                    <p>Assistant: The capital of France is Paris. It is known for
                       the Eiffel Tower, the Louvre Museum, and its rich cultural
                       heritage.</p>
                    <p>Human: Tell me more about the Louvre.</p>
                    <p>Assistant: The Louvre is the world's largest art museum and
                       a historic monument in Paris. It houses approximately 380,000
                       objects and displays 35,000 works of art.</p>
                    """,
                    sanitize=False,
                )

        # Right panel: Selection info
        with ui.card().classes("w-1/3"):
            ui.label("Selection Info").classes("text-h6")

            # Bind labels to selection_data dictionary
            ui.label().bind_text_from(selection_data, "display").props(
                'data-testid="selected-text"'
            )
            ui.label().bind_text_from(
                selection_data, "start", backward=lambda s: f"Start: {s if s else '-'}"
            ).props('data-testid="start-offset"')
            ui.label().bind_text_from(
                selection_data, "end", backward=lambda e: f"End: {e if e else '-'}"
            ).props('data-testid="end-offset"')

            async def create_highlight() -> None:
                """Apply highlight CSS to saved selection range."""
                await _create_highlight_from_selection(selection_data)

            ui.button("Create Highlight", on_click=create_highlight).props(
                'data-testid="create-highlight-btn"'
            ).classes("mt-4")

    def handle_selection(e: GenericEventArguments) -> None:
        """Handle text selection from browser."""
        _handle_text_selected_event(e, selection_data)

    ui.on("text_selected", handle_selection)

    # Wait for WebSocket connection before running JavaScript
    await ui.context.client.connected()

    # Set up selection handler using NiceGUI element ID
    container_id = content_container.id
    await ui.run_javascript(f"""
        const container = getHtmlElement({container_id});
        const DEBOUNCE_MS = {SELECTION_DEBOUNCE_MS};

        function checkAndEmitSelection() {{
            const selection = window.getSelection();
            if (selection.isCollapsed) return;

            const text = selection.toString().trim();
            if (!text) return;

            // Check if selection is within our container
            if (selection.rangeCount === 0) return;
            const range = selection.getRangeAt(0);
            if (!container.contains(range.commonAncestorContainer)) return;

            // Save range for later highlighting (clone it since selection can change)
            // NOTE: Range objects become invalid if DOM changes. For production,
            // consider storing text offsets and reconstructing the range on highlight.
            window._savedRange = range.cloneRange();

            // Calculate offsets relative to container
            const preRange = document.createRange();
            preRange.selectNodeContents(container);
            preRange.setEnd(range.startContainer, range.startOffset);
            const start = preRange.toString().length;

            emitEvent('text_selected', {{
                text: text,
                start: start,
                end: start + text.length
            }});
        }}

        container.addEventListener('mouseup', function(e) {{
            setTimeout(checkAndEmitSelection, DEBOUNCE_MS);
        }});

        // Mark handlers as ready for testing
        container.setAttribute('data-handlers-ready', 'true');
    """)
