"""Tests for walk_and_wrap — AST-based LaTeX highlight splitting (Issue #132).

Popperian risky tests:
1. Never produce \\highLight or \\underLine containing blank line or \\par
2. Never produce \\annot inside \\section{} or any restricted argument
3. Existing pipeline behaviour is preserved (tested via integration tests)
4. Highlight spanning heading + list compiles without errors

These tests target the function directly. Integration tests verify the
full pipeline (convert_html_with_annotations).
"""

from __future__ import annotations

import re
from typing import Any

from promptgrimoire.export.latex import walk_and_wrap

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_highlight(
    tag: str = "jurisdiction",
) -> dict[str, Any]:
    """Create a minimal highlight dict for testing."""
    return {
        "tag": tag,
        "author": "Tester",
        "created_at": "2026-02-09T10:00:00+00:00",
        "comments": [],
    }


def _hl_start(n: int) -> str:
    return f"HLSTART{n}ENDHL"


def _hl_end(n: int) -> str:
    return f"HLEND{n}ENDHL"


def _ann_marker(n: int) -> str:
    return f"ANNMARKER{n}ENDMARKER"


# Restricted contexts where \par is forbidden
_SECTION_CMDS = [r"\section", r"\subsection", r"\subsubsection", r"\paragraph"]


def _find_brace_content(latex: str, start: int) -> str:
    """Extract content of first {...} group starting at `start`."""
    depth = 0
    begin = None
    for i in range(start, len(latex)):
        if latex[i] == "{":
            if depth == 0:
                begin = i + 1
            depth += 1
        elif latex[i] == "}":
            depth -= 1
            if depth == 0 and begin is not None:
                return latex[begin:i]
    return ""


def _annots_inside_sections(latex: str) -> list[str]:
    """Return list of \\annot commands found inside sectioning commands."""
    problems = []
    for cmd in _SECTION_CMDS:
        pattern = re.compile(re.escape(cmd) + r"\s*\{")
        for m in pattern.finditer(latex):
            content = _find_brace_content(latex, m.start() + len(cmd))
            if r"\annot" in content:
                problems.append(f"{cmd} contains \\annot: ...{content[:80]}...")
    return problems


def _annots_at_nonzero_depth(latex: str) -> list[str]:
    r"""Return list of \\annot commands found at brace depth > 0.

    This is the generic check — \annot contains \par (via \marginalia/\parbox)
    so it must never appear inside any macro argument (any brace depth > 0).
    """
    problems = []
    i = 0
    while i < len(latex):
        idx = latex.find(r"\annot", i)
        if idx == -1:
            break
        # Verify it's \annot{ not \annotation etc.
        after = idx + len(r"\annot")
        if after < len(latex) and latex[after] not in "{[":
            i = after
            continue
        # Calculate brace depth at this position
        depth = 0
        for j in range(idx):
            if latex[j] == "{":
                depth += 1
            elif latex[j] == "}":
                depth -= 1
        if depth > 0:
            # Extract context for error message
            start = max(0, idx - 40)
            end = min(len(latex), idx + 40)
            problems.append(f"\\annot at depth {depth}: ...{latex[start:end]}...")
        i = after
    return problems


def _highlight_bodies(latex: str) -> list[str]:
    """Extract all \\highLight{...} body contents (handling nested braces)."""
    bodies = []
    prefix = r"\highLight"
    pos = 0
    while True:
        idx = latex.find(prefix, pos)
        if idx == -1:
            break
        # Find the opening brace after optional [...] argument
        brace_start = latex.find("{", idx + len(prefix))
        if brace_start == -1:
            break
        # Check if there's an optional arg
        after_prefix = idx + len(prefix)
        if after_prefix < len(latex) and latex[after_prefix] == "[":
            close_bracket = latex.find("]", after_prefix)
            if close_bracket != -1:
                brace_start = latex.find("{", close_bracket)
        if brace_start == -1:
            break
        body = _find_brace_content(latex, brace_start)
        bodies.append(body)
        pos = brace_start + 1
    return bodies


def _underline_bodies(latex: str) -> list[str]:
    """Extract all \\underLine{...} body contents (handling nested braces)."""
    bodies = []
    prefix = r"\underLine"
    pos = 0
    while True:
        idx = latex.find(prefix, pos)
        if idx == -1:
            break
        after_prefix = idx + len(prefix)
        brace_start = latex.find("{", after_prefix)
        if brace_start == -1:
            break
        if after_prefix < len(latex) and latex[after_prefix] == "[":
            close_bracket = latex.find("]", after_prefix)
            if close_bracket != -1:
                brace_start = latex.find("{", close_bracket)
        if brace_start == -1:
            break
        body = _find_brace_content(latex, brace_start)
        bodies.append(body)
        pos = brace_start + 1
    return bodies


# ===========================================================================
# Popperian Claim 1: No \\highLight or \\underLine containing blank line/\\par
# ===========================================================================


class TestNoParInsideHighlights:
    """walk_and_wrap must never wrap \\par or blank lines inside highlight commands."""

    def test_par_not_inside_highlight_simple(self) -> None:
        r"""A highlight spanning a \\par should split around it."""
        latex = f"Some {_hl_start(0)}text\\par more text{_hl_end(0)}{_ann_marker(0)}"
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        for body in _highlight_bodies(result):
            assert r"\par" not in body, f"\\par found inside \\highLight: {body}"

    def test_blank_line_not_inside_highlight(self) -> None:
        """A highlight spanning a blank line (= \\par) should split around it."""
        latex = f"Some {_hl_start(0)}text\n\nmore text{_hl_end(0)}{_ann_marker(0)}"
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        for body in _highlight_bodies(result):
            assert "\n\n" not in body, f"Blank line inside \\highLight: {body}"

    def test_par_not_inside_underline(self) -> None:
        r"""\\underLine must also not wrap \\par."""
        latex = f"Some {_hl_start(0)}text\\par more{_hl_end(0)}{_ann_marker(0)}"
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        for body in _underline_bodies(result):
            assert r"\par" not in body, f"\\par found inside \\underLine: {body}"

    def test_environment_boundary_splits_highlight(self) -> None:
        r"""\\begin{enumerate} inside highlight should cause a split."""
        latex = (
            f"{_hl_start(0)}Before list\n"
            r"\begin{enumerate}"
            "\n"
            r"\item First"
            "\n"
            r"\end{enumerate}"
            f"\nAfter list{_hl_end(0)}{_ann_marker(0)}"
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        for body in _highlight_bodies(result):
            assert r"\begin{enumerate}" not in body, (
                f"\\begin{{enumerate}} inside \\highLight: {body}"
            )

    def test_section_boundary_splits_highlight(self) -> None:
        r"""\\section{} inside highlight should cause a split."""
        latex = (
            f"{_hl_start(0)}Before heading\n"
            r"\section{My Heading}"
            f"\nAfter heading{_hl_end(0)}{_ann_marker(0)}"
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        for body in _highlight_bodies(result):
            assert r"\section" not in body, f"\\section inside \\highLight: {body}"


# ===========================================================================
# Popperian Claim 2: No \\annot inside ANY restricted argument (brace depth 0)
# ===========================================================================


class TestNoAnnotInsideRestrictedArgs:
    r"""walk_and_wrap must never place \\annot at brace depth > 0.

    \\annot contains \\par (via \\marginalia/\\parbox), which is forbidden
    inside any non-\\long macro argument. This is tested generically via
    brace-depth — no hardcoded command name list.
    """

    def test_annot_not_in_section(self) -> None:
        r"""\\annot for a highlight ending in \\section must appear outside."""
        latex = (
            r"\section{"
            f"{_hl_start(0)}Heading text{_hl_end(0)}{_ann_marker(0)}"
            "}\n\nBody paragraph."
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        problems = _annots_at_nonzero_depth(result)
        assert not problems, f"\\annot at depth > 0: {problems}"

    def test_annot_not_in_subsection(self) -> None:
        r"""\\annot for a highlight ending in \\subsection must appear outside."""
        latex = (
            r"\subsection{"
            f"{_hl_start(0)}Sub heading{_hl_end(0)}{_ann_marker(0)}"
            "}\n\nBody."
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        problems = _annots_at_nonzero_depth(result)
        assert not problems, f"\\annot at depth > 0: {problems}"

    def test_annot_not_in_textbf(self) -> None:
        r"""\\annot inside \\textbf{} must be moved outside — the actual bug."""
        latex = (
            r"\textbf{"
            f"{_hl_start(0)}Bold text{_hl_end(0)}{_ann_marker(0)}"
            "}\n\nMore text."
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        problems = _annots_at_nonzero_depth(result)
        assert not problems, f"\\annot at depth > 0: {problems}"

    def test_annot_not_in_emph(self) -> None:
        r"""\\annot inside \\emph{} must be moved outside."""
        latex = (
            r"\emph{"
            f"{_hl_start(0)}Emphasized{_hl_end(0)}{_ann_marker(0)}"
            "}"
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        problems = _annots_at_nonzero_depth(result)
        assert not problems, f"\\annot at depth > 0: {problems}"

    def test_annot_not_in_nested_formatting(self) -> None:
        r"""\\annot inside \\textbf{\\emph{}} (depth 2) must reach depth 0."""
        latex = (
            r"\textbf{\emph{"
            f"{_hl_start(0)}Deep text{_hl_end(0)}{_ann_marker(0)}"
            "}}"
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        problems = _annots_at_nonzero_depth(result)
        assert not problems, f"\\annot at depth > 0: {problems}"

    def test_annot_with_highlight_spanning_section_boundary(self) -> None:
        """Highlight spanning from section heading into body text."""
        latex = (
            r"\section{"
            f"{_hl_start(0)}Heading"
            "}\n\n"
            f"Body text continues{_hl_end(0)}{_ann_marker(0)} more."
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        problems = _annots_at_nonzero_depth(result)
        assert not problems, f"\\annot at depth > 0: {problems}"
        assert r"\highLight" in result


# ===========================================================================
# Claim 3: Existing behaviour preserved (basic wrapping correctness)
# ===========================================================================


class TestBasicWrapping:
    """walk_and_wrap must produce correct highlight/underline wrapping."""

    def test_simple_highlight(self) -> None:
        """Single highlight around plain text."""
        latex = f"before {_hl_start(0)}highlighted{_hl_end(0)}{_ann_marker(0)} after"
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        assert r"\highLight" in result
        assert "before" in result
        assert "after" in result
        assert r"\annot" in result

    def test_no_highlights_passthrough(self) -> None:
        """Text with no markers should pass through unchanged."""
        latex = r"Just some \textbf{normal} LaTeX."
        result = walk_and_wrap(latex, {})

        assert result == latex

    def test_nested_highlights(self) -> None:
        """Two overlapping highlights should produce nested wrapping."""
        latex = (
            f"{_hl_start(0)}first "
            f"{_hl_start(1)}both{_hl_end(0)}{_ann_marker(0)} "
            f"second only{_hl_end(1)}{_ann_marker(1)}"
        )
        highlights = {
            0: _make_highlight(tag="jurisdiction"),
            1: _make_highlight(tag="reasoning"),
        }

        result = walk_and_wrap(latex, highlights)

        # Should have highlight wrapping for both
        assert r"\highLight" in result
        assert r"\annot" in result

    def test_inline_formatting_preserved(self) -> None:
        r"""\\textbf inside a highlight should be preserved."""
        latex = (
            f"{_hl_start(0)}normal \\textbf{{bold}} normal{_hl_end(0)}{_ann_marker(0)}"
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        assert r"\textbf" in result
        assert r"\highLight" in result

    def test_empty_latex_returns_empty(self) -> None:
        """Empty input produces empty output."""
        assert walk_and_wrap("", {}) == ""

    def test_markers_with_minimal_text(self) -> None:
        """Markers with minimal text produce highlights and annot."""
        latex = f"{_hl_start(0)}x{_hl_end(0)}{_ann_marker(0)}"
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        assert r"\highLight" in result
        assert r"\annot" in result


# ===========================================================================
# Claim 4: Highlight spanning heading + list (the crashing case)
# ===========================================================================


class TestCrossBoundaryHighlights:
    """Highlights crossing structural boundaries must produce valid LaTeX."""

    def test_highlight_spanning_heading_and_list(self) -> None:
        """The specific case that crashes: highlight from heading into list."""
        latex = (
            r"\section{"
            f"{_hl_start(0)}Title"
            "}\n\n"
            r"\begin{itemize}"
            "\n"
            r"\item First item"
            "\n"
            r"\item Second item"
            "\n"
            r"\end{itemize}"
            f"\n{_hl_end(0)}{_ann_marker(0)}"
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        # Claim 1: no \par inside highlights
        for body in _highlight_bodies(result):
            assert r"\par" not in body
            assert "\n\n" not in body

        # Claim 2: no \annot inside \section
        problems = _annots_inside_sections(result)
        assert not problems

        # Highlight wrapping should exist
        assert r"\highLight" in result
        assert r"\annot" in result

    def test_highlight_spanning_two_paragraphs(self) -> None:
        """Highlight spanning paragraph break (blank line)."""
        latex = (
            f"First paragraph {_hl_start(0)}starts here.\n\n"
            f"Second paragraph continues.{_hl_end(0)}{_ann_marker(0)}"
        )
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        for body in _highlight_bodies(result):
            assert "\n\n" not in body
            assert r"\par" not in body

    def test_highlight_spanning_backslash_par(self) -> None:
        r"""Highlight spanning explicit \\par command."""
        latex = f"{_hl_start(0)}Before\\par After{_hl_end(0)}{_ann_marker(0)}"
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        for body in _highlight_bodies(result):
            assert r"\par" not in body

    def test_highlight_reopens_after_boundary(self) -> None:
        """After splitting at a boundary, the highlight should resume."""
        latex = f"{_hl_start(0)}Before\\par After{_hl_end(0)}{_ann_marker(0)}"
        highlights = {0: _make_highlight()}

        result = walk_and_wrap(latex, highlights)

        # Should have at least two \highLight commands (before and after \par)
        highlight_count = result.count(r"\highLight")
        assert highlight_count >= 2, (
            f"Expected highlight to split and reopen, got {highlight_count} "
            f"\\highLight commands: {result}"
        )
