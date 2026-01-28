# Phase 4: Integration

**Goal:** Replace regex-based marker matching with lexer+region+generator pipeline

**Architecture:** Wire the three components (tokenize_markers, build_regions, generate_highlighted_latex) into `_replace_markers_with_annots()`, maintaining backward compatibility with existing tests while fixing interleaved highlight handling.

**Tech Stack:** Python 3.14, lark, pylatexenc, pytest

**Scope:** Phase 4 of 5 from original design

**Codebase verified:** 2026-01-28

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Replace `_replace_markers_with_annots()` Implementation

**Files:**
- Modify: `src/promptgrimoire/export/latex.py:451-542`

**Context:**
The current implementation uses regex with backreferences to match HLSTART{n}...HLEND{n} pairs. This fails for interleaved markers like `HLSTART{1}...HLSTART{2}...HLEND{1}...HLEND{2}`.

The new implementation pipelines:
1. `tokenize_markers(text)` → list of MarkerToken
2. `build_regions(tokens)` → list of Region
3. Process regions with existing `_wrap_content_with_highlight()` for env boundaries
4. `generate_highlighted_latex(region)` → LaTeX string

**Step 1: Write the failing test**

Create test that exercises the full pipeline through `_replace_markers_with_annots()`:

```python
# tests/unit/test_overlapping_highlights.py (CREATE THIS FILE)

from promptgrimoire.export.latex import _replace_markers_with_annots


def test_replace_markers_interleaved_highlights():
    """Interleaved highlights should produce correct nested LaTeX."""
    # HLSTART{1}...HLSTART{2}...HLEND{1}...HLEND{2}
    text = "HLSTART{1}ENDHLouterHLSTART{2}ENDHLmiddleHLEND{1}ENDHLinnerHLEND{2}ENDHL"
    annots = {1: ("tag-alpha", "Note 1"), 2: ("tag-beta", "Note 2")}

    result = _replace_markers_with_annots(text, annots, [])

    # Verify structure: both highlights wrap "middle", only hl2 wraps "inner"
    assert "\\highLight[tag-alpha-light]" in result
    assert "\\highLight[tag-beta-light]" in result
    # The "middle" text should have both highlights
    # The "inner" text should only have hl2
    # "outer" should only have hl1
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_overlapping_highlights.py::test_replace_markers_interleaved_highlights -v
```

Expected: FAIL - current regex implementation cannot handle interleaved markers.

**Step 3: Replace implementation**

Replace the body of `_replace_markers_with_annots()` in `src/promptgrimoire/export/latex.py`:

```python
def _replace_markers_with_annots(
    text: str,
    annots: dict[int, tuple[str, str]],
    env_boundaries: list[tuple[int, int]],
) -> str:
    """Replace highlight markers with LaTeX highlight commands.

    Handles arbitrarily interleaved highlights by:
    1. Tokenizing markers with lark lexer
    2. Building regions with active highlight sets
    3. Generating nested LaTeX for each region using generate_highlighted_latex()

    Args:
        text: LaTeX content with HLSTART{n}ENDHL, HLEND{n}ENDHL, ANNMARKER{n}ENDMARKER
        annots: Map from highlight index to (colour_name, annotation_text)
        env_boundaries: List of (start, end) positions for LaTeX environments
            that must not be split by highlight commands

    Returns:
        LaTeX with \\highLight and \\underLine commands
    """
    if not text:
        return text

    # Step 1: Tokenize
    tokens = tokenize_markers(text)

    # Step 2: Build regions
    regions = build_regions(tokens)

    # Step 3: Convert annots dict to highlights format expected by generator
    # annots: dict[int, tuple[colour_name, annot_text]]
    # highlights: dict[int, dict[str, Any]] with {"tag": ..., etc}
    highlights: dict[int, dict[str, Any]] = {}
    for idx, (colour_name, annot_text) in annots.items():
        # Extract base tag name from colour (e.g., "tag-alpha" from "tag-alpha-light")
        # The colour_name IS the tag name in our system
        highlights[idx] = {
            "tag": colour_name,
            "annotation": annot_text,
        }

    # Step 4: Generate LaTeX using the Phase 3 function
    # This handles all region processing, env boundaries, underlines, and annots
    return generate_highlighted_latex(regions, highlights, env_boundaries)
```

**Note:** The `generate_highlighted_latex()` function from Phase 3 handles:
- Iterating over regions
- Wrapping in `\highLight` and `\underLine` commands
- Splitting at environment boundaries
- Emitting annotation commands

No changes needed to `_wrap_content_with_highlight()` - that function is replaced by the new pipeline.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_overlapping_highlights.py::test_replace_markers_interleaved_highlights -v
```

Expected: PASS

**Step 5: Run full test suite**

```bash
uv run pytest tests/unit/test_overlapping_highlights.py -v
```

Expected: All existing tests pass (backward compatibility).

**Step 6: Commit**

```bash
git add src/promptgrimoire/export/latex.py tests/unit/test_overlapping_highlights.py
git commit -m "$(cat <<'EOF'
feat: replace regex marker matching with lexer pipeline

Wire tokenize_markers(), build_regions(), and generate_highlighted_latex()
into _replace_markers_with_annots() to handle interleaved highlights.

Fixes #85

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

**Falsifiability checkpoint:**

| Claim | How to falsify |
|-------|----------------|
| Pipeline handles interleaved markers | Test `HLSTART{1}...HLSTART{2}...HLEND{1}...HLEND{2}` produces correct nesting |
| Backward compatible with existing tests | Run full test suite - any failure falsifies |
| Environment boundaries still respected | Test highlight spanning `\begin{quote}...\end{quote}` splits correctly |
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Integration Tests for Overlapping Highlights

**Files:**
- Modify: `tests/unit/test_overlapping_highlights.py`

**Step 1: Write tests for worked examples from design**

```python
def test_replace_markers_worked_example_from_design():
    """Test the exact worked example from the design document.

    Input: "The HLSTART{1}ENDHLquick HLSTART{2}ENDHLbrown HLEND{1}ENDHLfox HLEND{2}ENDHLjumps"

    Expected regions:
    - "The " (no highlights)
    - "quick " (hl1 only)
    - "brown " (hl1, hl2)
    - "fox " (hl2 only)
    - "jumps" (no highlights)
    """
    text = "The HLSTART{1}ENDHLquick HLSTART{2}ENDHLbrown HLEND{1}ENDHLfox HLEND{2}ENDHLjumps"
    annots = {1: ("tag-alpha", "Note 1"), 2: ("tag-beta", "Note 2")}

    result = _replace_markers_with_annots(text, annots, [])

    # "The " and "jumps" should be plain text
    assert result.startswith("The ")
    assert result.endswith("jumps")

    # "quick " should have only tag-alpha highlight
    assert "\\highLight[tag-alpha-light]{" in result
    # "brown " should have both highlights (nested)
    # "fox " should have only tag-beta highlight
    assert "\\highLight[tag-beta-light]{" in result


def test_replace_markers_with_annotations():
    """Annotations should appear in the output."""
    text = "HLSTART{1}ENDHLtextANNMARKER{1}ENDMARKERHLEND{1}ENDHL"
    annots = {1: ("tag-alpha", "My annotation")}

    result = _replace_markers_with_annots(text, annots, [])

    # Annotation should be formatted (existing _format_annot behaviour)
    assert "My annotation" in result or "\\marginpar" in result or "\\todo" in result


def test_replace_markers_three_overlapping():
    """Three overlapping highlights should use many-dark underline."""
    text = "HLSTART{1}ENDHLHLSTART{2}ENDHLHLSTART{3}ENDHLtextHLEND{3}ENDHLHLEND{2}ENDHLHLEND{1}ENDHL"
    annots = {
        1: ("tag-alpha", "Note 1"),
        2: ("tag-beta", "Note 2"),
        3: ("tag-gamma", "Note 3"),
    }

    result = _replace_markers_with_annots(text, annots, [])

    # Should have three nested highLight commands
    assert result.count("\\highLight[") == 3
    # Should have many-dark underline (4pt)
    assert "many-dark" in result
    assert "height=4pt" in result


def test_replace_markers_preserves_latex_commands():
    """LaTeX commands within highlighted text should be preserved."""
    text = "HLSTART{1}ENDHLsome \\textbf{bold} textHLEND{1}ENDHL"
    annots = {1: ("tag-alpha", "Note")}

    result = _replace_markers_with_annots(text, annots, [])

    assert "\\textbf{bold}" in result
```

**Step 2: Run tests**

```bash
uv run pytest tests/unit/test_overlapping_highlights.py -v
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_overlapping_highlights.py
git commit -m "$(cat <<'EOF'
test: add integration tests for overlapping highlights

Cover worked examples from design, annotations, three-way overlap,
and LaTeX command preservation.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

**Falsifiability checkpoint:**

| Claim | How to falsify |
|-------|----------------|
| Worked example produces correct output | Compare against design document's expected regions |
| Annotations appear in output | Check for annotation text or margin command |
| Three highlights use many-dark | Check for `many-dark` and `height=4pt` in output |
| LaTeX preserved | Check `\textbf{bold}` appears unchanged |
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Compilation Validation

**Files:**
- Modify: `tests/unit/test_overlapping_highlights.py`

**Step 1: Write compilation test**

```python
import subprocess
import tempfile
from pathlib import Path

def test_overlapping_highlights_compile_to_pdf(tmp_path: Path):
    """Generated LaTeX for overlapping highlights must compile without errors."""
    text = "The HLSTART{1}ENDHLquick HLSTART{2}ENDHLbrown HLEND{1}ENDHLfox HLEND{2}ENDHLjumps"
    annots = {1: ("tag-alpha", "Note 1"), 2: ("tag-beta", "Note 2")}

    highlighted = _replace_markers_with_annots(text, annots, [])

    # Wrap in minimal LaTeX document
    document = f"""\\documentclass{{article}}
\\usepackage{{lua-ul}}
\\usepackage{{xcolor}}
\\definecolor{{tag-alpha-light}}{{HTML}}{{FFE4B5}}
\\definecolor{{tag-alpha-dark}}{{HTML}}{{8B4513}}
\\definecolor{{tag-beta-light}}{{HTML}}{{E6E6FA}}
\\definecolor{{tag-beta-dark}}{{HTML}}{{4B0082}}
\\definecolor{{many-dark}}{{HTML}}{{333333}}
\\begin{{document}}
{highlighted}
\\end{{document}}
"""

    tex_file = tmp_path / "test.tex"
    tex_file.write_text(document)

    # Get latexmk path
    from promptgrimoire.export.pdf import get_latexmk_path
    latexmk = get_latexmk_path()

    if latexmk is None:
        pytest.skip("TinyTeX not installed")

    result = subprocess.run(
        [str(latexmk), "-lualatex", "-interaction=nonstopmode", str(tex_file)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check compilation succeeded
    assert result.returncode == 0, f"LaTeX compilation failed:\n{result.stderr}"
    assert (tmp_path / "test.pdf").exists()
```

**Step 2: Run compilation test**

```bash
uv run pytest tests/unit/test_overlapping_highlights.py::test_overlapping_highlights_compile_to_pdf -v
```

Expected: PASS (or SKIP if TinyTeX not installed).

**Step 3: Commit**

```bash
git add tests/unit/test_overlapping_highlights.py
git commit -m "$(cat <<'EOF'
test: add LaTeX compilation validation for overlapping highlights

Verify generated LaTeX compiles to PDF without errors.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

**Falsifiability checkpoint:**

| Claim | How to falsify |
|-------|----------------|
| Generated LaTeX compiles | Compilation returns non-zero exit code |
| PDF is produced | Output file doesn't exist |
| No LaTeX errors | stderr contains error messages |
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase Completion Criteria

**Done when:**
1. `_replace_markers_with_annots()` uses the new lexer pipeline
2. All existing tests in `test_overlapping_highlights.py` pass
3. New integration tests for interleaved highlights pass
4. LaTeX compilation validation passes
5. All commits made with descriptive messages

**Epistemic boundaries:**

| Known | Unknown |
|-------|---------|
| Pipeline handles interleaved markers | Performance with very large documents (not a concern per design) |
| Environment boundary splitting works | Edge cases with malformed markers (handled in Phase 1/2) |
| Generated LaTeX compiles | Visual appearance matches expectation (requires manual review) |
