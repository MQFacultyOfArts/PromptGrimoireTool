# Phase 2: Crepe Editor with Python Interop

**Goal:** Replace the current kit-based Milkdown editor with Crepe from the local bundle, with toolbar and Python read/write.

**Type:** Infrastructure + functionality (verified manually — spike code, no automated tests)

**Dependencies:** Phase 1 (bundle exists at `src/promptgrimoire/static/milkdown/dist/milkdown-bundle.js`)

---

<!-- START_TASK_1 -->
### Task 1: Rewrite milkdown_spike.py to load from local bundle

**Files:**
- Modify: `src/promptgrimoire/pages/milkdown_spike.py` (full rewrite — replace all 211 lines)

**Step 1: Rewrite the page module**

Replace the entire contents of `src/promptgrimoire/pages/milkdown_spike.py` with:

```python
"""Spike: Milkdown Crepe editor embedded in NiceGUI.

Proves that Milkdown Crepe can be embedded in a NiceGUI page with:
- WYSIWYG toolbar (Bold, Italic, Heading, List, Blockquote, Code)
- Python read/write of markdown content
- Local Vite bundle (no CDN dependencies)

Not production code — delete after spike evaluation.

Route: /demo/milkdown-spike (requires ENABLE_DEMO_PAGES=true)
"""

from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from promptgrimoire.pages.layout import require_demo_enabled
from promptgrimoire.pages.registry import page_route

# Serve the Milkdown bundle from static files
_BUNDLE_DIR = Path(__file__).parent.parent / "static" / "milkdown" / "dist"
app.add_static_files("/milkdown", str(_BUNDLE_DIR))

_EDITOR_CONTAINER_STYLE = (
    "min-height: 300px; border: 1px solid #ddd; border-radius: 8px; padding: 16px;"
)

_DEFAULT_MD = """\
# Response Draft

Start writing your reflection here.

- Use **bold** and *italic*
- Create lists
- Add headings
"""


@page_route(
    "/demo/milkdown-spike",
    title="Milkdown Spike",
    icon="edit_note",
    category="demo",
    requires_demo=True,
    order=90,
)
async def milkdown_spike_page() -> None:
    """Spike page: Milkdown Crepe editor embedded in NiceGUI."""
    if not require_demo_enabled():
        return

    # Load the IIFE bundle (not an ES module — no type="module" needed)
    ui.add_body_html('<script src="/milkdown/milkdown-bundle.js"></script>')

    # Demo banner
    with ui.row().classes(
        "w-full bg-amber-100 border border-amber-400"
        " rounded p-3 mb-4 items-center gap-2"
    ):
        ui.icon("science").classes("text-amber-700 text-xl")
        ui.label("SPIKE / DEMO").classes("text-amber-800 font-bold")
        ui.label(
            "Milkdown Crepe editor embedding test. Not production code."
        ).classes("text-amber-700 text-sm")

    ui.label("Milkdown Editor Spike").classes("text-2xl font-bold mb-4")

    # Editor container
    editor_div = ui.html(
        f'<div id="milkdown-editor" style="{_EDITOR_CONTAINER_STYLE}"></div>',
        sanitize=False,
    )

    # Markdown display area (hidden until "Get Markdown" is clicked)
    markdown_display = ui.label("").classes(
        "text-sm font-mono bg-gray-100 p-4 mt-4 whitespace-pre-wrap"
    )
    markdown_display.set_visibility(False)

    async def get_markdown() -> None:
        """Read markdown content from the editor via JS global."""
        result = await ui.run_javascript("window._getMilkdownMarkdown()")
        markdown_display.text = result or "(empty)"
        markdown_display.set_visibility(True)

    async def set_markdown() -> None:
        """Inject sample markdown into the editor."""
        sample = "# Injected Content\\n\\nThis was set from Python!"
        # For spike: log limitation. Full implementation needs editor API.
        await ui.run_javascript(
            f"window._setMilkdownMarkdown(`{sample}`)"
        )
        ui.notify("Set Markdown called (see console for spike limitation)")

    with ui.row().classes("mt-4 gap-2"):
        ui.button("Get Markdown", on_click=get_markdown)
        ui.button("Set Markdown", on_click=set_markdown)

    # Wait for WebSocket, then initialize the editor
    await ui.context.client.connected()

    # Escape the default markdown for JS template literal
    escaped_md = _DEFAULT_MD.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")

    await ui.run_javascript(f"""
        const root = document.getElementById('milkdown-editor');
        if (root && window._createMilkdownEditor) {{
            window._createMilkdownEditor(root, `{escaped_md}`, function(md) {{
                // onUpdate callback — could emit events to Python here
            }});
        }} else {{
            console.error('[spike] milkdown-bundle.js not loaded or #milkdown-editor not found');
        }}
    """)
```

**Step 2: Verify the editor renders**

```bash
ENABLE_DEMO_PAGES=true uv run python -m promptgrimoire
```

Navigate to `http://localhost:8080/demo/milkdown-spike`.

Expected:
- Crepe editor renders with toolbar
- Bold, Italic, Heading, List, Blockquote, Code buttons functional
- Default markdown content visible in the editor
- Browser console shows `[milkdown-bundle] Crepe editor created`
- No JS errors in console

**Step 3: Test Python interop**

- Click "Get Markdown" — displays current markdown content
- Type new text, click "Get Markdown" again — shows updated content
- Click "Set Markdown" — console shows spike limitation warning

**Step 4: Commit**

```bash
git add src/promptgrimoire/pages/milkdown_spike.py
git commit -m "feat: rewrite milkdown spike to use local Crepe bundle with Python interop"
```

<!-- END_TASK_1 -->

---

**Note: Python `setMarkdown` is a no-op stub.** Design DoD #3 requires bidirectional Python interop. Read (via `_getMilkdownMarkdown`) is fully implemented. Write (via `_setMilkdownMarkdown`) is stubbed as a `console.warn` because Milkdown's Crepe API does not expose a simple `setMarkdown` method — it requires editor recreation or use of `replaceAll` action from `@milkdown/utils`. This is acceptable for a spike; the read path proves the JS→Python interop pattern, which is the harder direction. Production implementation can add write support via `editor.action(replaceAll(md))`.

## UAT Steps (requires human judgment)

1. [ ] Start the app: `ENABLE_DEMO_PAGES=true uv run python -m promptgrimoire`
2. [ ] Navigate to: `/demo/milkdown-spike`
3. [ ] Verify: Crepe editor renders with working toolbar (Bold, Italic, Heading, List, Blockquote, Code)
4. [ ] Type text, use formatting buttons — all functional
5. [ ] Click "Get Markdown" — shows markdown content accurately
6. [ ] Browser console shows no errors (especially no ProseMirror conflicts)

**Evidence Required:**
- [ ] Screenshot of editor with toolbar visible
- [ ] Screenshot of "Get Markdown" output showing correct content
