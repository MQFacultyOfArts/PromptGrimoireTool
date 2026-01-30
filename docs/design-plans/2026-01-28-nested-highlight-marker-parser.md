# Nested Highlight Marker Parser Design

## Summary

Replace the regex-based marker matching in `_replace_markers_with_annots()` with a lark-based lexer and linear state machine. This handles interleaved (not just nested) highlight markers, producing correctly nested `\highLight{\underLine{...}}` commands with visual distinction for overlap count.

## Definition of Done

A lark-based parser module that correctly handles nested/interleaved highlight markers, producing properly nested `\highLight{...}` commands with stacked `\underLine{...}` commands and associated `\annot{...}` commands.

**Success criteria:**
1. Lexer correctly tokenizes `HLSTART{n}/HLEND{n}/ANNMARKER{n}` markers
2. Region builder tracks active highlights through interleaved marker sequences
3. LaTeX generator produces nested commands with correct underline parameters
4. Parser associates `ANNMARKER{n}` with highlights by index (position-agnostic)
5. Output integrates with existing `_wrap_content_with_highlight` for environment boundary splitting
6. All existing tests pass + new tests for interleaved scenarios
7. Issue #85 regression test updated to assert markers ARE processed (not literal text)

**Out of scope:**
- Changing marker insertion (`_insert_markers_into_html`) - that stays the same
- Multiple export formats - PDF/LaTeX only for now
- Future "split annotation" markers - designed to accommodate but not implemented

## Glossary

| Term | Definition |
|------|------------|
| **Interleaved markers** | Highlights that overlap without proper XML-style nesting, e.g. `HLSTART{1}...HLSTART{2}...HLEND{1}...HLEND{2}` |
| **Region** | A contiguous span of text with a constant set of active highlights |
| **Active highlights** | The set of highlight indices currently "open" (started but not yet ended) at a given position |
| **Environment boundary** | A LaTeX structure (paragraph, itemize, etc.) that cannot be spanned by unclosed commands |
| **Stacked underlines** | Multiple `\underLine` commands nested inside each other with same `bottom` but different `height` values |

## Problem Statement

Issue #85: Nested `HLSTART{n}/HLEND{n}` markers appear as literal text in PDF output instead of being converted to `\highLight` commands.

**Root cause:** The current implementation in `_replace_markers_with_annots()` uses a regex with backreference to match paired markers:
```python
re.sub(r'HLSTART\{(\d+)\}ENDHL(.*?)HLEND\{\1\}ENDHL', ...)
```

This fails when markers interleave because regex cannot handle the case where `HLSTART{1}...HLSTART{2}...HLEND{1}...HLEND{2}` - the backreference `\1` expects proper nesting.

**Key insight:** Highlights can INTERLEAVE, not just nest. This is not a recursive grammar problem - it's a linear state tracking problem.

## Architecture

### Current Workflow (What Changes)

```
HTML + Highlights
       ↓
[_insert_markers_into_html]  ← UNCHANGED
       ↓
Marked HTML
       ↓
[Pandoc]  ← UNCHANGED
       ↓
LaTeX with text markers
       ↓
[_replace_markers_with_annots]  ← THIS CHANGES
       ↓
LaTeX with commands
       ↓
[compile_latex]  ← UNCHANGED
```

### New Implementation of `_replace_markers_with_annots`

```
LaTeX with text markers
       ↓
[pylatexenc: _extract_env_boundaries]  ← find ALL boundaries (unchanged logic)
       ↓
[Lark Lexer]  ← tokenize: TEXT, HLSTART(n), HLEND(n), ANNMARKER(n)
       ↓
Token stream
       ↓
[Region Builder]  ← linear scan, track active_highlights: set[int]
       ↓
List of (text, active_highlights, annmarkers) regions
       ↓
[LaTeX Generator]  ← emit nested \highLight{\underLine{...}} per region
                     splits at env boundaries using existing logic
       ↓
LaTeX with commands
```

### Component Responsibilities

**Lark Lexer:**
- Tokenize marker stream into: `TEXT`, `HLSTART(index)`, `HLEND(index)`, `ANNMARKER(index)`
- Preserve ALL text including spaces (no whitespace loss)
- Robust to malformed input (existing markers survive Pandoc)

**Region Builder:**
- Simple linear state machine
- Track `active_highlights: set[int]` as we scan
- On `HLSTART{n}`: add n to active set, emit region boundary
- On `HLEND{n}`: remove n from active set, emit region boundary
- On `ANNMARKER{n}`: associate with current position (by index, not position)
- Output: list of `Region(text, frozenset[int], list[int])` tuples

**LaTeX Generator:**
- For each region with non-empty active set:
  - Check if text contains environment boundaries
  - If yes: split at boundaries, wrap each segment
  - Generate nested `\highLight[colour]{...}` commands (one per active highlight)
  - Generate nested `\underLine[...]` commands inside (parameters based on overlap count)
- Emit `\annot{...}` commands at appropriate positions

## Visual Specification (Underlines)

Underlines indicate which highlights are active at each position. Colours match the highlight's tag colour.

| Overlap Count | Underline Spec | LaTeX |
|---------------|----------------|-------|
| 1 highlight | 1pt line, bottom=-3pt | `\underLine[color=X-dark, height=1pt, bottom=-3pt]{...}` |
| 2 highlights | 2pt outer + 1pt inner, bottom=-3pt | `\underLine[color=X-dark, height=2pt, bottom=-3pt]{\underLine[color=Y-dark, height=1pt, bottom=-3pt]{...}}` |
| 3+ highlights | 4pt "many" line, bottom=-5pt | `\underLine[color=many-dark, height=4pt, bottom=-5pt]{...}` |

**Colour mapping:**
- Each highlight has a tag colour (e.g., "red-light" for background)
- Underline uses corresponding dark variant (e.g., "red-dark")
- "many-dark" is `#333333` (dark grey) for 3+ overlaps

**Example (2 overlapping):**
```latex
\highLight[red-light]{\highLight[green-light]{%
  \underLine[color=red-dark, height=2pt, bottom=-3pt]{%
    \underLine[color=green-dark, height=1pt, bottom=-3pt]{fox jumps}}}}
```

## Worked Examples

### Example A: Simple Nesting

```
Input:  "The HLSTART{1}ENDHL quick HLSTART{2}ENDHL fox HLEND{2}ENDHL brown HLEND{1}ENDHL dog"

Tokens: [TEXT("The "), HLSTART(1), TEXT("quick "), HLSTART(2), TEXT("fox "),
         HLEND(2), TEXT("brown "), HLEND(1), TEXT("dog")]

Regions:
  Region("The ", active={}, annots=[])
  Region("quick ", active={1}, annots=[])
  Region("fox ", active={1,2}, annots=[])      ← 2 active
  Region("brown ", active={1}, annots=[])
  Region("dog", active={}, annots=[])
```

### Example B: Interleaved (the key case)

```
Input:  "The HLSTART{1}ENDHL quick HLSTART{2}ENDHL fox HLEND{1}ENDHL over HLEND{2}ENDHL dog"

Tokens: [TEXT("The "), HLSTART(1), TEXT("quick "), HLSTART(2), TEXT("fox "),
         HLEND(1), TEXT("over "), HLEND(2), TEXT("dog")]

Regions:
  Region("The ", active={}, annots=[])
  Region("quick ", active={1}, annots=[])
  Region("fox ", active={1,2}, annots=[])      ← 2 active
  Region("over ", active={2}, annots=[])       ← only 2 now (1 ended mid-overlap)
  Region("dog", active={}, annots=[])
```

### Example C: Three Overlapping

```
Input:  "HLSTART{1}ENDHL a HLSTART{2}ENDHL b HLSTART{3}ENDHL c HLEND{1}ENDHL d HLEND{2}ENDHL e HLEND{3}ENDHL"

Regions:
  Region("a ", active={1}, annots=[])
  Region("b ", active={1,2}, annots=[])
  Region("c ", active={1,2,3}, annots=[])     ← 3 active → "many" underline
  Region("d ", active={2,3}, annots=[])
  Region("e ", active={3}, annots=[])
```

## Existing Patterns Followed

| Pattern | Location | How We Follow It |
|---------|----------|------------------|
| pylatexenc for env boundaries | `_extract_env_boundaries()` latex.py:323-392 | Reuse unchanged |
| Env boundary splitting | `_wrap_content_with_highlight()` latex.py:395-448 | Call from generator |
| Marker format | `_insert_markers_into_html()` | Keep same marker syntax |
| Colour definitions | `generate_tag_colour_definitions()` | Add "many-dark" colour |
| Annotation formatting | `_format_annot()` | Reuse unchanged |

## Implementation Phases

### Phase 1: Lark Lexer

**Deliverables:**
- Lark grammar for marker tokenization
- `tokenize_markers(latex: str) -> list[Token]` function
- Unit tests for tokenization (including edge cases)

**Files:** `src/promptgrimoire/export/latex.py` (new function)

**UAT:** Run lexer on sample LaTeX, verify tokens are correct.

### Phase 2: Region Builder

**Deliverables:**
- `Region` dataclass: `(text: str, active: frozenset[int], annots: list[int])`
- `build_regions(tokens: list[Token]) -> list[Region]` function
- Unit tests for all worked examples (A, B, C above)

**Files:** `src/promptgrimoire/export/latex.py` (new function)

**UAT:** Run region builder on Examples A, B, C, verify output matches.

### Phase 3: LaTeX Generator

**Deliverables:**
- `generate_highlighted_latex(regions, highlights, env_boundaries) -> str` function
- Correct underline nesting based on overlap count
- Env boundary splitting (using existing `_wrap_content_with_highlight` logic)
- Unit tests for underline generation

**Files:** `src/promptgrimoire/export/latex.py` (new function)

**UAT:** Generate LaTeX for examples, verify output structure.

### Phase 4: Integration

**Deliverables:**
- Replace regex matching in `_replace_markers_with_annots()` with new pipeline
- Add "many-dark" colour definition
- Ensure all existing tests pass

**Files:** `src/promptgrimoire/export/latex.py` (modify existing function)

**UAT:** Full PDF export with overlapping highlights, visual inspection.

### Phase 5: Test Cleanup

**Deliverables:**
- Remove/update tests based on incorrect regex assumptions
- Add comprehensive fixture-based tests for new components
- Issue #85 regression test: assert no literal marker text in output

**Files:** `tests/unit/test_overlapping_highlights.py`, `tests/unit/test_latex_export.py`

**UAT:** All tests pass, test coverage adequate.

## Testing Strategy

### Unit Tests (per component)

```python
class TestMarkerLexer:
    def test_simple_markers(self): ...
    def test_preserves_spaces(self): ...
    def test_adjacent_markers(self): ...
    def test_malformed_input_survives(self): ...

class TestRegionBuilder:
    def test_single_highlight(self): ...
    def test_non_overlapping(self): ...
    def test_nested_example_a(self): ...
    def test_interleaved_example_b(self): ...
    def test_three_overlapping_example_c(self): ...
    def test_annmarker_association_by_index(self): ...

class TestLaTeXGenerator:
    def test_single_highlight_1pt_underline(self): ...
    def test_two_overlapping_stacked_underlines(self): ...
    def test_three_plus_many_underline(self): ...
    def test_env_boundary_splitting(self): ...
    def test_underline_colours_match_highlights(self): ...
```

### Integration Tests

```python
class TestOverlappingCompilation:
    def test_nested_highlights_compile(self): ...
    def test_interleaved_highlights_compile(self): ...
    def test_three_overlapping_compile(self): ...
```

### Regression Test

```python
def test_issue_85_nested_markers_not_literal():
    """Nested markers produce \\highLight commands, not literal HLSTART text."""
    # Create document with nested highlights
    # Export to LaTeX
    assert "HLSTART" not in latex_output
    assert "HLEND" not in latex_output
    assert "\\highLight" in latex_output
```

## Test Inventory and Reorganization

### Current Test Files (Before Refactor)

| File | Current Contents | Status |
|------|------------------|--------|
| `tests/unit/test_latex_export.py` | Mixed: string functions, marker insertion, marker replacement, compilation | Muddled |
| `tests/unit/test_latex_cross_env.py` | Integration test in unit folder | Misplaced |
| `tests/unit/test_overlapping_highlights.py` | **UNCOMMITTED** - marker insertion + compilation + documents Issue #85 | Partial |
| `tests/integration/test_pdf_export.py` | Pipeline integration (HTML→LaTeX→PDF) | OK |
| `tests/e2e/test_pdf_export.py` | Full UI workflow with multi-user collaboration | OK |

### Current Test Classes - Disposition

#### `tests/unit/test_latex_export.py`

| Class | Tests | Disposition |
|-------|-------|-------------|
| `TestFormatTimestamp` | Timestamp formatting | ✅ KEEP - pure function |
| `TestGenerateTagColourDefinitions` | Colour definitions | ✅ KEEP - pure function |
| `TestFormatAnnot` | Annotation formatting | ✅ KEEP - pure function |
| `TestInsertMarkersIntoHtml` | Marker insertion | ✅ KEEP - unchanged in new design |
| `TestReplaceMarkersWithAnnots` | Marker replacement | ⚠️ UPDATE - tests function we're rewriting |
| `TestCompilationValidation` | Compilation | ✅ KEEP - tests output compiles |

#### `tests/unit/test_latex_cross_env.py`

| Class | Tests | Disposition |
|-------|-------|-------------|
| `TestCrossEnvironmentHighlights` | Cross-env boundary splitting | 🔄 MOVE to integration - uses full pipeline |

#### `tests/unit/test_overlapping_highlights.py` (UNCOMMITTED)

| Class | Tests | Disposition |
|-------|-------|-------------|
| `TestOverlappingMarkerInsertion` | Marker insertion with overlaps | ✅ KEEP - tests unchanged function |
| `TestOverlappingMarkerReplacement` | Documents Issue #85 bug | ❌ DELETE - tests broken regex |
| `TestOverlappingCompilation` | Asserts markers ARE in output | ⚠️ FLIP - should assert markers NOT in output |

### Proposed Test Structure (After Refactor)

**Principle:** Unit tests test ONE pipeline stage. Integration tests combine stages.

```
tests/
├── unit/
│   ├── export/
│   │   ├── test_latex_string_functions.py   # Pure functions (escape, timestamp, colours, format_annot)
│   │   ├── test_marker_insertion.py         # _insert_markers_into_html (unchanged)
│   │   ├── test_marker_lexer.py             # NEW: Lark lexer tokenization
│   │   ├── test_region_builder.py           # NEW: Region building from tokens
│   │   └── test_latex_generator.py          # NEW: Highlight/underline generation
│   └── ...
├── integration/
│   ├── test_pdf_pipeline.py                 # Full pipeline: HTML → markers → pandoc → process → compile
│   └── test_cross_env_highlights.py         # Moved from unit/ (uses full pipeline)
└── e2e/
    └── test_pdf_export.py                   # UI workflow (unchanged)
```

### Test File Migration Plan

| From | To | What Moves |
|------|----|------------|
| `test_latex_export.py` | `test_latex_string_functions.py` | `TestFormatTimestamp`, `TestGenerateTagColourDefinitions`, `TestFormatAnnot`, `TestCompilationValidation` |
| `test_latex_export.py` | `test_marker_insertion.py` | `TestInsertMarkersIntoHtml` |
| `test_latex_export.py` | DELETE | `TestReplaceMarkersWithAnnots` (replaced by new component tests) |
| `test_overlapping_highlights.py` | `test_marker_insertion.py` | `TestOverlappingMarkerInsertion` |
| `test_overlapping_highlights.py` | DELETE | `TestOverlappingMarkerReplacement` |
| `test_overlapping_highlights.py` | `test_pdf_pipeline.py` | `TestOverlappingCompilation` (with flipped assertion) |
| `test_latex_cross_env.py` | `test_cross_env_highlights.py` (integration/) | `TestCrossEnvironmentHighlights` |
| NEW | `test_marker_lexer.py` | `TestMarkerLexer` |
| NEW | `test_region_builder.py` | `TestRegionBuilder` |
| NEW | `test_latex_generator.py` | `TestLaTeXGenerator` |

### New Unit Test Specifications

#### `test_marker_lexer.py`

```python
"""Unit tests for Lark-based marker lexer.

Tests the tokenization stage ONLY - no region building or LaTeX generation.
"""

class TestMarkerLexer:
    def test_empty_input(self): ...
    def test_text_only_no_markers(self): ...
    def test_single_hlstart(self): ...
    def test_single_hlend(self): ...
    def test_single_annmarker(self): ...
    def test_complete_highlight_pair(self): ...
    def test_preserves_spaces_in_text(self): ...
    def test_preserves_newlines_in_text(self): ...
    def test_adjacent_markers_no_text_between(self): ...
    def test_multiple_highlights_sequential(self): ...
    def test_nested_markers(self): ...
    def test_interleaved_markers(self): ...
    def test_extracts_correct_indices(self): ...
    def test_latex_commands_in_text_preserved(self): ...
```

#### `test_region_builder.py`

```python
"""Unit tests for region builder.

Tests the state machine that converts tokens to regions.
Uses tokens directly - does NOT call lexer.
"""

class TestRegionBuilder:
    def test_empty_tokens(self): ...
    def test_text_only_single_region(self): ...
    def test_single_highlight_three_regions(self): ...
    def test_non_overlapping_highlights(self): ...
    def test_nested_highlights_example_a(self): ...
    def test_interleaved_highlights_example_b(self): ...
    def test_three_overlapping_example_c(self): ...
    def test_annmarker_associated_by_index(self): ...
    def test_annmarker_not_position_dependent(self): ...
    def test_active_set_is_frozenset(self): ...
    def test_spaces_included_in_regions(self): ...
```

#### `test_latex_generator.py`

```python
"""Unit tests for LaTeX generator.

Tests highlight/underline generation from regions.
Uses regions directly - does NOT call lexer or region builder.
"""

class TestLaTeXGenerator:
    def test_empty_regions(self): ...
    def test_no_active_highlights_passthrough(self): ...
    def test_single_highlight_1pt_underline(self): ...
    def test_single_highlight_correct_colours(self): ...
    def test_two_highlights_stacked_underlines(self): ...
    def test_two_highlights_outer_2pt_inner_1pt(self): ...
    def test_three_highlights_many_underline(self): ...
    def test_many_underline_4pt_bottom_minus_5(self): ...
    def test_many_underline_uses_many_dark_colour(self): ...
    def test_env_boundary_splits_highlight(self): ...
    def test_annmarker_emits_annot_command(self): ...
    def test_nested_highlights_correct_nesting_order(self): ...
```

### Integration Test Specifications

#### `test_pdf_pipeline.py`

```python
"""Integration tests for full PDF export pipeline.

Tests the complete flow: HTML → markers → pandoc → process → compile.
Requires Pandoc and TinyTeX.
"""

@requires_latexmk
class TestPdfPipeline:
    def test_simple_highlight_compiles(self): ...
    def test_multiple_non_overlapping_compiles(self): ...
    def test_nested_highlights_compile(self): ...
    def test_interleaved_highlights_compile(self): ...
    def test_three_overlapping_compile(self): ...
    def test_cross_environment_highlight_compiles(self): ...

    def test_issue_85_regression_no_literal_markers(self):
        """Regression test: markers are processed, not literal text.

        CRITICAL: This test MUST fail if Issue #85 regresses.
        """
        # Create document with nested/interleaved highlights
        # Run full pipeline
        assert "HLSTART" not in latex_output
        assert "HLEND" not in latex_output
        assert "ANNMARKER" not in latex_output
        assert r"\highLight" in latex_output
```

### Test Fixtures

Create shared fixtures in `tests/conftest.py` or `tests/fixtures/`:

```python
# Highlight definitions for testing
SAMPLE_HIGHLIGHTS = [
    {"start_word": 1, "end_word": 3, "tag": "alpha", ...},
    {"start_word": 2, "end_word": 5, "tag": "beta", ...},
]

# Tag colours
SAMPLE_TAG_COLOURS = {
    "alpha": "#1f77b4",
    "beta": "#d62728",
}

# Worked example inputs/outputs
EXAMPLE_A_INPUT = "The HLSTART{1}ENDHL quick..."
EXAMPLE_A_TOKENS = [Token("TEXT", "The "), Token("HLSTART", 1), ...]
EXAMPLE_A_REGIONS = [Region("The ", frozenset(), []), ...]

EXAMPLE_B_INPUT = ...  # Interleaved case
EXAMPLE_C_INPUT = ...  # Three overlapping
```

## Additional Considerations

### Implementation Approach

- **Very slow and steady** - one small change at a time
- **UAT checkpoint after each change** - user reviews before proceeding
- **Tear down old tests** with incorrect assumptions, rebuild cleanly with fixtures
- **Keep user in the loop** - no autonomous multi-step changes
- **Test reorganization as Phase 5** - move/refactor tests after implementation works

### Dependencies

- **lark** - new dependency for lexer (add to pyproject.toml)
- **lua-ul** - already installed, supports nested `\highLight` and `\underLine`

### Risk Mitigation

- Lark lexer is well-tested library, reduces regex fragility
- Linear state machine is simple to reason about and test
- Existing env boundary logic is preserved, not rewritten
- Comprehensive worked examples verify algorithm before implementation
- Test reorganization improves maintainability and clarity

---

*Design validated: 2026-01-28*
*Freshness: Valid until implementation complete or requirements change*
