"""Tests for _move_annots_outside_restricted — annot extraction from brace groups.

Regression test for production failure on workspace with 57 highlights where
the old max_iterations=50 left 6 \\annot commands nested inside \\textbf{},
causing '! Paragraph ended before \\text@command was complete' in LuaLaTeX.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pycrdt
import pytest

from promptgrimoire.export.highlight_spans import compute_highlight_spans
from promptgrimoire.export.html_normaliser import (
    fix_midword_font_splits,
    strip_scripts_and_styles,
)
from promptgrimoire.export.pandoc import (
    _brace_depth_at,
    _move_annots_outside_restricted,
    convert_html_to_latex,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "workspace_legal_will_57hl_scrubbed.json"
)
_HIGHLIGHT_FILTER = (
    Path(__file__).parent.parent.parent
    / "src"
    / "promptgrimoire"
    / "export"
    / "filters"
    / "highlight.lua"
)


def _load_fixture() -> tuple[str, list[dict], dict[str, str]]:
    """Load scrubbed workspace fixture.

    Returns (html, highlights, tag_colours).
    """
    data = json.loads(FIXTURE_PATH.read_text())
    content = data["documents"][0]["content"]

    crdt_bytes = base64.b64decode(data["workspace"]["crdt_state"]["base64"])
    doc = pycrdt.Doc()
    doc.apply_update(crdt_bytes)
    highlights_map = doc.get("highlights", type=pycrdt.Map)

    highlights = []
    for _hid, h in highlights_map.items():
        hd = dict(h)
        hd["start_char"] = int(hd["start_char"])
        hd["end_char"] = int(hd["end_char"])
        hd["comments"] = [dict(c) for c in hd.get("comments", [])]
        highlights.append(hd)

    tag_colours = {}
    for tag in data["tags"]:
        tag_colours[tag["name"]] = tag.get("colour", "888888")
        tag_colours[tag["id"]] = tag.get("colour", "888888")

    return content, highlights, tag_colours


class TestMoveAnnotsOutsideRestricted:
    """Unit tests for the annot-extraction post-processor."""

    def test_single_nested_annot(self) -> None:
        r"""A single \annot inside \textbf{} is moved to depth 0."""
        latex = r"\textbf{hello\annot{red}{note}world}"
        result = _move_annots_outside_restricted(latex)
        idx = result.find(r"\annot")
        assert idx >= 0
        assert _brace_depth_at(result, idx) == 0

    def test_already_at_depth_zero(self) -> None:
        r"""\annot already at depth 0 is left unchanged."""
        latex = r"hello\annot{red}{note}world"
        result = _move_annots_outside_restricted(latex)
        assert result == latex

    @pytest.mark.asyncio
    async def test_57_highlight_workspace_all_annots_at_depth_zero(self) -> None:
        """Regression: 57-highlight legal will must have all annots at depth 0.

        The production failure occurred because max_iterations=50 was exhausted
        before all 56 nested annots could be moved out of restricted contexts.
        """
        content, highlights, tag_colours = _load_fixture()

        # Run the pipeline up to Pandoc (without _move_annots_outside_restricted)
        html = strip_scripts_and_styles(content)
        html = fix_midword_font_splits(html)
        span_html = compute_highlight_spans(html, highlights, tag_colours)

        latex_raw = await convert_html_to_latex(
            span_html, filter_paths=[_HIGHLIGHT_FILTER]
        )

        # Apply the post-processor
        latex = _move_annots_outside_restricted(latex_raw)

        # Every \annot must be at brace depth 0
        nested = []
        pos = 0
        while True:
            idx = latex.find(r"\annot{", pos)
            if idx == -1:
                break
            depth = _brace_depth_at(latex, idx)
            if depth > 0:
                # Extract context for diagnostic
                ctx = latex[max(0, idx - 30) : idx + 60].replace("\n", "\\n")
                nested.append((idx, depth, ctx))
            pos = idx + 1

        assert nested == [], (
            f"{len(nested)} \\annot command(s) still nested after post-processing:\n"
            + "\n".join(f"  pos={pos} depth={d}: ...{ctx}..." for pos, d, ctx in nested)
        )
