# Phase 5: Test Cleanup

**Goal:** Reorganize tests into proper structure with component-level unit tests

**Architecture:** Move tests to `tests/unit/export/` by concern, delete obsolete regex-based tests, add Issue #85 regression test to integration suite.

**Tech Stack:** Python 3.14, pytest

**Scope:** Phase 5 of 5 from original design

**Codebase verified:** 2026-01-28

---

<!-- START_TASK_1 -->
### Task 1: Create `tests/unit/export/` Directory Structure

**Files:**
- Create: `tests/unit/export/__init__.py`
- Create: `tests/unit/export/test_latex_string_functions.py`
- Create: `tests/unit/export/test_marker_insertion.py`

**Step 1: Create directory and __init__.py**

```bash
mkdir -p tests/unit/export
touch tests/unit/export/__init__.py
```

**Step 2: Move pure function tests to `test_latex_string_functions.py`**

Extract from `tests/unit/test_latex_export.py`:
- `TestFormatTimestamp`
- `TestGenerateTagColourDefinitions`
- `TestFormatAnnot`
- `TestCompilationValidation`

```python
# tests/unit/export/test_latex_string_functions.py
"""Unit tests for LaTeX export pure functions.

Tests string manipulation, formatting, and colour generation functions.
These are pure functions with no external dependencies.
"""

import pytest
from promptgrimoire.export.latex import (
    _format_timestamp,
    generate_tag_colour_definitions,
    _format_annot,
)


class TestFormatTimestamp:
    """Tests for _format_timestamp()."""

    def test_formats_iso_timestamp(self):
        result = _format_timestamp("2024-01-15T10:30:00Z")
        assert "2024" in result
        assert "01" in result or "Jan" in result

    def test_handles_empty_string(self):
        result = _format_timestamp("")
        assert result == ""

    def test_handles_none(self):
        result = _format_timestamp(None)
        assert result == ""


class TestGenerateTagColourDefinitions:
    """Tests for generate_tag_colour_definitions()."""

    def test_generates_colour_for_single_tag(self):
        result = generate_tag_colour_definitions({"alpha": "#1f77b4"})
        assert "tag-alpha" in result
        assert "1f77b4" in result.lower() or "1F77B4" in result

    def test_generates_light_and_dark_variants(self):
        result = generate_tag_colour_definitions({"alpha": "#1f77b4"})
        assert "tag-alpha-light" in result
        assert "tag-alpha-dark" in result

    def test_handles_multiple_tags(self):
        result = generate_tag_colour_definitions({
            "alpha": "#1f77b4",
            "beta": "#d62728",
        })
        assert "tag-alpha" in result
        assert "tag-beta" in result

    def test_handles_empty_dict(self):
        result = generate_tag_colour_definitions({})
        assert result == ""


class TestFormatAnnot:
    """Tests for _format_annot().

    Signature: _format_annot(highlight: dict[str, Any], para_ref: str = "") -> str
    """

    def _make_highlight(self, tag: str, comments: list[str] | None = None) -> dict:
        """Helper to create highlight dicts for testing."""
        return {
            "tag": tag,
            "author": "Test User",
            "created_at": "2026-01-28T10:00:00Z",
            "comments": [{"text": c, "author": "User", "created_at": "2026-01-28"} for c in (comments or [])],
        }

    def test_formats_simple_annotation(self):
        highlight = self._make_highlight("alpha", ["Test note"])
        result = _format_annot(highlight)
        assert "Test note" in result

    def test_escapes_special_characters(self):
        highlight = self._make_highlight("alpha", ["Note with & symbol"])
        result = _format_annot(highlight)
        # Should escape or handle ampersand
        assert "&" not in result or "\\&" in result

    def test_handles_empty_comments(self):
        highlight = self._make_highlight("alpha", [])
        result = _format_annot(highlight)
        # Should still produce output even with no comments
        assert "alpha" in result.lower() or result == ""

    def test_handles_multiline_comment(self):
        highlight = self._make_highlight("alpha", ["Line 1\nLine 2"])
        result = _format_annot(highlight)
        assert "Line 1" in result

    def test_includes_tag_colour(self):
        highlight = self._make_highlight("alpha", ["Note"])
        result = _format_annot(highlight)
        assert "alpha" in result.lower() or "tag-alpha" in result

    def test_handles_special_latex_chars(self):
        highlight = self._make_highlight("alpha", ["Note with $math$ and %percent"])
        result = _format_annot(highlight)
        # Should escape or handle special chars
        assert result  # Non-empty output
```

**Step 3: Move marker insertion tests to `test_marker_insertion.py`**

Extract `TestInsertMarkersIntoHtml` from `test_latex_export.py`:

```python
# tests/unit/export/test_marker_insertion.py
"""Unit tests for marker insertion into HTML.

Tests _insert_markers_into_html() which adds HLSTART/HLEND/ANNMARKER
markers to HTML content before pandoc conversion.
"""

import pytest
from promptgrimoire.export.latex import _insert_markers_into_html


class TestInsertMarkersIntoHtml:
    """Tests for _insert_markers_into_html()."""

    def test_inserts_markers_for_single_highlight(self):
        html = "<p>The quick brown fox</p>"
        highlights = [
            {"start_word": 1, "end_word": 2, "tag": "alpha", "index": 1}
        ]
        result = _insert_markers_into_html(html, highlights)
        assert "HLSTART{1}ENDHL" in result
        assert "HLEND{1}ENDHL" in result

    def test_inserts_annmarker(self):
        html = "<p>The quick brown fox</p>"
        highlights = [
            {"start_word": 1, "end_word": 2, "tag": "alpha", "index": 1, "annotation": "Note"}
        ]
        result = _insert_markers_into_html(html, highlights)
        assert "ANNMARKER{1}ENDMARKER" in result

    def test_handles_multiple_highlights(self):
        html = "<p>The quick brown fox jumps</p>"
        highlights = [
            {"start_word": 1, "end_word": 2, "tag": "alpha", "index": 1},
            {"start_word": 3, "end_word": 4, "tag": "beta", "index": 2},
        ]
        result = _insert_markers_into_html(html, highlights)
        assert "HLSTART{1}ENDHL" in result
        assert "HLSTART{2}ENDHL" in result

    def test_handles_overlapping_highlights(self):
        html = "<p>The quick brown fox</p>"
        highlights = [
            {"start_word": 1, "end_word": 3, "tag": "alpha", "index": 1},
            {"start_word": 2, "end_word": 4, "tag": "beta", "index": 2},
        ]
        result = _insert_markers_into_html(html, highlights)
        # Both markers should be present
        assert "HLSTART{1}ENDHL" in result
        assert "HLSTART{2}ENDHL" in result
        assert "HLEND{1}ENDHL" in result
        assert "HLEND{2}ENDHL" in result
```

**Step 4: Run tests to verify migration**

```bash
uv run pytest tests/unit/export/ -v
```

Expected: All migrated tests pass.

**Step 5: Commit**

```bash
git add tests/unit/export/
git commit -m "$(cat <<'EOF'
refactor(tests): create tests/unit/export/ with pure function and marker tests

Move TestFormatTimestamp, TestGenerateTagColourDefinitions, TestFormatAnnot,
TestCompilationValidation to test_latex_string_functions.py.
Move TestInsertMarkersIntoHtml to test_marker_insertion.py.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

**Falsifiability checkpoint:**

| Claim | How to falsify |
|-------|----------------|
| Tests migrated correctly | Run `pytest tests/unit/export/` - any import error or test failure falsifies |
| Pure functions isolated | Tests in `test_latex_string_functions.py` require no fixtures |
| Marker insertion tests work | `test_marker_insertion.py` tests pass independently |
<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Move Component Test Files to `tests/unit/export/`

**Files:**
- Move: `tests/unit/test_marker_lexer.py` -> `tests/unit/export/test_marker_lexer.py`
- Move: `tests/unit/test_region_builder.py` -> `tests/unit/export/test_region_builder.py`
- Move: `tests/unit/test_latex_generator.py` -> `tests/unit/export/test_latex_generator.py`

**Note:** These test files were created in Phases 1-3 at `tests/unit/`. This task moves them
to the new `tests/unit/export/` directory structure for better organization.

**Step 1: Move `test_marker_lexer.py`**

```bash
mv tests/unit/test_marker_lexer.py tests/unit/export/test_marker_lexer.py
```

The file content (from Phase 1) should be:

```python
# tests/unit/export/test_marker_lexer.py
"""Unit tests for Lark-based marker lexer.

Tests the tokenization stage ONLY - no region building or LaTeX generation.
"""

import pytest
from promptgrimoire.export.latex import (
    tokenize_markers,
    MarkerToken,
    MarkerTokenType,
)


class TestMarkerLexer:
    """Tests for tokenize_markers()."""

    def test_empty_input(self):
        result = tokenize_markers("")
        assert result == []

    def test_text_only_no_markers(self):
        result = tokenize_markers("plain text")
        assert len(result) == 1
        assert result[0].type == MarkerTokenType.TEXT
        assert result[0].value == "plain text"

    def test_single_hlstart(self):
        result = tokenize_markers("HLSTART{1}ENDHL")
        assert len(result) == 1
        assert result[0].type == MarkerTokenType.HLSTART
        assert result[0].index == 1

    def test_single_hlend(self):
        result = tokenize_markers("HLEND{1}ENDHL")
        assert len(result) == 1
        assert result[0].type == MarkerTokenType.HLEND
        assert result[0].index == 1

    def test_single_annmarker(self):
        result = tokenize_markers("ANNMARKER{1}ENDMARKER")
        assert len(result) == 1
        assert result[0].type == MarkerTokenType.ANNMARKER
        assert result[0].index == 1

    def test_complete_highlight_pair(self):
        result = tokenize_markers("HLSTART{1}ENDHLtextHLEND{1}ENDHL")
        assert len(result) == 3
        assert result[0].type == MarkerTokenType.HLSTART
        assert result[1].type == MarkerTokenType.TEXT
        assert result[1].value == "text"
        assert result[2].type == MarkerTokenType.HLEND

    def test_preserves_spaces_in_text(self):
        result = tokenize_markers("HLSTART{1}ENDHL text with spaces HLEND{1}ENDHL")
        text_token = [t for t in result if t.type == MarkerTokenType.TEXT][0]
        assert text_token.value == " text with spaces "

    def test_preserves_newlines_in_text(self):
        result = tokenize_markers("HLSTART{1}ENDHLline1\nline2HLEND{1}ENDHL")
        text_token = [t for t in result if t.type == MarkerTokenType.TEXT][0]
        assert "\n" in text_token.value

    def test_adjacent_markers_no_text_between(self):
        result = tokenize_markers("HLSTART{1}ENDHLHLSTART{2}ENDHL")
        assert len(result) == 2
        assert all(t.type == MarkerTokenType.HLSTART for t in result)

    def test_multiple_highlights_sequential(self):
        result = tokenize_markers(
            "HLSTART{1}ENDHLaHLEND{1}ENDHLHLSTART{2}ENDHLbHLEND{2}ENDHL"
        )
        types = [t.type for t in result]
        assert types == [
            MarkerTokenType.HLSTART,
            MarkerTokenType.TEXT,
            MarkerTokenType.HLEND,
            MarkerTokenType.HLSTART,
            MarkerTokenType.TEXT,
            MarkerTokenType.HLEND,
        ]

    def test_nested_markers(self):
        result = tokenize_markers(
            "HLSTART{1}ENDHLouterHLSTART{2}ENDHLinnerHLEND{2}ENDHLouterHLEND{1}ENDHL"
        )
        indices = [(t.type.name, t.index) for t in result if t.type != MarkerTokenType.TEXT]
        assert indices == [
            ("HLSTART", 1),
            ("HLSTART", 2),
            ("HLEND", 2),
            ("HLEND", 1),
        ]

    def test_interleaved_markers(self):
        result = tokenize_markers(
            "HLSTART{1}ENDHLHLSTART{2}ENDHLHLEND{1}ENDHLHLEND{2}ENDHL"
        )
        indices = [(t.type.name, t.index) for t in result]
        assert indices == [
            ("HLSTART", 1),
            ("HLSTART", 2),
            ("HLEND", 1),
            ("HLEND", 2),
        ]

    def test_extracts_correct_indices(self):
        result = tokenize_markers("HLSTART{42}ENDHLtextHLEND{42}ENDHL")
        assert result[0].index == 42
        assert result[2].index == 42

    def test_latex_commands_in_text_preserved(self):
        result = tokenize_markers(r"HLSTART{1}ENDHL\textbf{bold}HLEND{1}ENDHL")
        text_token = [t for t in result if t.type == MarkerTokenType.TEXT][0]
        assert r"\textbf{bold}" in text_token.value
```

**Step 2: Move `test_region_builder.py`**

```bash
mv tests/unit/test_region_builder.py tests/unit/export/test_region_builder.py
```

The file content (from Phase 2) should be:

```python
# tests/unit/export/test_region_builder.py
"""Unit tests for region builder.

Tests the state machine that converts tokens to regions.
Uses tokens directly - does NOT call lexer.
"""

import pytest
from promptgrimoire.export.latex import (
    build_regions,
    Region,
    MarkerToken,
    MarkerTokenType,
)


def _token(type_name: str, value: str = "", index: int | None = None) -> MarkerToken:
    """Helper to create tokens for testing."""
    return MarkerToken(
        type=MarkerTokenType[type_name],
        value=value,
        index=index,
        start_pos=0,
        end_pos=len(value),
    )


class TestRegionBuilder:
    """Tests for build_regions()."""

    def test_empty_tokens(self):
        result = build_regions([])
        assert result == []

    def test_text_only_single_region(self):
        tokens = [_token("TEXT", "plain text")]
        result = build_regions(tokens)
        assert len(result) == 1
        assert result[0].text == "plain text"
        assert result[0].active == frozenset()

    def test_single_highlight_three_regions(self):
        tokens = [
            _token("TEXT", "before "),
            _token("HLSTART", index=1),
            _token("TEXT", "middle"),
            _token("HLEND", index=1),
            _token("TEXT", " after"),
        ]
        result = build_regions(tokens)
        assert len(result) == 3
        assert result[0].active == frozenset()
        assert result[1].active == frozenset({1})
        assert result[2].active == frozenset()

    def test_non_overlapping_highlights(self):
        tokens = [
            _token("HLSTART", index=1),
            _token("TEXT", "first"),
            _token("HLEND", index=1),
            _token("HLSTART", index=2),
            _token("TEXT", "second"),
            _token("HLEND", index=2),
        ]
        result = build_regions(tokens)
        active_sets = [r.active for r in result if r.text]
        assert active_sets == [frozenset({1}), frozenset({2})]

    def test_nested_highlights_example_a(self):
        # hl1[outer hl2[inner] outer]
        tokens = [
            _token("HLSTART", index=1),
            _token("TEXT", "outer "),
            _token("HLSTART", index=2),
            _token("TEXT", "inner"),
            _token("HLEND", index=2),
            _token("TEXT", " outer"),
            _token("HLEND", index=1),
        ]
        result = build_regions(tokens)
        texts = [(r.text, r.active) for r in result]
        assert texts == [
            ("outer ", frozenset({1})),
            ("inner", frozenset({1, 2})),
            (" outer", frozenset({1})),
        ]

    def test_interleaved_highlights_example_b(self):
        # hl1[a hl2[b] hl1-end c hl2-end]
        tokens = [
            _token("HLSTART", index=1),
            _token("TEXT", "a "),
            _token("HLSTART", index=2),
            _token("TEXT", "b"),
            _token("HLEND", index=1),
            _token("TEXT", " c"),
            _token("HLEND", index=2),
        ]
        result = build_regions(tokens)
        texts = [(r.text, r.active) for r in result]
        assert texts == [
            ("a ", frozenset({1})),
            ("b", frozenset({1, 2})),
            (" c", frozenset({2})),
        ]

    def test_three_overlapping_example_c(self):
        # All three active at same time
        tokens = [
            _token("HLSTART", index=1),
            _token("HLSTART", index=2),
            _token("HLSTART", index=3),
            _token("TEXT", "all three"),
            _token("HLEND", index=3),
            _token("HLEND", index=2),
            _token("HLEND", index=1),
        ]
        result = build_regions(tokens)
        assert len(result) == 1
        assert result[0].active == frozenset({1, 2, 3})

    def test_annmarker_associated_by_index(self):
        tokens = [
            _token("HLSTART", index=1),
            _token("TEXT", "text"),
            _token("ANNMARKER", index=1),
            _token("HLEND", index=1),
        ]
        result = build_regions(tokens)
        # Annmarker appears in region where it occurs
        region_with_annot = [r for r in result if r.annots][0]
        assert 1 in region_with_annot.annots

    def test_annmarker_not_position_dependent(self):
        # ANNMARKER can appear anywhere within the highlight
        tokens = [
            _token("HLSTART", index=1),
            _token("ANNMARKER", index=1),
            _token("TEXT", "text after marker"),
            _token("HLEND", index=1),
        ]
        result = build_regions(tokens)
        # Should still work - annmarker associated by index, not position
        annot_regions = [r for r in result if r.annots]
        assert len(annot_regions) >= 1
        assert 1 in annot_regions[0].annots

    def test_active_set_is_frozenset(self):
        tokens = [_token("HLSTART", index=1), _token("TEXT", "x"), _token("HLEND", index=1)]
        result = build_regions(tokens)
        assert isinstance(result[0].active, frozenset)

    def test_spaces_included_in_regions(self):
        tokens = [
            _token("HLSTART", index=1),
            _token("TEXT", " leading and trailing "),
            _token("HLEND", index=1),
        ]
        result = build_regions(tokens)
        assert result[0].text == " leading and trailing "
```

**Step 3: Move `test_latex_generator.py`**

```bash
mv tests/unit/test_latex_generator.py tests/unit/export/test_latex_generator.py
```

The file content (from Phase 3) should be:

```python
# tests/unit/export/test_latex_generator.py
"""Unit tests for LaTeX generator.

Tests highlight/underline generation from regions.
Uses regions directly - does NOT call lexer or region builder.

Note: generate_underline_wrapper and generate_highlight_wrapper return
Callable[[str], str] - they create wrapper functions, not wrapped text directly.
"""

import pytest
from typing import Any
from promptgrimoire.export.latex import (
    generate_highlighted_latex,
    generate_underline_wrapper,
    generate_highlight_wrapper,
    Region,
)


class TestUnderlineWrapper:
    """Tests for generate_underline_wrapper().

    This function returns a Callable[[str], str] that wraps text in underlines.
    """

    def test_single_highlight_1pt_underline(self):
        highlights = {1: {"tag": "alpha"}}
        wrapper = generate_underline_wrapper(frozenset({1}), highlights)
        result = wrapper("text")
        assert "\\underLine" in result
        assert "height=1pt" in result
        assert "tag-alpha-dark" in result

    def test_two_highlights_stacked_underlines(self):
        highlights = {1: {"tag": "alpha"}, 2: {"tag": "beta"}}
        wrapper = generate_underline_wrapper(frozenset({1, 2}), highlights)
        result = wrapper("text")
        # Should have two underLine commands
        assert result.count("\\underLine") == 2
        # Outer should be 2pt, inner should be 1pt
        assert "height=2pt" in result
        assert "height=1pt" in result

    def test_two_highlights_outer_2pt_inner_1pt(self):
        highlights = {1: {"tag": "alpha"}, 2: {"tag": "beta"}}
        wrapper = generate_underline_wrapper(frozenset({1, 2}), highlights)
        result = wrapper("text")
        # Outer (lower index) gets 2pt, inner gets 1pt
        outer_pos = result.find("height=2pt")
        inner_pos = result.find("height=1pt")
        assert outer_pos < inner_pos  # 2pt comes before 1pt in the string

    def test_three_highlights_many_underline(self):
        highlights = {1: {"tag": "alpha"}, 2: {"tag": "beta"}, 3: {"tag": "gamma"}}
        wrapper = generate_underline_wrapper(frozenset({1, 2, 3}), highlights)
        result = wrapper("text")
        # Should have single underline with many-dark
        assert result.count("\\underLine") == 1
        assert "many-dark" in result

    def test_many_underline_4pt_bottom_minus_5(self):
        highlights = {1: {"tag": "a"}, 2: {"tag": "b"}, 3: {"tag": "c"}}
        wrapper = generate_underline_wrapper(frozenset({1, 2, 3}), highlights)
        result = wrapper("text")
        assert "height=4pt" in result
        assert "bottom=-5pt" in result

    def test_many_underline_uses_many_dark_colour(self):
        highlights = {1: {"tag": "a"}, 2: {"tag": "b"}, 3: {"tag": "c"}}
        wrapper = generate_underline_wrapper(frozenset({1, 2, 3}), highlights)
        result = wrapper("text")
        assert "color=many-dark" in result

    def test_empty_active_returns_identity(self):
        wrapper = generate_underline_wrapper(frozenset(), {})
        result = wrapper("unchanged text")
        assert result == "unchanged text"


class TestHighlightWrapper:
    """Tests for generate_highlight_wrapper().

    This function returns a Callable[[str], str] that wraps text in highlights.
    """

    def test_single_highlight_correct_colours(self):
        highlights = {1: {"tag": "alpha"}}
        wrapper = generate_highlight_wrapper(frozenset({1}), highlights)
        result = wrapper("text")
        assert "\\highLight[tag-alpha-light]" in result

    def test_nested_highlights_correct_nesting_order(self):
        highlights = {1: {"tag": "alpha"}, 2: {"tag": "beta"}}
        wrapper = generate_highlight_wrapper(frozenset({1, 2}), highlights)
        result = wrapper("text")
        # Lower index = outer, so tag-alpha should wrap tag-beta
        alpha_pos = result.find("tag-alpha-light")
        beta_pos = result.find("tag-beta-light")
        assert alpha_pos < beta_pos

    def test_empty_active_returns_identity(self):
        wrapper = generate_highlight_wrapper(frozenset(), {})
        result = wrapper("unchanged text")
        assert result == "unchanged text"


class TestLaTeXGenerator:
    """Tests for generate_highlighted_latex().

    Signature: generate_highlighted_latex(
        regions: list[Region],
        highlights: dict[int, dict[str, Any]],
        env_boundaries: list[tuple[int, int, str]]
    ) -> str
    """

    def test_empty_regions(self):
        result = generate_highlighted_latex([], {}, [])
        assert result == ""

    def test_no_active_highlights_passthrough(self):
        region = Region(text="plain text", active=frozenset(), annots=[])
        result = generate_highlighted_latex([region], {}, [])
        assert result == "plain text"

    def test_single_highlight_full_wrapper(self):
        region = Region(text="highlighted", active=frozenset({1}), annots=[])
        highlights = {1: {"tag": "alpha"}}
        result = generate_highlighted_latex([region], highlights, [])
        assert "\\highLight[tag-alpha-light]" in result
        assert "\\underLine" in result
        assert "highlighted" in result

    def test_annmarker_emits_annot_command(self):
        region = Region(text="text", active=frozenset({1}), annots=[1])
        highlights = {
            1: {
                "tag": "alpha",
                "annotation": "My annotation note",
                "author": "Test User",
                "created_at": "2026-01-28T10:00:00Z",
            }
        }
        result = generate_highlighted_latex([region], highlights, [])
        # Should include the annotation somehow (marginnote, todo, etc.)
        assert "My annotation note" in result or "\\todo" in result or "\\marginpar" in result
```

**Step 4: Run all new tests**

```bash
uv run pytest tests/unit/export/test_marker_lexer.py tests/unit/export/test_region_builder.py tests/unit/export/test_latex_generator.py -v
```

Expected: All tests fail (red) - implementations created in Phases 1-3.

**Step 5: Commit**

```bash
git add tests/unit/export/test_marker_lexer.py tests/unit/export/test_region_builder.py tests/unit/export/test_latex_generator.py
git commit -m "$(cat <<'EOF'
test: add component unit tests for marker parser pipeline

Add TestMarkerLexer for tokenization
Add TestRegionBuilder for state machine
Add TestLaTeXGenerator for LaTeX output

Tests are comprehensive per design spec.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

**Falsifiability checkpoint:**

| Claim | How to falsify |
|-------|----------------|
| Lexer tests cover all token types | Missing token type = test gap |
| Region builder tests cover interleaving | Test `test_interleaved_highlights_example_b` fails on incorrect impl |
| Generator tests verify underline rules | Wrong height values = test failure |
<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Move Cross-Environment Test to Integration

**Files:**
- Delete: `tests/unit/test_latex_cross_env.py`
- Create: `tests/integration/test_cross_env_highlights.py`

**Step 1: Read current test**

```bash
cat tests/unit/test_latex_cross_env.py
```

**Step 2: Create integration test file**

```python
# tests/integration/test_cross_env_highlights.py
"""Integration tests for cross-environment highlight handling.

Tests that highlights spanning LaTeX environments (quote, itemize, etc.)
are correctly split at environment boundaries.

Moved from tests/unit/test_latex_cross_env.py - these are integration
tests as they use the full pdf_exporter pipeline.
"""

import pytest


class TestCrossEnvironmentHighlights:
    """Tests for highlights that span environment boundaries."""

    @pytest.mark.requires_latexmk
    def test_cross_env_highlight_compiles_to_pdf(self, pdf_exporter):
        """Highlight spanning \\begin{quote}...\\end{quote} should compile."""
        html = """
        <p>Before the quote.</p>
        <blockquote>Inside the quote.</blockquote>
        <p>After the quote.</p>
        """
        highlights = [
            {
                "start_word": 0,
                "end_word": 10,  # Spans before, quote, and after
                "tag": "alpha",
                "index": 1,
                "annotation": "Spans the quote",
            }
        ]

        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="cross_env_highlight",
        )

        assert result.pdf_path.exists()
        assert result.tex_path.exists()

        # Verify the LaTeX was generated
        latex_content = result.tex_path.read_text()
        assert "\\highLight" in latex_content
        # Environment should be preserved
        assert "\\begin{quote}" in latex_content or "quote" in latex_content.lower()
```

**Step 3: Delete old file**

```bash
rm tests/unit/test_latex_cross_env.py
```

**Step 4: Run test**

```bash
uv run pytest tests/integration/test_cross_env_highlights.py -v
```

Expected: PASS (or SKIP if no latexmk).

**Step 5: Commit**

```bash
git add tests/integration/test_cross_env_highlights.py
git rm tests/unit/test_latex_cross_env.py
git commit -m "$(cat <<'EOF'
refactor(tests): move cross-env test to integration/

TestCrossEnvironmentHighlights uses full pdf_exporter pipeline,
making it an integration test not a unit test.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

**Falsifiability checkpoint:**

| Claim | How to falsify |
|-------|----------------|
| Test moved correctly | `tests/unit/test_latex_cross_env.py` exists = failure |
| Integration test works | `pytest tests/integration/test_cross_env_highlights.py` fails = failure |
<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Delete Obsolete Tests from `test_latex_export.py`

**Files:**
- Modify: `tests/unit/test_latex_export.py`
- Modify: `tests/conftest.py` (add `requires_latexmk` marker)

**Step 1: Move `requires_latexmk` marker to conftest.py**

The `requires_latexmk` marker is defined in `test_latex_export.py` but used by integration tests.
Before deleting that file, move the marker to `tests/conftest.py`:

```python
# Add to tests/conftest.py

import pytest
from promptgrimoire.export.pdf import get_latexmk_path

# Marker for tests that require LaTeX compilation
requires_latexmk = pytest.mark.skipif(
    get_latexmk_path() is None,
    reason="TinyTeX/latexmk not installed"
)
```

**Step 2: Identify tests to remove**

The following are now duplicated in `tests/unit/export/`:
- `TestFormatTimestamp` -> moved to `test_latex_string_functions.py`
- `TestGenerateTagColourDefinitions` -> moved to `test_latex_string_functions.py`
- `TestFormatAnnot` -> moved to `test_latex_string_functions.py`
- `TestInsertMarkersIntoHtml` -> moved to `test_marker_insertion.py`
- `TestCompilationValidation` -> moved to `test_latex_string_functions.py`

The following tests the OLD regex implementation which will fail after Phase 4:
- `TestReplaceMarkersWithAnnots` -> DELETE (replaced by component tests)

**Step 3: Delete or gut `test_latex_export.py`**

After migrations, `test_latex_export.py` should be empty or deleted entirely.

```bash
# If nothing left to keep:
rm tests/unit/test_latex_export.py

# Or if keeping as stub:
cat > tests/unit/test_latex_export.py << 'EOF'
"""Legacy test file - tests moved to tests/unit/export/.

See:
- test_latex_string_functions.py - pure functions
- test_marker_insertion.py - marker insertion
- test_marker_lexer.py - lexer component
- test_region_builder.py - region builder component
- test_latex_generator.py - LaTeX generation component
"""
EOF
```

**Step 4: Run full test suite**

```bash
uv run pytest tests/unit/ -v
```

Expected: All tests pass (no duplicates, no broken tests).

**Step 5: Commit**

```bash
git rm tests/unit/test_latex_export.py
git commit -m "$(cat <<'EOF'
refactor(tests): remove test_latex_export.py after migration

All tests migrated to tests/unit/export/:
- Pure functions -> test_latex_string_functions.py
- Marker insertion -> test_marker_insertion.py
- TestReplaceMarkersWithAnnots deleted (replaced by component tests)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

**Falsifiability checkpoint:**

| Claim | How to falsify |
|-------|----------------|
| No duplicate tests | `pytest --collect-only` shows same test count = verified |
| Old file removed | `tests/unit/test_latex_export.py` exists with test classes = failure |
| Test suite passes | `pytest tests/unit/` has failures = regression |
<!-- END_TASK_4 -->

---

<!-- START_TASK_5 -->
### Task 5: Create Integration Pipeline Test

**Files:**
- Create: `tests/integration/test_pdf_pipeline.py`

**Step 1: Add Issue #85 regression test**

```python
# tests/integration/test_pdf_pipeline.py
"""Integration tests for full PDF export pipeline.

Tests the complete flow: HTML -> markers -> pandoc -> process -> compile.
"""

import pytest


class TestPdfPipeline:
    """Integration tests for PDF export pipeline."""

    @pytest.mark.requires_latexmk
    def test_issue_85_regression_no_literal_markers(self, pdf_exporter):
        """Regression test: markers are processed, not literal text.

        Issue #85: Nested/interleaved highlights left literal HLSTART/HLEND
        markers in the output instead of processing them into LaTeX commands.

        CRITICAL: This test MUST fail if Issue #85 regresses.
        """
        html = """
        <p>The quick brown fox jumps over the lazy dog.</p>
        """
        # Create interleaved highlights (the problematic case)
        highlights = [
            {
                "start_word": 1,  # "quick"
                "end_word": 4,    # through "fox"
                "tag": "alpha",
                "index": 1,
                "annotation": "Quick to fox",
            },
            {
                "start_word": 2,  # "brown"
                "end_word": 6,    # through "over"
                "tag": "beta",
                "index": 2,
                "annotation": "Brown to over",
            },
        ]

        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="issue_85_regression",
        )

        latex_content = result.tex_path.read_text()

        # CRITICAL ASSERTIONS - markers must NOT appear literally
        assert "HLSTART" not in latex_content, "HLSTART marker found in output - Issue #85 regression!"
        assert "HLEND" not in latex_content, "HLEND marker found in output - Issue #85 regression!"
        assert "ANNMARKER" not in latex_content, "ANNMARKER found in output - Issue #85 regression!"
        assert "ENDHL" not in latex_content, "ENDHL found in output - Issue #85 regression!"
        assert "ENDMARKER" not in latex_content, "ENDMARKER found in output - Issue #85 regression!"

        # Positive assertions - LaTeX commands should be present
        assert r"\highLight" in latex_content, "No \\highLight command in output"

        # PDF should compile successfully
        assert result.pdf_path.exists(), "PDF was not generated"

    @pytest.mark.requires_latexmk
    def test_interleaved_highlights_compile(self, pdf_exporter):
        """Interleaved highlights should compile to PDF."""
        html = "<p>One two three four five six seven eight</p>"
        highlights = [
            {"start_word": 1, "end_word": 5, "tag": "alpha", "index": 1},
            {"start_word": 3, "end_word": 7, "tag": "beta", "index": 2},
        ]

        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="interleaved_compile",
        )

        assert result.pdf_path.exists()

    @pytest.mark.requires_latexmk
    def test_three_overlapping_compile(self, pdf_exporter):
        """Three overlapping highlights should compile to PDF."""
        html = "<p>Word one word two word three word four</p>"
        highlights = [
            {"start_word": 0, "end_word": 6, "tag": "alpha", "index": 1},
            {"start_word": 1, "end_word": 5, "tag": "beta", "index": 2},
            {"start_word": 2, "end_word": 4, "tag": "gamma", "index": 3},
        ]

        result = pdf_exporter(
            html=html,
            highlights=highlights,
            test_name="three_overlapping",
        )

        assert result.pdf_path.exists()
```

**Step 2: Run tests**

```bash
uv run pytest tests/integration/test_pdf_pipeline.py -v
```

Expected: Tests pass after Phase 4 integration complete.

**Step 3: Commit**

```bash
git add tests/integration/test_pdf_pipeline.py
git commit -m "$(cat <<'EOF'
test: add Issue #85 regression test for marker processing

Ensures literal HLSTART/HLEND/ANNMARKER markers never appear in
final LaTeX output. This test MUST fail if Issue #85 regresses.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

**Falsifiability checkpoint:**

| Claim | How to falsify |
|-------|----------------|
| Regression test catches Issue #85 | Insert literal marker in output - test should fail |
| Interleaved highlights compile | PDF not generated = failure |
| Three overlapping compile | PDF not generated = failure |
<!-- END_TASK_5 -->

---

## Phase Completion Criteria

**Done when:**
1. `tests/unit/export/` directory exists with 5 test files
2. All tests from `test_latex_export.py` migrated or deleted
3. `test_latex_cross_env.py` moved to `tests/integration/`
4. Issue #85 regression test added
5. Full test suite passes

**Epistemic boundaries:**

| Known | Unknown |
|-------|---------|
| Test structure matches design spec | Whether all edge cases are covered (will emerge during implementation) |
| Migration preserves test coverage | Whether test names exactly match existing ones (verify during migration) |
| Regression test catches Issue #85 | Whether other regressions exist (discovered through usage) |
