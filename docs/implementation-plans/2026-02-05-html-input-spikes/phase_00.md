# HTML Input Spikes Implementation Plan

**Goal:** Determine the best mechanism for HTML clipboard paste in NiceGUI

**Architecture:** Three competing approaches tested via minimal scripts

**Tech Stack:** NiceGUI, selectolax, Python 3.14

**Scope:** 1 phase (spikes only) - return to design after results

**Codebase verified:** 2026-02-05

---

## Overview

This phase contains exploratory spikes to determine which HTML input mechanism works best. No TDD - these are throwaway experiments.

**Priority order:**
1. **Spike D**: `ui.editor` - most NiceGUI-native, test first
2. **Spike A**: `js_handler` - fallback if D fails
3. **Spike B**: contenteditable - fallback if A has issues
4. **Spike S**: selectolax text iteration - needed regardless of input mechanism

**Decision criteria:**
- Does HTML structure survive paste? (headings, lists, tables)
- Can we extract clean HTML programmatically?
- Cross-browser compatibility (Chrome, Firefox, Safari)
- Minimal custom JavaScript

---

<!-- START_TASK_1 -->
### Task 1: Spike D - ui.editor HTML Paste

**Files:**
- Create: `scripts/spike_ui_editor.py`

**Step 1: Create the spike script**

```python
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

    editor = ui.editor(placeholder="Paste HTML content here...").classes("w-full h-64 my-4")

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


ui.run(main, title="Spike D: ui.editor", port=8080)
```

**Step 2: Run the spike**

```bash
uv run python scripts/spike_ui_editor.py
```

Open http://localhost:8080 in browser. Test with:
- Claude conversation export
- ChatGPT conversation export
- AustLII legal document

**Step 3: Record results**

Document in comments at top of script:
- SUCCESS: HTML structure preserved, `.value` returns usable HTML
- PARTIAL: Some structure lost, may need post-processing
- FAIL: Significant structure loss or browser issues

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Spike A - js_handler Clipboard Access

**Files:**
- Create: `scripts/spike_js_handler.py`

**Step 1: Create the spike script**

```python
#!/usr/bin/env python3
"""Spike A: Test js_handler for clipboard HTML access.

Run: uv run python scripts/spike_js_handler.py
Then: Open http://localhost:8081, paste HTML content

Success criteria:
1. Can access text/html MIME type from clipboard
2. Works in Chrome, Firefox, Safari
3. No permission dialogs block the flow
"""

from nicegui import ui
from nicegui.events import GenericEventArguments


def main() -> None:
    ui.label("Spike A: js_handler Clipboard Test").classes("text-2xl font-bold mb-4")

    ui.label("Instructions:").classes("font-bold")
    ui.label("1. Copy HTML from a chatbot (Claude, ChatGPT, etc.)")
    ui.label("2. Click in the paste target area below")
    ui.label("3. Press Ctrl+V / Cmd+V to paste")
    ui.label("4. Check the extracted HTML and text below")

    html_output = ui.code("(paste to see HTML)", language="html").classes("w-full h-48")
    text_output = ui.code("(paste to see plain text)", language="text").classes("w-full h-24")

    def handle_paste(e: GenericEventArguments) -> None:
        html_content = e.args.get("html", "")
        text_content = e.args.get("text", "")

        html_output.content = html_content or "(no HTML in clipboard)"
        text_output.content = text_content or "(no text in clipboard)"

        print(f"\n=== Paste Event ===")
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


ui.run(main, title="Spike A: js_handler", port=8081)
```

**Step 2: Run the spike**

```bash
uv run python scripts/spike_js_handler.py
```

Test in multiple browsers.

**Step 3: Record results**

Document browser compatibility and any issues.

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Spike B - Contenteditable Div

**Files:**
- Create: `scripts/spike_contenteditable.py`

**Step 1: Create the spike script**

```python
#!/usr/bin/env python3
"""Spike B: Test contenteditable div for HTML paste.

Run: uv run python scripts/spike_contenteditable.py
Then: Open http://localhost:8082, paste HTML content

Success criteria:
1. HTML paste preserves structure
2. innerHTML extraction works reliably
3. No excessive browser normalization
"""

from nicegui import ui
from nicegui.events import GenericEventArguments


def main() -> None:
    ui.label("Spike B: Contenteditable Test").classes("text-2xl font-bold mb-4")

    ui.label("Instructions:").classes("font-bold")
    ui.label("1. Copy HTML from a chatbot (Claude, ChatGPT, etc.)")
    ui.label("2. Click in the contenteditable area below")
    ui.label("3. Paste (Ctrl+V / Cmd+V)")
    ui.label("4. Click 'Extract innerHTML' to see raw HTML")

    # Contenteditable div
    content_div = ui.html('''
        <div id="paste-target" contenteditable="true"
             style="border: 2px dashed #ccc; min-height: 200px; padding: 16px;
                    background: #f9f9f9; margin: 16px 0;">
            Click here and paste HTML content...
        </div>
    ''')

    output = ui.code("", language="html").classes("w-full h-64")

    def extract_html() -> None:
        ui.run_javascript('''
            const div = document.getElementById('paste-target');
            emitEvent('content_extracted', { html: div.innerHTML });
        ''')

    def handle_extraction(e: GenericEventArguments) -> None:
        html_content = e.args.get("html", "")
        output.content = html_content
        print(f"\n=== innerHTML ({len(html_content)} chars) ===")
        print(html_content[:2000])
        print("=== End ===\n")

    ui.on("content_extracted", handle_extraction)
    ui.button("Extract innerHTML", on_click=extract_html).classes("mt-4")

    ui.label("Evaluation checklist:").classes("font-bold mt-8")
    ui.label("[ ] Structure preserved after paste")
    ui.label("[ ] innerHTML extraction works")
    ui.label("[ ] No excessive wrapper elements")
    ui.label("[ ] Cursor/selection behavior acceptable")
    ui.label("[ ] Works across browsers")


ui.run(main, title="Spike B: Contenteditable", port=8082)
```

**Step 2: Run the spike**

```bash
uv run python scripts/spike_contenteditable.py
```

**Step 3: Record results**

Document any browser normalization issues.

<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Spike S - selectolax Text Node Iteration

**Files:**
- Create: `scripts/spike_selectolax_text.py`

**Step 1: Create the spike script**

```python
#!/usr/bin/env python3
"""Spike S: Test selectolax text node iteration for char span injection.

Run: uv run python scripts/spike_selectolax_text.py

Success criteria:
1. Can iterate over text nodes in HTML
2. Can wrap each character in a span
3. Preserves HTML structure (headings, lists, tables)
4. Handles whitespace correctly
5. Handles <br> tags as newline chars
"""

from selectolax.lexbor import LexborHTMLParser


def inject_char_spans(html: str) -> tuple[str, int]:
    """Walk HTML DOM, wrap each text character in data-char-index span.

    Returns:
        (html_with_spans, total_char_count)
    """
    tree = LexborHTMLParser(html)
    char_index = 0

    # Find all text nodes
    def process_node(node):
        nonlocal char_index

        if node.tag == "-text":
            text = node.text() or ""
            if not text:
                return

            # Build replacement HTML with char spans
            spans = []
            for char in text:
                spans.append(f'<span class="char" data-char-index="{char_index}">{char}</span>')
                char_index += 1

            # Replace text node with spans
            # Note: This is a simplified approach - real implementation needs
            # to handle the replacement properly
            print(f"Text node: {repr(text[:50])} -> {len(text)} chars starting at {char_index - len(text)}")

    # Walk the tree
    for node in tree.root.traverse():
        process_node(node)

    return tree.html, char_index


def test_simple() -> None:
    """Test with simple HTML."""
    html = "<p>Hello <strong>world</strong>!</p>"
    print(f"\n=== Simple HTML ===")
    print(f"Input: {html}")
    result, count = inject_char_spans(html)
    print(f"Char count: {count}")


def test_nested() -> None:
    """Test with nested structure."""
    html = """
    <div>
        <h1>Title</h1>
        <p>First <em>paragraph</em> here.</p>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
    </div>
    """
    print(f"\n=== Nested HTML ===")
    result, count = inject_char_spans(html)
    print(f"Char count: {count}")


def test_whitespace() -> None:
    """Test whitespace handling."""
    html = "<p>Word1   Word2\n\tWord3</p>"
    print(f"\n=== Whitespace ===")
    print(f"Input: {repr(html)}")
    result, count = inject_char_spans(html)
    print(f"Char count: {count}")


def test_br_tags() -> None:
    """Test <br> tag handling."""
    html = "<p>Line 1<br>Line 2<br/>Line 3</p>"
    print(f"\n=== BR tags ===")
    print(f"Input: {html}")
    result, count = inject_char_spans(html)
    print(f"Char count: {count}")


def test_chatbot_sample() -> None:
    """Test with realistic chatbot HTML."""
    html = """
    <div class="conversation">
        <div class="turn user">
            <p>What is the capital of France?</p>
        </div>
        <div class="turn assistant">
            <p>The capital of France is <strong>Paris</strong>.</p>
            <p>Paris is known for:</p>
            <ul>
                <li>The Eiffel Tower</li>
                <li>The Louvre Museum</li>
                <li>Notre-Dame Cathedral</li>
            </ul>
        </div>
    </div>
    """
    print(f"\n=== Chatbot Sample ===")
    result, count = inject_char_spans(html)
    print(f"Char count: {count}")


if __name__ == "__main__":
    print("Spike S: selectolax Text Node Iteration")
    print("=" * 50)

    test_simple()
    test_nested()
    test_whitespace()
    test_br_tags()
    test_chatbot_sample()

    print("\n" + "=" * 50)
    print("Evaluation checklist:")
    print("[ ] Text nodes discovered correctly")
    print("[ ] Character indices are sequential")
    print("[ ] Whitespace characters counted")
    print("[ ] Structure preserved")
    print("[ ] BR tags handled")
```

**Step 2: Run the spike**

```bash
uv run python scripts/spike_selectolax_text.py
```

**Step 3: Record results**

This spike validates the char span injection approach regardless of which input mechanism wins.

<!-- END_TASK_4 -->

---

<!-- START_TASK_5 -->
### Task 5: Document Results and Recommend Approach

**Files:**
- Update: `docs/design-plans/2026-02-04-html-input-pipeline.md`

**Step 1: Run all spikes and collect results**

Run each spike, test with real chatbot exports, document findings.

**Step 2: Create results summary**

Add a new section to the design plan:

```markdown
## Spike Results (2026-02-XX)

### Spike D: ui.editor
- Status: SUCCESS / PARTIAL / FAIL
- Notes: [observations]

### Spike A: js_handler
- Status: SUCCESS / PARTIAL / FAIL
- Notes: [observations]

### Spike B: contenteditable
- Status: SUCCESS / PARTIAL / FAIL
- Notes: [observations]

### Spike S: selectolax text iteration
- Status: SUCCESS / PARTIAL / FAIL
- Notes: [observations]

### Recommendation
Based on spike results, the recommended approach is: [D/A/B]
Rationale: [why]
```

**Step 3: Return to design planning**

After documenting results, the next step is to:
1. Update the design plan with the winning approach
2. Create implementation plans for phases 1-8

<!-- END_TASK_5 -->

---

## UAT Steps

1. [ ] Run each spike script successfully
2. [ ] Test with real chatbot exports (Claude, ChatGPT)
3. [ ] Document results in design plan
4. [ ] Recommend winning approach

## Evidence Required

- [ ] Screenshot/recording of each spike working (or failing)
- [ ] Results summary in design plan
- [ ] Clear recommendation with rationale
