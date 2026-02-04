#!/usr/bin/env python3
"""Spike D: Test if ui.editor preserves HTML on paste.

Run: uv run python scripts/spike_ui_editor.py
Then: Open http://localhost:8080, paste HTML from a chatbot export

Success criteria:
1. Paste from Claude/ChatGPT preserves structure (headings, paragraphs)
2. editor.value returns HTML string we can process
3. No browser normalization issues
"""

from nicegui import ui


def main() -> None:
    ui.label("Spike D: ui.editor HTML Paste Test").classes("text-2xl font-bold mb-4")

    ui.label("Instructions:").classes("font-bold")
    ui.label("1. Copy HTML from a chatbot (Claude, ChatGPT, etc.)")
    ui.label("2. Paste into the editor below")
    ui.label("3. Click 'Extract HTML' to see the raw HTML")
    ui.label("4. Check if structure is preserved")

    editor = ui.editor(placeholder="Paste HTML content here...").classes(
        "w-full h-64 my-4"
    )

    output = ui.code("", language="html").classes("w-full")

    def extract_html() -> None:
        html_content = editor.value or ""
        output.content = html_content
        print(f"\n=== Extracted HTML ({len(html_content)} chars) ===")
        print(html_content[:2000])  # First 2000 chars
        print("=== End ===\n")

    ui.button("Extract HTML", on_click=extract_html).classes("mt-4")

    ui.label("Evaluation checklist:").classes("font-bold mt-8")
    ui.label("[ ] Headings preserved (<h1>, <h2>, etc.)")
    ui.label("[ ] Paragraphs preserved (<p> tags)")
    ui.label("[ ] Lists preserved (<ul>, <ol>, <li>)")
    ui.label("[ ] Tables preserved (<table>, <tr>, <td>)")
    ui.label("[ ] No excessive wrapper divs added")
    ui.label("[ ] Speaker labels/turn markers visible")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(main, title="Spike D: ui.editor", port=8080)
