#!/usr/bin/env python3
"""Spike B: Test contenteditable div for HTML paste.

Run: uv run python scripts/spike_contenteditable.py
Then: Open http://localhost:8082, paste HTML content

Success criteria:
1. HTML paste preserves structure
2. innerHTML extraction works reliably
3. No excessive browser normalization
"""

from typing import TYPE_CHECKING

from nicegui import ui

if TYPE_CHECKING:
    from nicegui.events import GenericEventArguments


def main() -> None:
    ui.label("Spike B: Contenteditable Test").classes("text-2xl font-bold mb-4")

    ui.label("Instructions:").classes("font-bold")
    ui.label("1. Copy HTML from a chatbot (Claude, ChatGPT, etc.)")
    ui.label("2. Click in the contenteditable area below")
    ui.label("3. Paste (Ctrl+V / Cmd+V)")
    ui.label("4. Click 'Extract innerHTML' to see raw HTML")

    # Contenteditable div
    ui.html(
        """
        <div id="paste-target" contenteditable="true"
             style="border: 2px dashed #ccc; min-height: 200px; padding: 16px;
                    background: #f9f9f9; margin: 16px 0;">
            Click here and paste HTML content...
        </div>
        """,
        sanitize=False,
    )

    output = ui.code("", language="html").classes("w-full h-64")

    def handle_extraction(e: GenericEventArguments) -> None:
        html_content = e.args.get("html", "")
        output.content = html_content
        print(f"\n=== innerHTML ({len(html_content)} chars) ===")
        print(html_content[:2000])
        print("=== End ===\n")

    ui.on("content_extracted", handle_extraction)

    def extract_html() -> None:
        ui.run_javascript("""
            const div = document.getElementById('paste-target');
            emitEvent('content_extracted', { html: div.innerHTML });
        """)

    ui.button("Extract innerHTML", on_click=extract_html).classes("mt-4")

    ui.label("Evaluation checklist:").classes("font-bold mt-8")
    ui.label("[ ] Structure preserved after paste")
    ui.label("[ ] innerHTML extraction works")
    ui.label("[ ] No excessive wrapper elements")
    ui.label("[ ] Cursor/selection behavior acceptable")
    ui.label("[ ] Works across browsers")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(main, title="Spike B: Contenteditable", port=8082)
