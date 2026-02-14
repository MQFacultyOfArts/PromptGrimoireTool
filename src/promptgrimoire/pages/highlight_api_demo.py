"""Demo: CSS Custom Highlight API proof-of-concept.

Proves two claims:
1. CSS Custom Highlight API ranges span across DOM block boundaries
   (p, h2, li, blockquote) without splitting or DOM modification.
   Uses workspace export of Lawlis v R [2025] NSWCCA 183 (pre-processed).
2. The same character offsets used for live highlighting feed directly
   into the PDF export pipeline (export_annotation_pdf) unchanged.

Route: /demo/highlight-api (requires ENABLE_DEMO_PAGES=true)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nicegui import ui

from promptgrimoire.export.pdf_export import export_annotation_pdf
from promptgrimoire.input_pipeline.html_input import extract_text_from_html
from promptgrimoire.pages.layout import require_demo_enabled
from promptgrimoire.pages.registry import page_route

logger = logging.getLogger(__name__)

# --- Fixture path (pre-processed workspace export, no pipeline needed) ---
_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "workspace_lawlis_v_r.html"
)

_CROSS_BLOCK_HIGHLIGHTS: list[dict[str, Any]] = []

_TAG_COLOURS = {
    "jurisdiction": "#3366cc",
    "legal_issues": "#cc3333",
    "legislation": "#339933",
    "evidence": "#cc9900",
}


def _render_header(
    tag_names: list[str],
    current_tag_idx: list[int],
) -> None:
    """Render page title, description, and tag selector buttons."""
    ui.label("CSS Custom Highlight API — Proof of Concept").classes("text-h4")
    ui.markdown(
        "**Fixture:** `workspace_lawlis_v_r.html` "
        "(Lawlis v R [2025] NSWCCA 183). "
        "Select text, click a tag. Highlights use the "
        "CSS Custom Highlight API — **no DOM modification**."
    )
    with ui.row().classes("gap-2 items-center"):
        ui.label("Tag:").classes("text-bold")
        for i, (tag, colour) in enumerate(_TAG_COLOURS.items()):
            ui.button(
                tag.replace("_", " ").title(),
                on_click=lambda _e, idx=i: _set_tag(idx),
            ).props(f'dense style="background-color: {colour}; color: white"')
        tag_label = ui.label(f"Active: {tag_names[0]}").classes("text-caption")

    def _set_tag(idx: int) -> None:
        current_tag_idx[0] = idx
        tag_label.set_text(f"Active: {tag_names[idx]}")


def _build_highlight_css() -> str:
    """Build CSS rules for ``::highlight()`` pseudo-elements."""
    lines = []
    for tag, colour in _TAG_COLOURS.items():
        r = int(colour[1:3], 16)
        g = int(colour[3:5], 16)
        b = int(colour[5:7], 16)
        lines.append(
            f"::highlight(hl-{tag}) {{ "
            f"background-color: rgba({r},{g},{b},0.25); "
            f"text-decoration: underline 2px "
            f"rgba({r},{g},{b},0.8); }}"
        )
    return f"<style>{chr(10).join(lines)}</style>"


async def _do_export_pdf(
    highlights: list[dict[str, Any]],
    clean_html: str,
    status_label: ui.label,
) -> None:
    """Export current highlights to PDF and trigger browser download."""
    if not highlights:
        status_label.set_text("No highlights to export.")
        return
    status_label.set_text("Generating PDF...")
    try:
        pdf_path = await export_annotation_pdf(
            html_content=clean_html,
            highlights=highlights,
            tag_colours=_TAG_COLOURS,
            user_id="demo",
            filename="highlight_api_demo",
        )
        ui.download(pdf_path)
        status_label.set_text(f"PDF exported ({len(highlights)} highlights).")
    except Exception:
        logger.exception("PDF export failed")
        status_label.set_text("PDF export failed — check server logs.")


@page_route(
    "/demo/highlight-api",
    title="Highlight API",
    icon="highlight",
    category="demo",
    requires_auth=False,
    requires_demo=True,
    order=50,
)
async def highlight_api_demo() -> None:
    """CSS Custom Highlight API proof-of-concept."""
    if not require_demo_enabled():
        return

    # Load pre-processed workspace fixture (already through input pipeline)
    clean_html = _FIXTURE_PATH.read_text(encoding="utf-8")
    document_chars = extract_text_from_html(clean_html)

    highlights: list[dict[str, Any]] = list(_CROSS_BLOCK_HIGHLIGHTS)
    current_tag_idx = [0]
    tag_names = list(_TAG_COLOURS.keys())

    _render_header(tag_names, current_tag_idx)

    # --- Document (clean HTML, no char spans) ---
    ui.label("Document (clean HTML):").classes("text-h6 q-mt-md")
    ui.html(clean_html, sanitize=False).classes("border rounded p-4 bg-white").props(
        'id="hl-demo-doc"'
    ).style("max-height: 60vh; overflow-y: auto")

    ui.add_head_html(_build_highlight_css())

    # --- Export status ---
    export_status = ui.label("").classes("text-caption q-mt-sm")

    # --- Load text walker + highlight API module ---
    ui.add_body_html('<script src="/static/annotation-highlight.js"></script>')

    # --- Event handlers ---
    async def _push_highlights() -> None:
        manifest: dict[str, list[dict[str, int]]] = {}
        for hl in highlights:
            manifest.setdefault(hl["tag"], []).append(
                {"start": hl["start_char"], "end": hl["end_char"]}
            )
        await ui.run_javascript(
            f"const c = document.getElementById('hl-demo-doc');"
            f"if(c) applyHighlights(c, {json.dumps(manifest)});"
        )
        n = len(highlights)
        export_status.set_text(f"{n} highlight{'s' if n != 1 else ''} active.")

    async def on_selection(e: Any) -> None:
        start = e.args.get("start_char")
        end = e.args.get("end_char")
        if start is None or end is None or start >= end:
            return
        tag = tag_names[current_tag_idx[0]]
        text = "".join(document_chars[start:end])
        highlights.append(
            {
                "start_char": start,
                "end_char": end,
                "tag": tag,
                "text": text,
                "author": "demo",
                "para_ref": "",
                "comments": [],
            }
        )
        logger.info("Highlight: %s [%d:%d]", tag, start, end)
        await _push_highlights()

    ui.on("hl_demo_selection", on_selection)

    async def verify_parity() -> None:
        js_chars = await ui.run_javascript(
            "const c = document.getElementById('hl-demo-doc');"
            "if(!c) return null;"
            "const nodes = walkTextNodes(c);"
            "if(!nodes.length) return null;"
            "return nodes[nodes.length - 1].endChar;"
        )
        py_count = len(document_chars)
        match = js_chars == py_count
        export_status.set_text(
            f"Parity: JS={js_chars}, Python={py_count}"
            f" — {'MATCH' if match else 'MISMATCH'}"
        )

    async def clear_all() -> None:
        highlights.clear()
        await _push_highlights()

    # --- Action buttons ---
    with ui.row().classes("gap-2 q-mt-md"):
        ui.button("Verify JS/Python Parity", on_click=verify_parity).props("outline")
        ui.button(
            "Export PDF",
            on_click=lambda: _do_export_pdf(highlights, clean_html, export_status),
        ).props("outline color=primary")
        ui.button("Clear Highlights", on_click=clear_all).props("outline color=red")

    # --- Init selection handler after DOM ready ---
    ui.timer(
        0.5,
        lambda: ui.run_javascript(
            "const c = document.getElementById('hl-demo-doc');if(c) setupSelection(c);"
        ),
        once=True,
    )
