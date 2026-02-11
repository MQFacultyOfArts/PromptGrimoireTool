"""Demo: CSS Custom Highlight API proof-of-concept.

Proves two claims:
1. CSS Custom Highlight API ranges span across DOM block boundaries
   (p, h2, li, blockquote) without splitting or DOM modification.
   Uses real 183-austlii.html fixture (Lawlis v R [2025] NSWCCA 183).
2. The same character offsets used for live highlighting feed directly
   into the PDF export pipeline (compute_highlight_spans) unchanged.

Route: /demo/highlight-api (requires ENABLE_DEMO_PAGES=true)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nicegui import ui

from promptgrimoire.export.highlight_spans import compute_highlight_spans
from promptgrimoire.input_pipeline.html_input import (
    extract_text_from_html,
    process_input,
)
from promptgrimoire.pages.layout import require_demo_enabled
from promptgrimoire.pages.registry import page_route

logger = logging.getLogger(__name__)

# --- Fixture path ---
_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "183-austlii.html"
)

_CROSS_BLOCK_HIGHLIGHTS: list[dict[str, Any]] = []

_TAG_COLOURS = {
    "jurisdiction": "#3366cc",
    "legal_issues": "#cc3333",
    "legislation": "#339933",
    "evidence": "#cc9900",
}

# JS: walk DOM text nodes and compute flat character offsets.
# Mirrors Python extract_text_from_html() rules.
_TEXT_WALKER_JS = """
const SKIP_TAGS = new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE']);
const BLOCK_TAGS = new Set([
    'TABLE','TBODY','THEAD','TFOOT','TR','TD','TH',
    'UL','OL','LI','DL','DT','DD',
    'DIV','SECTION','ARTICLE','ASIDE','HEADER','FOOTER','NAV','MAIN',
    'FIGURE','FIGCAPTION','BLOCKQUOTE'
]);

function walkTextNodes(root) {
    // Returns array of {node, startChar, endChar} for each text node
    const result = [];
    let charIdx = 0;

    function walk(el) {
        for (let child = el.firstChild; child; child = child.nextSibling) {
            if (child.nodeType === Node.ELEMENT_NODE) {
                const tag = child.tagName;
                if (SKIP_TAGS.has(tag)) continue;
                if (tag === 'BR') {
                    charIdx++;  // BR counts as 1 char (newline)
                    continue;
                }
                walk(child);
            } else if (child.nodeType === Node.TEXT_NODE) {
                const parent = child.parentElement;
                const text = child.textContent;
                // Skip whitespace-only text nodes in block containers
                if (BLOCK_TAGS.has(parent?.tagName) && /^\\s*$/.test(text)) continue;
                // Collapse whitespace runs
                let nodeStart = charIdx;
                let prevWasSpace = false;
                for (const ch of text) {
                    const isSpace = /[\\s\\u00a0]/.test(ch);
                    if (isSpace) {
                        if (!prevWasSpace) {
                            charIdx++;
                            prevWasSpace = true;
                        }
                    } else {
                        charIdx++;
                        prevWasSpace = false;
                    }
                }
                result.push({node: child, startChar: nodeStart, endChar: charIdx});
            }
        }
    }
    walk(root);
    return result;
}
"""

# JS: apply highlights using CSS Custom Highlight API
_APPLY_HIGHLIGHTS_JS = """
function applyHighlights(container, highlightData) {
    const textNodes = walkTextNodes(container);
    if (!textNodes.length) return;

    // Clear existing highlights
    for (const name of CSS.highlights.keys()) {
        if (name.startsWith('hl-')) CSS.highlights.delete(name);
    }

    for (const [tag, regions] of Object.entries(highlightData)) {
        const ranges = [];
        for (const region of regions) {
            const range = charOffsetToRange(textNodes, region.start, region.end);
            if (range) ranges.push(range);
        }
        if (ranges.length) {
            const hl = new Highlight(...ranges);
            hl.priority = region_priority(tag);
            CSS.highlights.set('hl-' + tag, hl);
        }
    }
}

function region_priority(tag) {
    const p = {
        jurisdiction: 10, legal_issues: 20,
        legislation: 30, evidence: 40
    };
    return p[tag] || 0;
}

function charOffsetToRange(textNodes, startChar, endChar) {
    let startNode = null, startOff = 0, endNode = null, endOff = 0;

    for (const tn of textNodes) {
        if (!startNode && tn.endChar > startChar) {
            startNode = tn.node;
            startOff = findLocalOffset(tn.node, startChar - tn.startChar);
        }
        if (!endNode && tn.endChar >= endChar) {
            endNode = tn.node;
            endOff = findLocalOffset(tn.node, endChar - tn.startChar);
            break;
        }
    }
    if (!startNode || !endNode) return null;
    try {
        return new StaticRange({
            startContainer: startNode, startOffset: startOff,
            endContainer: endNode, endOffset: endOff
        });
    } catch(e) {
        console.warn('StaticRange creation failed:', e);
        return null;
    }
}

function findLocalOffset(textNode, collapsedOffset) {
    // Convert collapsed-whitespace offset back to raw text offset
    const text = textNode.textContent;
    let collapsed = 0;
    let prevWasSpace = false;
    for (let i = 0; i < text.length; i++) {
        if (collapsed >= collapsedOffset) return i;
        const isSpace = /[\\s\\u00a0]/.test(text[i]);
        if (isSpace) {
            if (!prevWasSpace) { collapsed++; prevWasSpace = true; }
        } else {
            collapsed++;
            prevWasSpace = false;
        }
    }
    return text.length;
}
"""

# JS: selection detection — convert browser Range to flat char offsets
_SELECTION_JS = """
function setupSelection(container) {
    document.addEventListener('mouseup', () => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount) return;
        const range = sel.getRangeAt(0);
        if (!container.contains(range.startContainer)) return;

        const textNodes = walkTextNodes(container);
        const startChar = rangePointToCharOffset(
            textNodes, range.startContainer, range.startOffset);
        const endChar = rangePointToCharOffset(
            textNodes, range.endContainer, range.endOffset);

        if (startChar !== null && endChar !== null && startChar < endChar) {
            emitEvent('hl_demo_selection', {start_char: startChar, end_char: endChar});
        }
    });
}

function rangePointToCharOffset(textNodes, node, offset) {
    // If node is an element, convert to text node reference
    if (node.nodeType === Node.ELEMENT_NODE) {
        if (offset < node.childNodes.length) {
            node = node.childNodes[offset];
            offset = 0;
        } else {
            // Past end of element — find last text node inside
            const last = textNodes.filter(
                tn => node.contains(tn.node));
            if (last.length) return last[last.length - 1].endChar;
            return null;
        }
    }
    for (const tn of textNodes) {
        if (tn.node === node) {
            return tn.startChar + countCollapsed(node.textContent, offset);
        }
    }
    return null;
}

function countCollapsed(text, rawOffset) {
    let collapsed = 0;
    let prevWasSpace = false;
    for (let i = 0; i < rawOffset && i < text.length; i++) {
        const isSpace = /[\\s\\u00a0]/.test(text[i]);
        if (isSpace) {
            if (!prevWasSpace) { collapsed++; prevWasSpace = true; }
        } else {
            collapsed++;
            prevWasSpace = false;
        }
    }
    return collapsed;
}
"""


def _render_header(
    tag_names: list[str],
    current_tag_idx: list[int],
) -> None:
    """Render page title, description, and tag selector buttons."""
    ui.label("CSS Custom Highlight API — Proof of Concept").classes("text-h4")
    ui.markdown(
        "**Fixture:** `183-austlii.html` "
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


def _render_export_preview(
    export_el: ui.html,
    parity_el: ui.label,
    highlights: list[dict[str, Any]],
    doc_chars_len: int,
    clean_html: str,
) -> None:
    """Update the export preview panel with highlight span output."""
    if highlights:
        result = compute_highlight_spans(clean_html, highlights, _TAG_COLOURS)
        preview = result[:3000]
        export_el.set_content(
            f"<pre style='white-space:pre-wrap;font-size:0.8em;'>"
            f"{_escape_html(preview)}</pre>"
        )
    else:
        export_el.set_content("")
    parity_el.set_text(f"Server chars: {doc_chars_len} | Highlights: {len(highlights)}")


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

    # Load 183-austlii fixture and clean via input pipeline
    raw_html = _FIXTURE_PATH.read_text(encoding="utf-8")
    clean_html = await process_input(raw_html, "html", None)
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

    # --- Export preview ---
    ui.label("Export Preview:").classes("text-h6 q-mt-lg")
    export_el = ui.html("", sanitize=False).classes("border rounded p-4 bg-grey-1")
    parity_label = ui.label("").classes("text-caption q-mt-sm")

    # --- Inject JS ---
    all_js = _TEXT_WALKER_JS + _APPLY_HIGHLIGHTS_JS + _SELECTION_JS
    ui.add_body_html(f"<script>{all_js}</script>")

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
        _render_export_preview(
            export_el,
            parity_label,
            highlights,
            len(document_chars),
            clean_html,
        )

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
        parity_label.set_text(
            f"Parity: JS={js_chars}, Python={py_count}"
            f" — {'MATCH' if match else 'MISMATCH'}"
        )

    async def clear_all() -> None:
        highlights.clear()
        await _push_highlights()

    # --- Action buttons ---
    with ui.row().classes("gap-2 q-mt-md"):
        ui.button("Verify JS/Python Parity", on_click=verify_parity).props("outline")
        ui.button("Clear Highlights", on_click=clear_all).props("outline color=red")

    # --- Init selection handler after DOM ready ---
    ui.timer(
        0.5,
        lambda: ui.run_javascript(
            "const c = document.getElementById('hl-demo-doc');if(c) setupSelection(c);"
        ),
        once=True,
    )


def _escape_html(text: str) -> str:
    """Escape HTML special characters for display in <pre>."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
