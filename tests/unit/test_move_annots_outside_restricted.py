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


class TestBraceDepthEscaping:
    r"""_brace_depth_at must skip LaTeX-escaped braces (\{ and \}).

    Production failure: student comment containing literal '}' is escaped to
    '\}' by escape_unicode_latex. The naive brace counter treated '\}' as a
    structural closing brace, throwing off depth for all subsequent content.
    _move_annots_outside_restricted then saw the wrong depth and failed to
    move \annot out of \textbf{}.
    """

    def test_escaped_close_brace_not_counted(self) -> None:
        r"""\} inside a group does not reduce structural depth."""
        # \textbf{ opens depth 1; \} is NOT structural; } closes to depth 0
        latex = r"\textbf{hello\}world}"
        # Position after the final '}' — depth should be 0
        assert _brace_depth_at(latex, len(latex)) == 0
        # Position just before the final '}' — depth should be 1 (still inside \textbf)
        final_close = latex.rfind("}")
        assert _brace_depth_at(latex, final_close) == 1

    def test_escaped_open_brace_not_counted(self) -> None:
        r"""\{ inside a group does not increase structural depth."""
        latex = r"\textbf{hello\{world}"
        assert _brace_depth_at(latex, len(latex)) == 0
        final_close = latex.rfind("}")
        assert _brace_depth_at(latex, final_close) == 1

    def test_double_backslash_then_brace_is_structural(self) -> None:
        r"""\\{ is escaped backslash + structural open brace."""
        # \\{ = line break + structural {
        latex = r"\\{hello}"
        # After \\{ we're at depth 1, after } at depth 0
        assert _brace_depth_at(latex, len(latex)) == 0
        brace_pos = latex.index("{")
        assert _brace_depth_at(latex, brace_pos + 1) == 1

    def test_annot_with_escaped_brace_in_comment(self) -> None:
        r"""Reproduces production bug: \annot comment text with literal '}'.

        The annot at depth 0 contains \} in its content. The NEXT \annot
        after it, which is inside \textbf{}, must be correctly detected
        as depth 1 (not 0) so the post-processor moves it out.
        """
        latex = (
            r"\annot{red}{comment [2\}}"  # depth 0 annot with escaped brace
            r"\textbf{hello\annot{blue}{note\par}world}"  # depth 1 annot
        )
        # The second \annot should be at depth 1 (inside \textbf{})
        second_annot = latex.find(r"\annot{blue}")
        assert second_annot > 0
        assert _brace_depth_at(latex, second_annot) == 1

    def test_move_annots_with_escaped_brace_in_prior_annot(self) -> None:
        r"""Post-processor must move \annot out despite escaped braces earlier.

        This is the end-to-end regression test for the production failure.
        """
        latex = (
            r"\annot{red}{comment [2\}}"
            r"\textbf{hello\annot{blue}{note\par}world}"
        )
        result = _move_annots_outside_restricted(latex)
        # The blue annot must now be at depth 0
        blue_idx = result.find(r"\annot{blue}")
        assert blue_idx >= 0
        assert _brace_depth_at(result, blue_idx) == 0


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
