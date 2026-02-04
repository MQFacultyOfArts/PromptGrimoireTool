#!/usr/bin/env python3
"""Spike A: Test js_handler for clipboard HTML access.

Run: uv run python scripts/spike_js_handler.py
Then: Open http://localhost:8081, paste HTML content

Success criteria:
1. Can access text/html MIME type from clipboard
2. Works in Chrome, Firefox, Safari
3. No permission dialogs block the flow
"""

from typing import TYPE_CHECKING

from nicegui import ui

if TYPE_CHECKING:
    from nicegui.events import GenericEventArguments


def main() -> None:
    ui.label("Spike A: js_handler Clipboard Test").classes("text-2xl font-bold mb-4")

    ui.label("Instructions:").classes("font-bold")
    ui.label("1. Copy HTML from a chatbot (Claude, ChatGPT, etc.)")
    ui.label("2. Click in the paste target area below")
    ui.label("3. Press Ctrl+V / Cmd+V to paste")
    ui.label("4. Check the extracted HTML and text below")

    html_output = ui.code("(paste to see HTML)", language="html").classes("w-full h-48")
    text_output = ui.code("(paste to see plain text)", language="text").classes(
        "w-full h-24"
    )

    def handle_paste(e: GenericEventArguments) -> None:
        html_content = e.args.get("html", "")
        text_content = e.args.get("text", "")

        html_output.content = html_content or "(no HTML in clipboard)"
        text_output.content = text_content or "(no text in clipboard)"

        print("\n=== Paste Event ===")
        print(f"HTML length: {len(html_content)}")
        print(f"Text length: {len(text_content)}")
        print(f"HTML preview: {html_content[:500]}")
        print("=== End ===\n")

    ui.on("clipboard_paste", handle_paste)

    # Paste target area with js_handler
    paste_area = ui.textarea(
        placeholder="Click here and paste (Ctrl+V / Cmd+V)..."
    ).classes("w-full h-32 my-4")

    # Inject JavaScript to capture paste event
    ui.run_javascript(f'''
        const textarea = document.querySelector('[id="{paste_area.id}"] textarea');
        if (textarea) {{
            textarea.addEventListener('paste', (event) => {{
                const html = event.clipboardData.getData('text/html');
                const text = event.clipboardData.getData('text/plain');
                emitEvent('clipboard_paste', {{ html: html || '', text: text || '' }});
                event.preventDefault();
            }});
        }}
    ''')

    ui.label("Evaluation checklist:").classes("font-bold mt-8")
    ui.label("[ ] text/html MIME type accessible")
    ui.label("[ ] Works in Chrome")
    ui.label("[ ] Works in Firefox")
    ui.label("[ ] Works in Safari")
    ui.label("[ ] No permission dialogs")
    ui.label("[ ] HTML structure intact")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(main, title="Spike A: js_handler", port=8081)
