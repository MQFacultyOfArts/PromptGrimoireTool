# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "nicegui>=3.6.1",
# ]
# ///
"""Minimal repro: NiceGUI 3.7.x destroys client-side DOM mods.

Text should have alternating pink/blue character backgrounds.
Click the button to trigger a server-side element update.
In 3.7.x the coloring disappears. In 3.6.1 it stays.

Usage (standalone, no project needed):
    uv run repro.py                          # latest nicegui
    uv run --with nicegui==3.6.1 repro.py    # works
    uv run --with nicegui==3.7.1 repro.py    # broken
"""

import importlib.metadata
import json

import nicegui
from nicegui import ui


def _nicegui_version_label() -> str:
    """Return version string including git source if installed from a branch."""
    version = nicegui.__version__
    try:
        dist = importlib.metadata.distribution("nicegui")
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            info = json.loads(direct_url)
            vcs = info.get("vcs_info", {})
            ref = vcs.get("requested_revision", "")
            commit = vcs.get("commit_id", "")[:8]
            if ref:
                return f"NiceGUI {version} ({ref} @ {commit})"
    except Exception:
        pass
    return f"NiceGUI {version}"


@ui.page("/")
def index():
    ui.label(_nicegui_version_label()).classes("text-h5")
    ui.label("Text below has alternating pink/blue chars.")
    ui.label("Click the button. In 3.7.x the color vanishes.")

    ui.html(
        "<p>Hello world sample text for char spans</p>",
        sanitize=False,
    ).props('id="target"')

    # Inject styled spans wrapping each character
    ui.run_javascript("""
        const el = document.getElementById('target');
        if (!el) return;
        let idx = 0;
        function wrap(node) {
            if (node.nodeType === Node.TEXT_NODE) {
                const frag = document.createDocumentFragment();
                for (const ch of node.textContent) {
                    const s = document.createElement('span');
                    s.dataset.charIndex = idx;
                    s.style.backgroundColor =
                        idx % 2 === 0 ? '#ffcccc' : '#ccccff';
                    s.textContent = ch;
                    idx++;
                    frag.appendChild(s);
                }
                node.parentNode.replaceChild(frag, node);
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                Array.from(node.childNodes).forEach(wrap);
            }
        }
        Array.from(el.childNodes).forEach(wrap);
        console.log('[REPRO] Injected ' + idx + ' spans');
    """)

    # Button triggers a server-side element update
    target = ui.label("I am visible").classes("text-lg")

    def on_click() -> None:
        target.set_visibility(not target.visible)

    ui.button(
        "Toggle (triggers server update)",
        on_click=on_click,
    )


ui.run(port=8090, show=False, reload=False)
