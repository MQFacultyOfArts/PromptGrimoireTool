"""Text selection demo page.

Demonstrates browser text selection capture for annotations.
Users can select text, see selection data, and create visual highlights.

Route: /demo/text-selection
"""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

# Path to CSS file
_CSS_FILE = Path(__file__).parent.parent / "static" / "annotations.css"


@ui.page("/demo/text-selection")
async def text_selection_demo_page() -> None:
    """Demo page: Text selection for annotations."""
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
                if not selection_data.get("text"):
                    ui.notify("No text selected", type="warning")
                    return

                result = await ui.run_javascript("""
                    if (window._savedRange) {
                        const span = document.createElement('span');
                        span.className = 'annotation-highlight';
                        span.setAttribute('data-testid', 'highlight');
                        try {
                            window._savedRange.surroundContents(span);
                            window._savedRange = null;
                            return true;
                        } catch (e) {
                            // surroundContents fails if range spans multiple elements
                            // Fall back to extractContents approach
                            const fragment = window._savedRange.extractContents();
                            span.appendChild(fragment);
                            window._savedRange.insertNode(span);
                            window._savedRange = null;
                            return true;
                        }
                    }
                    return false;
                """)
                if result:
                    ui.notify("Highlight created!")
                else:
                    ui.notify("No saved selection to highlight", type="warning")

            ui.button("Create Highlight", on_click=create_highlight).props(
                'data-testid="create-highlight-btn"'
            ).classes("mt-4")

    def handle_selection(e) -> None:
        """Handle text selection from browser."""
        text = e.args.get("text", "")
        start = e.args.get("start", 0)
        end = e.args.get("end", 0)

        if text:
            display = f'"{text[:50]}..."' if len(text) > 50 else f'"{text}"'
            selection_data.update(
                {"text": text, "start": start, "end": end, "display": display}
            )
            ui.notify(f"Selected: {display}")

    ui.on("text_selected", handle_selection)

    # Wait for WebSocket connection before running JavaScript
    await ui.context.client.connected()

    # Set up selection handler using NiceGUI element ID
    container_id = content_container.id
    await ui.run_javascript(f"""
        const container = getHtmlElement({container_id});

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
            setTimeout(checkAndEmitSelection, 10);
        }});
    """)
