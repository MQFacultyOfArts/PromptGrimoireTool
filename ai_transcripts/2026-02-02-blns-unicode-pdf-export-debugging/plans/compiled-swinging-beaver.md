# Plan: Cross-Environment Highlight Styling Demonstration Test

## Background

Previous work (now complete):
- Log path on failure: LaTeXCompilationError exception shows tex/log paths
- Stale export cleanup: User-scoped export directories
- CLI tool: `uv run show-export-log [--tex|--both]`
- E2E artifacts: PDF saved to `output/e2e/`

## Current Problem

LaTeX compilation crashes with "Lonely \item" error when highlights span list environment boundaries. The `highlight_wrapper()` function in `latex.py` splits on `\par`, `\\`, `\tabularnewline`, and `&`, but NOT on:
- `\item`
- `\begin{enumerate}` / `\end{enumerate}`
- `\begin{itemize}` / `\end{itemize}`

This causes malformed LaTeX like:
```latex
\highLight[color]{\item First item}  % OK
\highLight[color]{Second}  % Orphaned closing brace outside the list
}
```

Before fixing, user wants to see the LaTeX output to approve the intended styling approach.

## Plan: Unit Test for Cross-Environment Highlights

Create a unit test that:
1. Uses 183.rtf → HTML (via `parsed_lawlis` fixture from test_rtf_parser.py)
2. Creates highlights spanning list boundaries (words 848-905 per E2E test spec)
3. Converts HTML → LaTeX via `convert_html_with_annotations()`
4. Saves LaTeX to `output/unit/test_latex_cross_env/` for inspection
5. Also attempts PDF compilation to confirm the "Lonely \item" error

### Test Location

**File:** `tests/unit/test_latex_cross_env.py`

### Test Structure

```python
"""Tests for LaTeX highlight behavior across environment boundaries.

These tests demonstrate the current (broken) behavior where highlights
spanning list items cause LaTeX compilation errors. The output artifacts
allow visual inspection before implementing fixes.
"""

from pathlib import Path

import pytest

from promptgrimoire.export.latex import (
    build_annotation_preamble,
    convert_html_with_annotations,
)
from promptgrimoire.export.pdf import LaTeXCompilationError, compile_latex
from promptgrimoire.models import ParsedRTF
from promptgrimoire.parsers.rtf import parse_rtf

# Output directory for inspection
_OUTPUT_DIR = Path("output/unit/test_latex_cross_env")

# Reuse the parsed RTF fixture from test_rtf_parser
pytestmark = pytest.mark.xdist_group("rtf_parser")


@pytest.fixture(scope="module")
def parsed_lawlis() -> ParsedRTF:
    """Parse 183.rtf once for all tests in module."""
    path = Path(__file__).parent.parent / "fixtures" / "183.rtf"
    return parse_rtf(path)


# Standard tag colours from live_annotation_demo.py
TAG_COLOURS = {
    "jurisdiction": "#1f77b4",
    "procedural_history": "#ff7f0e",
    "legally_relevant_facts": "#2ca02c",
    "legal_issues": "#d62728",
    "reasons": "#9467bd",
    "courts_reasoning": "#8c564b",
    "decision": "#e377c2",
    "order": "#7f7f7f",
    "domestic_sources": "#bcbd22",
    "reflection": "#17becf",
}


class TestCrossEnvironmentHighlights:
    """Tests demonstrating highlight behavior across list boundaries."""

    def test_highlight_spanning_list_items_generates_latex(
        self, parsed_lawlis: ParsedRTF
    ) -> None:
        """Generate LaTeX with highlight spanning list items for inspection.

        Uses words 848-905 which span across an \item boundary in the source
        document (per E2E test spec: order tag overlaps with reasons).
        """
        # Highlight spanning list boundary
        highlights = [
            {
                "start_word": 848,
                "end_word": 906,  # CRDT uses exclusive end
                "tag": "order",
                "author": "Test User",
                "text": "test",
                "comments": [],
                "created_at": "2026-01-27T10:00:00+00:00",
            }
        ]

        # Convert to LaTeX
        latex_body = convert_html_with_annotations(
            html=parsed_lawlis.html,
            highlights=highlights,
            tag_colours=TAG_COLOURS,
        )

        # Build complete document
        preamble = build_annotation_preamble(TAG_COLOURS)
        document = f"""\\documentclass[a4paper,12pt]{{article}}
{preamble}

\\begin{{document}}

{latex_body}

\\end{{document}}
"""

        # Save for inspection
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        tex_path = _OUTPUT_DIR / "cross_env_highlight.tex"
        tex_path.write_text(document)

        # Basic assertions
        assert "\\highLight" in latex_body
        assert "\\annot{tag-order}" in latex_body

        print(f"\nLaTeX saved to: {tex_path.absolute()}")

    def test_compilation_fails_with_lonely_item(
        self, parsed_lawlis: ParsedRTF
    ) -> None:
        """Confirm that cross-environment highlights cause compilation failure.

        This test documents the current broken behavior - it should fail
        until we implement proper environment boundary splitting.
        """
        highlights = [
            {
                "start_word": 848,
                "end_word": 906,
                "tag": "order",
                "author": "Test User",
                "text": "test",
                "comments": [],
                "created_at": "2026-01-27T10:00:00+00:00",
            }
        ]

        latex_body = convert_html_with_annotations(
            html=parsed_lawlis.html,
            highlights=highlights,
            tag_colours=TAG_COLOURS,
        )

        preamble = build_annotation_preamble(TAG_COLOURS)
        document = f"""\\documentclass[a4paper,12pt]{{article}}
{preamble}

\\begin{{document}}

{latex_body}

\\end{{document}}
"""

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        tex_path = _OUTPUT_DIR / "cross_env_compile_test.tex"
        tex_path.write_text(document)

        # Expect compilation to fail with "Lonely \item" or similar
        with pytest.raises(LaTeXCompilationError) as exc_info:
            compile_latex(tex_path, _OUTPUT_DIR)

        # Verify we can inspect the error
        assert exc_info.value.tex_path == tex_path
        assert exc_info.value.log_path.exists()

        print(f"\nExpected failure - Log: {exc_info.value.log_path}")
```

## Files to Create/Modify

1. **Create:** `tests/unit/test_latex_cross_env.py` - New test file

## Verification

1. Run the test:
   ```bash
   uv run pytest tests/unit/test_latex_cross_env.py -v
   ```

2. Inspect artifacts:
   - `output/unit/test_latex_cross_env/cross_env_highlight.tex` - LaTeX source
   - `output/unit/test_latex_cross_env/cross_env_compile_test.log` - Error log

3. Examine the `.tex` file around `\item` to see:
   - How `\highLight` wraps text crossing environment boundaries
   - The malformed structure causing "Lonely \item"

## Expected Output

After running, user can:
1. Open `cross_env_highlight.tex` in a text editor
2. Search for `\highLight` near `\item` commands
3. See the exact malformed structure
4. Approve the visual styling approach before implementing the fix

The second test (`test_compilation_fails_with_lonely_item`) explicitly expects failure, documenting the bug until fixed.
