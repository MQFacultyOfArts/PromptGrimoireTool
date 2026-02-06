"""Spike: Milkdown markdown editor embedded in NiceGUI.

Proves that Milkdown can be embedded in a NiceGUI page and that
we can read/write markdown content between Python and the editor.

Not production code — delete after spike evaluation.

STATUS: WIP
- Milkdown renders and is editable via @milkdown/kit (low-level API)
- No toolbar/formatting buttons yet (needs Crepe features or
  individual plugin imports - Crepe breaks on esm.sh due to
  static CodeMirror import)
- Multi-client sync not yet wired (next step)
- Import map approach works for initial page load but
  ui.run_javascript() may not resolve import maps — need to
  move init code into a <script type="module"> tag instead

NEXT STEPS:
1. Move init JS from ui.run_javascript() to <script type="module">
   in ui.add_body_html() so import maps are respected
2. Wire multi-client broadcast (see sync_demo.py pattern)
3. Either bundle Milkdown locally (esbuild) to get Crepe toolbar,
   or import feature plugins individually via esm.sh
4. Test Milkdown collab plugin with pycrdt for real CRDT sync
"""

from nicegui import ui

from promptgrimoire.pages.layout import require_demo_enabled
from promptgrimoire.pages.registry import page_route

_EDITOR_CONTAINER_STYLE = (
    "min-height: 300px; border: 1px solid #ddd; border-radius: 8px; padding: 16px;"
)

_DEFAULT_MD = (
    "# Response Draft\n\n"
    "Start writing your reflection here.\n\n"
    "- Use **bold** and *italic*\n"
    "- Create lists\n"
    "- Add headings\n"
)

_DEFAULT_MD_JS = (
    _DEFAULT_MD.replace("\\", "\\\\")
    .replace("`", "\\`")
    .replace("$", "\\$")
    .replace("\n", "\\n")
)

# Everything in one <script type="module"> block so import maps
# are respected. ui.run_javascript() uses an indirect execution
# mechanism that cannot resolve bare specifiers from import maps.
_MILKDOWN_MODULE = f"""\
<script type="importmap">
{{
  "imports": {{
    "@milkdown/kit/core": "https://esm.sh/@milkdown/kit@7.18.0/core",
    "@milkdown/kit/preset/commonmark": "https://esm.sh/@milkdown/kit@7.18.0/preset/commonmark",
    "@milkdown/plugin-history": "https://esm.sh/@milkdown/plugin-history@7.18.0",
    "@milkdown/plugin-listener": "https://esm.sh/@milkdown/plugin-listener@7.18.0"
  }}
}}
</script>
<style>
  #milkdown-editor .ProseMirror {{
    outline: none;
    min-height: 250px;
    font-family: sans-serif;
    line-height: 1.6;
  }}
  #milkdown-editor .ProseMirror h1,
  #milkdown-editor .ProseMirror h2,
  #milkdown-editor .ProseMirror h3 {{
    font-weight: bold; margin: 0.5em 0;
  }}
  #milkdown-editor .ProseMirror h1 {{ font-size: 1.8em; }}
  #milkdown-editor .ProseMirror h2 {{ font-size: 1.4em; }}
  #milkdown-editor .ProseMirror h3 {{ font-size: 1.2em; }}
  #milkdown-editor .ProseMirror p {{ margin: 0.5em 0; }}
  #milkdown-editor .ProseMirror ul,
  #milkdown-editor .ProseMirror ol {{
    padding-left: 1.5em; margin: 0.5em 0;
  }}
  #milkdown-editor .ProseMirror li {{ margin: 0.2em 0; }}
  #milkdown-editor .ProseMirror strong {{ font-weight: bold; }}
  #milkdown-editor .ProseMirror em {{ font-style: italic; }}
  #milkdown-editor .ProseMirror blockquote {{
    border-left: 3px solid #ddd;
    padding-left: 1em;
    color: #666; margin: 0.5em 0;
  }}
  #milkdown-editor .ProseMirror code {{
    background: #f5f5f5;
    padding: 0.1em 0.3em;
    border-radius: 3px;
    font-family: monospace;
  }}
  #milkdown-editor .ProseMirror pre {{
    background: #f5f5f5; padding: 0.8em;
    border-radius: 4px; overflow-x: auto;
  }}
  #milkdown-editor .ProseMirror pre code {{
    background: none; padding: 0;
  }}
  #milkdown-editor .ProseMirror hr {{
    border: none;
    border-top: 1px solid #ddd;
    margin: 1em 0;
  }}
</style>
<script type="module">
  import {{ Editor, rootCtx, defaultValueCtx }}
    from "@milkdown/kit/core";
  import {{ commonmark }}
    from "@milkdown/kit/preset/commonmark";
  import {{ history }}
    from "@milkdown/plugin-history";
  import {{ listener, listenerCtx }}
    from "@milkdown/plugin-listener";

  // Wait for the DOM element to exist
  function waitForElement(sel, cb) {{
    const el = document.querySelector(sel);
    if (el) {{ cb(el); return; }}
    const obs = new MutationObserver(function() {{
      const el = document.querySelector(sel);
      if (el) {{ obs.disconnect(); cb(el); }}
    }});
    obs.observe(document.body, {{childList: true, subtree: true}});
  }}

  waitForElement('#milkdown-editor', async function(root) {{
    let currentMarkdown = `{_DEFAULT_MD_JS}`;

    const editor = await Editor.make()
      .config(function(ctx) {{
        ctx.set(rootCtx, root);
        ctx.set(defaultValueCtx, `{_DEFAULT_MD_JS}`);
      }})
      .use(commonmark)
      .use(history)
      .use(listener)
      .config(function(ctx) {{
        ctx.get(listenerCtx)
          .markdownUpdated(function(c, md, prev) {{
            currentMarkdown = md;
          }});
      }})
      .create();

    console.log('[SPIKE] Milkdown editor created');
    window._milkdownEditor = editor;
    window._getMilkdownMarkdown = function() {{
      return currentMarkdown;
    }};
  }});
</script>
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
    """Spike page: Milkdown editor embedded in NiceGUI."""
    if not require_demo_enabled():
        return

    ui.add_body_html(_MILKDOWN_MODULE)

    # Demo banner
    with ui.row().classes(
        "w-full bg-amber-100 border border-amber-400"
        " rounded p-3 mb-4 items-center gap-2"
    ):
        ui.icon("science").classes("text-amber-700 text-xl")
        ui.label("SPIKE / DEMO").classes("text-amber-800 font-bold")
        ui.label(
            "Milkdown markdown editor embedding test. Not production code."
        ).classes("text-amber-700 text-sm")

    ui.label("Milkdown Editor Spike").classes("text-2xl font-bold mb-4")

    # Editor container
    ui.html(
        f'<div id="milkdown-editor" style="{_EDITOR_CONTAINER_STYLE}"></div>',
        sanitize=False,
    )

    # Python interop: read markdown back from the editor
    markdown_display = ui.label("").classes(
        "text-sm font-mono bg-gray-100 p-4 mt-4 whitespace-pre-wrap"
    )
    markdown_display.set_visibility(False)

    async def get_markdown() -> None:
        result = await ui.run_javascript("window._getMilkdownMarkdown()")
        markdown_display.text = result or "(empty)"
        markdown_display.set_visibility(True)

    ui.button(
        "Get Markdown from Editor",
        on_click=get_markdown,
    ).classes("mt-4")
