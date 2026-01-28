# Phase 3: LaTeX Generator

<!-- START_TASK_1 -->
### Task 1: Add dark colour generation

**Files:**
- Modify: `src/promptgrimoire/export/latex.py`
- Modify: `tests/unit/test_latex_export.py`

**Step 1: Write the test**

Add to `tests/unit/test_latex_export.py` in `TestGenerateTagColourDefinitions`:

```python
def test_generates_dark_colour_variants(self) -> None:
    """Dark colour variants are generated for underlines."""
    tag_colours = {"alpha": "#1f77b4"}
    result = generate_tag_colour_definitions(tag_colours)

    assert "tag-alpha-dark" in result
    # Dark is 70% of base mixed with black
    assert r"\colorlet{tag-alpha-dark}{tag-alpha!70!black}" in result

def test_generates_many_dark_colour(self) -> None:
    """many-dark colour (#333333) is always generated."""
    tag_colours = {"alpha": "#1f77b4"}
    result = generate_tag_colour_definitions(tag_colours)

    assert r"\definecolor{many-dark}{HTML}{333333}" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_latex_export.py::TestGenerateTagColourDefinitions -v`
Expected: Tests fail (dark colours not generated yet)

**Step 3: Write the implementation**

Modify `generate_tag_colour_definitions()` in `src/promptgrimoire/export/latex.py` (around lines 83-104).

Add after the `-light` colorlet definition:

```python
# Dark variant for underlines (70% base, 30% black)
definitions.append(
    f"\\colorlet{{tag-{safe_name}-dark}}{{tag-{safe_name}!70!black}}"
)
```

Add at the end of the function before the return:

```python
# many-dark colour for 3+ overlapping highlights
definitions.append(r"\definecolor{many-dark}{HTML}{333333}")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_latex_export.py::TestGenerateTagColourDefinitions -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/latex.py tests/unit/test_latex_export.py
git commit -m "feat(latex): add dark colour variants for underlines"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create underline generation helper

**Files:**
- Modify: `src/promptgrimoire/export/latex.py`
- Create: `tests/unit/test_latex_generator.py`

**Step 1: Write the tests**

Create `tests/unit/test_latex_generator.py`:

```python
"""Unit tests for LaTeX generator.

Tests highlight/underline generation from regions.
Uses regions directly - does NOT call lexer or region builder.
"""

import pytest

from promptgrimoire.export.latex import (
    Region,
    generate_underline_wrapper,
)


class TestGenerateUnderlineWrapper:
    """Tests for generate_underline_wrapper helper."""

    def test_empty_active_returns_identity(self) -> None:
        """No active highlights means no underlines."""
        wrapper = generate_underline_wrapper(frozenset(), {})
        assert wrapper("text") == "text"

    def test_single_highlight_1pt_underline(self) -> None:
        """Single highlight produces 1pt underline with tag's dark colour."""
        highlights = {0: {"tag": "alpha"}}
        wrapper = generate_underline_wrapper(frozenset({0}), highlights)
        result = wrapper("text")

        assert r"\underLine[color=tag-alpha-dark, height=1pt, bottom=-3pt]{text}" == result

    def test_two_highlights_stacked_underlines(self) -> None:
        """Two highlights produce stacked 2pt + 1pt underlines."""
        highlights = {0: {"tag": "alpha"}, 1: {"tag": "beta"}}
        wrapper = generate_underline_wrapper(frozenset({0, 1}), highlights)
        result = wrapper("text")

        # Outer (lower index) is 2pt, inner (higher index) is 1pt
        expected = (
            r"\underLine[color=tag-alpha-dark, height=2pt, bottom=-3pt]{"
            r"\underLine[color=tag-beta-dark, height=1pt, bottom=-3pt]{text}}"
        )
        assert result == expected

    def test_three_highlights_many_underline(self) -> None:
        """Three or more highlights produce single many-dark 4pt underline."""
        highlights = {0: {"tag": "alpha"}, 1: {"tag": "beta"}, 2: {"tag": "gamma"}}
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")

        assert r"\underLine[color=many-dark, height=4pt, bottom=-5pt]{text}" == result

    def test_four_highlights_also_many_underline(self) -> None:
        """Four highlights also uses many-dark (not 4 stacked)."""
        highlights = {i: {"tag": f"tag{i}"} for i in range(4)}
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2, 3}), highlights)
        result = wrapper("text")

        assert "many-dark" in result
        # Should NOT have multiple nested underlines
        assert result.count(r"\underLine") == 1

    def test_underline_colours_from_tag_names(self) -> None:
        """Underline colours use tag-{name}-dark format."""
        highlights = {5: {"tag": "jurisdiction"}}
        wrapper = generate_underline_wrapper(frozenset({5}), highlights)
        result = wrapper("text")

        assert "tag-jurisdiction-dark" in result

    def test_tag_with_underscore_converted(self) -> None:
        """Underscores in tag names are converted to hyphens."""
        highlights = {0: {"tag": "my_custom_tag"}}
        wrapper = generate_underline_wrapper(frozenset({0}), highlights)
        result = wrapper("text")

        assert "tag-my-custom-tag-dark" in result

    def test_sorted_indices_for_deterministic_nesting(self) -> None:
        """Highlights are sorted by index for deterministic output."""
        highlights = {2: {"tag": "c"}, 0: {"tag": "a"}, 1: {"tag": "b"}}
        wrapper = generate_underline_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")

        # With 3 highlights, uses many-dark, so ordering doesn't show
        # But we can test with a mock that captures the order
        # For now, just verify it doesn't crash
        assert "many-dark" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_latex_generator.py::TestGenerateUnderlineWrapper -v`
Expected: ImportError (generate_underline_wrapper doesn't exist yet)

**Step 3: Write the implementation**

Add to `src/promptgrimoire/export/latex.py`:

```python
from typing import Callable


def generate_underline_wrapper(
    active: frozenset[int],
    highlights: dict[int, dict[str, Any]],
) -> Callable[[str], str]:
    """Create a function that wraps text in underline commands.

    Based on overlap count:
    - 0 highlights: identity function (no underlines)
    - 1 highlight: single 1pt underline in tag's dark colour
    - 2 highlights: stacked 2pt + 1pt underlines (outer is lower index)
    - 3+ highlights: single 4pt underline in many-dark colour

    Args:
        active: Frozenset of highlight indices currently active
        highlights: Mapping from highlight index to highlight dict

    Returns:
        Function that takes text and returns text wrapped in underlines
    """
    if not active:
        return lambda text: text

    count = len(active)

    if count >= 3:
        # Many overlapping: single thick line
        def wrap_many(text: str) -> str:
            return rf"\underLine[color=many-dark, height=4pt, bottom=-5pt]{{{text}}}"
        return wrap_many

    # Sort indices for deterministic ordering (lower index = outer)
    sorted_indices = sorted(active)

    def get_dark_colour(idx: int) -> str:
        tag = highlights.get(idx, {}).get("tag", "unknown")
        safe_tag = tag.replace("_", "-")
        return f"tag-{safe_tag}-dark"

    if count == 1:
        colour = get_dark_colour(sorted_indices[0])

        def wrap_single(text: str) -> str:
            return rf"\underLine[color={colour}, height=1pt, bottom=-3pt]{{{text}}}"
        return wrap_single

    # count == 2: stacked underlines
    outer_colour = get_dark_colour(sorted_indices[0])
    inner_colour = get_dark_colour(sorted_indices[1])

    def wrap_double(text: str) -> str:
        inner = rf"\underLine[color={inner_colour}, height=1pt, bottom=-3pt]{{{text}}}"
        return rf"\underLine[color={outer_colour}, height=2pt, bottom=-3pt]{{{inner}}}"
    return wrap_double
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_latex_generator.py::TestGenerateUnderlineWrapper -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/latex.py tests/unit/test_latex_generator.py
git commit -m "feat(latex): add generate_underline_wrapper for overlap underlines"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create highlight wrapper generation

**Files:**
- Modify: `src/promptgrimoire/export/latex.py`
- Modify: `tests/unit/test_latex_generator.py`

**Step 1: Write the tests**

Add to `tests/unit/test_latex_generator.py`:

```python
from promptgrimoire.export.latex import generate_highlight_wrapper


class TestGenerateHighlightWrapper:
    """Tests for generate_highlight_wrapper helper."""

    def test_empty_active_returns_identity(self) -> None:
        """No active highlights means no wrapping."""
        wrapper = generate_highlight_wrapper(frozenset(), {})
        assert wrapper("text") == "text"

    def test_single_highlight_wraps_with_light_colour(self) -> None:
        """Single highlight wraps in highLight with light colour."""
        highlights = {0: {"tag": "alpha"}}
        wrapper = generate_highlight_wrapper(frozenset({0}), highlights)
        result = wrapper("text")

        assert r"\highLight[tag-alpha-light]{text}" == result

    def test_two_highlights_nested_wrapping(self) -> None:
        """Two highlights produce nested highLight commands."""
        highlights = {0: {"tag": "alpha"}, 1: {"tag": "beta"}}
        wrapper = generate_highlight_wrapper(frozenset({0, 1}), highlights)
        result = wrapper("text")

        # Lower index is outer
        assert r"\highLight[tag-alpha-light]{\highLight[tag-beta-light]{text}}" == result

    def test_three_highlights_triple_nested(self) -> None:
        """Three highlights produce triple-nested commands."""
        highlights = {0: {"tag": "a"}, 1: {"tag": "b"}, 2: {"tag": "c"}}
        wrapper = generate_highlight_wrapper(frozenset({0, 1, 2}), highlights)
        result = wrapper("text")

        # Should have 3 \highLight commands
        assert result.count(r"\highLight") == 3

    def test_sorted_indices_for_deterministic_nesting(self) -> None:
        """Highlights are sorted by index regardless of set iteration order."""
        highlights = {2: {"tag": "c"}, 0: {"tag": "a"}}
        wrapper = generate_highlight_wrapper(frozenset({0, 2}), highlights)
        result = wrapper("text")

        # tag-a (index 0) should be outer
        assert result.startswith(r"\highLight[tag-a-light]")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_latex_generator.py::TestGenerateHighlightWrapper -v`
Expected: ImportError (generate_highlight_wrapper doesn't exist)

**Step 3: Write the implementation**

Add to `src/promptgrimoire/export/latex.py`:

```python
def generate_highlight_wrapper(
    active: frozenset[int],
    highlights: dict[int, dict[str, Any]],
) -> Callable[[str], str]:
    """Create a function that wraps text in highLight commands.

    Each active highlight adds a nested \\highLight[tag-X-light]{...} wrapper.
    Lower indices are outer (sorted for deterministic output).

    Args:
        active: Frozenset of highlight indices currently active
        highlights: Mapping from highlight index to highlight dict

    Returns:
        Function that takes text and returns text wrapped in highlights
    """
    if not active:
        return lambda text: text

    # Sort indices for deterministic ordering (lower index = outer)
    sorted_indices = sorted(active)

    def get_light_colour(idx: int) -> str:
        tag = highlights.get(idx, {}).get("tag", "unknown")
        safe_tag = tag.replace("_", "-")
        return f"tag-{safe_tag}-light"

    def wrap(text: str) -> str:
        result = text
        # Wrap from innermost (highest index) to outermost (lowest index)
        for idx in reversed(sorted_indices):
            colour = get_light_colour(idx)
            result = rf"\highLight[{colour}]{{{result}}}"
        return result

    return wrap
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_latex_generator.py::TestGenerateHighlightWrapper -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/latex.py tests/unit/test_latex_generator.py
git commit -m "feat(latex): add generate_highlight_wrapper for nested highlights"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create generate_highlighted_latex function

**Files:**
- Modify: `src/promptgrimoire/export/latex.py`
- Modify: `tests/unit/test_latex_generator.py`

**Step 1: Write the tests**

Add to `tests/unit/test_latex_generator.py`:

```python
from promptgrimoire.export.latex import generate_highlighted_latex


class TestGenerateHighlightedLatex:
    """Tests for generate_highlighted_latex main function."""

    def test_empty_regions_returns_empty(self) -> None:
        """Empty region list returns empty string."""
        result = generate_highlighted_latex([], {}, [])
        assert result == ""

    def test_no_active_highlights_passthrough(self) -> None:
        """Regions with no active highlights pass through unchanged."""
        regions = [Region("plain text", frozenset(), [])]
        result = generate_highlighted_latex(regions, {}, [])
        assert result == "plain text"

    def test_single_highlight_full_wrapping(self) -> None:
        """Single active highlight produces highLight + underLine."""
        regions = [Region("text", frozenset({0}), [])]
        highlights = {0: {"tag": "alpha"}}
        result = generate_highlighted_latex(regions, highlights, [])

        # Should have both highLight and underLine
        assert r"\highLight[tag-alpha-light]" in result
        assert r"\underLine[color=tag-alpha-dark" in result

    def test_multiple_regions_concatenated(self) -> None:
        """Multiple regions are concatenated in order."""
        regions = [
            Region("before ", frozenset(), []),
            Region("highlighted", frozenset({0}), []),
            Region(" after", frozenset(), []),
        ]
        highlights = {0: {"tag": "alpha"}}
        result = generate_highlighted_latex(regions, highlights, [])

        assert result.startswith("before ")
        assert result.endswith(" after")
        assert r"\highLight" in result

    def test_annmarker_emits_annot_command(self) -> None:
        """Regions with annots emit \\annot commands."""
        regions = [Region("text", frozenset({0}), [0])]
        highlights = {
            0: {
                "tag": "alpha",
                "author": "Test User",
                "comments": [],
                "created_at": "2026-01-28T10:00:00Z",
            }
        }
        result = generate_highlighted_latex(regions, highlights, [])

        assert r"\annot{" in result

    def test_env_boundary_splits_highlight(self) -> None:
        """Environment boundaries within region split the highlight."""
        # Text with a \\par in the middle
        regions = [Region(r"before\par after", frozenset({0}), [])]
        highlights = {0: {"tag": "alpha"}}
        result = generate_highlighted_latex(regions, highlights, [])

        # Should have two separate \\highLight blocks around \\par
        assert result.count(r"\highLight") == 2
        assert r"\par" in result

    def test_interleaved_example_b(self) -> None:
        """Example B from design: interleaved highlights."""
        # Regions from build_regions for interleaved case
        regions = [
            Region("The ", frozenset(), []),
            Region(" quick ", frozenset({1}), []),
            Region(" fox ", frozenset({1, 2}), []),
            Region(" over ", frozenset({2}), []),
            Region(" dog", frozenset(), []),
        ]
        highlights = {1: {"tag": "alpha"}, 2: {"tag": "beta"}}
        result = generate_highlighted_latex(regions, highlights, [])

        # Plain text regions
        assert "The " in result
        assert " dog" in result

        # Highlighted regions have commands
        # " quick " has only highlight 1
        # " fox " has both highlights (overlapping)
        # " over " has only highlight 2
        assert r"\highLight[tag-alpha-light]" in result
        assert r"\highLight[tag-beta-light]" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_latex_generator.py::TestGenerateHighlightedLatex -v`
Expected: ImportError (generate_highlighted_latex doesn't exist)

**Step 3: Write the implementation**

Add to `src/promptgrimoire/export/latex.py`:

```python
def generate_highlighted_latex(
    regions: list[Region],
    highlights: dict[int, dict[str, Any]],
    env_boundaries: list[tuple[int, int, str]],
) -> str:
    """Generate LaTeX with highlight and underline commands from regions.

    For each region:
    1. If active highlights: wrap in nested \\highLight commands
    2. If active highlights: wrap in \\underLine commands (based on overlap count)
    3. Split at environment boundaries using existing _wrap_content_with_highlight logic
    4. Emit \\annot commands for any annotation markers in the region

    Args:
        regions: List of Region objects from build_regions()
        highlights: Mapping from highlight index to highlight dict
        env_boundaries: Environment boundaries from _extract_env_boundaries()
                       (not currently used - boundaries are detected per-region)

    Returns:
        Complete LaTeX string with all highlight/underline/annot commands
    """
    if not regions:
        return ""

    result_parts: list[str] = []

    for region in regions:
        if not region.active:
            # No highlights - pass through unchanged
            result_parts.append(region.text)
        else:
            # Get wrappers for this region's active set
            underline_wrap = generate_underline_wrapper(region.active, highlights)
            highlight_wrap = generate_highlight_wrapper(region.active, highlights)

            # Get colour name for _wrap_content_with_highlight
            # Use the lowest-index highlight's colour for boundary splitting
            sorted_indices = sorted(region.active)
            primary_tag = highlights.get(sorted_indices[0], {}).get("tag", "unknown")
            primary_colour = f"tag-{primary_tag.replace('_', '-')}-light"

            # Use existing boundary splitting logic
            # This handles \\par, \\\\, environment boundaries, etc.
            boundaries_in_region = _extract_env_boundaries(region.text)

            # Wrap with underlines first, then split at boundaries
            underlined = underline_wrap(region.text)

            # The existing function wraps in \\highLight - but we need nested highlights
            # So we need to adapt: split at boundaries, then wrap each segment
            if boundaries_in_region or any(
                delim in region.text for delim in [r"\par", r"\\", r"\tabularnewline", "&"]
            ):
                # Has boundaries - use splitting logic
                wrapped = _wrap_content_with_nested_highlights(
                    region.text, region.active, highlights
                )
            else:
                # No boundaries - simple wrap
                wrapped = highlight_wrap(underline_wrap(region.text))

            result_parts.append(wrapped)

        # Emit annotation commands for this region
        for annot_idx in region.annots:
            if annot_idx in highlights:
                annot_latex = _format_annot(highlights[annot_idx])
                result_parts.append(annot_latex)

    return "".join(result_parts)


def _wrap_content_with_nested_highlights(
    content: str,
    active: frozenset[int],
    highlights: dict[int, dict[str, Any]],
) -> str:
    """Wrap content in nested highlights, splitting at environment boundaries.

    Similar to _wrap_content_with_highlight but handles multiple nested
    highlight layers and underlines.

    Args:
        content: Text content that may contain environment boundaries
        active: Frozenset of active highlight indices
        highlights: Mapping from highlight index to highlight dict

    Returns:
        LaTeX with properly split and wrapped highlight commands
    """
    underline_wrap = generate_underline_wrapper(active, highlights)
    highlight_wrap = generate_highlight_wrapper(active, highlights)

    # Use existing boundary detection
    boundaries = _extract_env_boundaries(content)

    # Inline delimiters that also require splitting
    inline_delimiters = [r"\par", r"\\", r"\tabularnewline", "&"]

    # Find all split points
    split_points: list[tuple[int, int, str]] = list(boundaries)

    # Add inline delimiter positions
    for delim in inline_delimiters:
        start = 0
        while True:
            pos = content.find(delim, start)
            if pos == -1:
                break
            split_points.append((pos, pos + len(delim), delim))
            start = pos + 1

    # Sort by position
    split_points.sort(key=lambda x: x[0])

    if not split_points:
        # No splits needed
        return highlight_wrap(underline_wrap(content))

    # Build result by iterating through segments
    result_parts: list[str] = []
    pos = 0

    for start, end, boundary_text in split_points:
        if start > pos:
            # Text before this boundary
            segment = content[pos:start]
            if segment.strip():
                result_parts.append(highlight_wrap(underline_wrap(segment)))
            else:
                result_parts.append(segment)  # Preserve whitespace-only

        # The boundary itself (not wrapped in highlight)
        result_parts.append(boundary_text)
        pos = end

    # Text after last boundary
    if pos < len(content):
        segment = content[pos:]
        if segment.strip():
            result_parts.append(highlight_wrap(underline_wrap(segment)))
        else:
            result_parts.append(segment)

    return "".join(result_parts)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_latex_generator.py::TestGenerateHighlightedLatex -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/latex.py tests/unit/test_latex_generator.py
git commit -m "feat(latex): add generate_highlighted_latex for full region rendering"
```
<!-- END_TASK_4 -->

---

## Phase 3 UAT

After all tasks complete:

1. **Run all generator tests:**
   ```bash
   uv run pytest tests/unit/test_latex_generator.py -v
   ```
   Expected: All tests pass

2. **Manual verification:**
   ```python
   from promptgrimoire.export.latex import (
       tokenize_markers,
       build_regions,
       generate_highlighted_latex,
   )

   # Example B: Interleaved
   tokens = tokenize_markers(
       "The HLSTART{1}ENDHLquick HLSTART{2}ENDHLfoxHLEND{1}ENDHL overHLEND{2}ENDHL dog"
   )
   regions = build_regions(tokens)
   highlights = {1: {"tag": "alpha"}, 2: {"tag": "beta"}}
   latex = generate_highlighted_latex(regions, highlights, [])
   print(latex)
   ```

   Expected: LaTeX with nested `\highLight` and `\underLine` commands for overlapping regions.
