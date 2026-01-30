# Nested Highlight Marker Parser Implementation Plan

**Goal:** Replace regex-based marker matching with a Lark lexer and linear state machine for handling interleaved highlights.

**Architecture:** Three-stage pipeline: Lark lexer tokenizes markers → Region builder tracks active highlights → LaTeX generator emits nested commands.

**Tech Stack:** Python 3.14, lark (lexer), pylatexenc (existing), lua-ul (existing LaTeX package)

**Scope:** 5 phases from original design (all phases)

**Codebase verified:** 2026-01-28

---

## Phase 1: Lark Lexer

<!-- START_TASK_1 -->
### Task 1: Add lark dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add lark to dependencies**

Add to `[project.dependencies]` section (around line 25):

```toml
"lark>=1.1.0",
```

**Step 2: Verify installation**

Run: `uv sync`
Expected: Installs without errors

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add lark parsing library for marker tokenization"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create MarkerToken dataclass

**Files:**
- Modify: `src/promptgrimoire/export/latex.py` (add near top, after imports)
- Create: `tests/unit/test_marker_lexer.py`

**Step 1: Write the test**

Create test file `tests/unit/test_marker_lexer.py`:

```python
"""Unit tests for marker lexer.

Tests tokenization stage ONLY - no region building or LaTeX generation.
"""

import pytest

from promptgrimoire.export.latex import MarkerToken, MarkerTokenType


class TestMarkerTokenDataclass:
    """Tests for the MarkerToken dataclass itself."""

    def test_text_token_has_none_index(self) -> None:
        """TEXT tokens have index=None."""
        token = MarkerToken(
            type=MarkerTokenType.TEXT,
            value="hello world",
            index=None,
            start_pos=0,
            end_pos=11,
        )
        assert token.type == MarkerTokenType.TEXT
        assert token.index is None

    def test_hlstart_token_has_int_index(self) -> None:
        """HLSTART tokens have integer index."""
        token = MarkerToken(
            type=MarkerTokenType.HLSTART,
            value="HLSTART{42}ENDHL",
            index=42,
            start_pos=0,
            end_pos=16,
        )
        assert token.type == MarkerTokenType.HLSTART
        assert token.index == 42

    def test_token_is_frozen(self) -> None:
        """MarkerToken is immutable (frozen dataclass)."""
        token = MarkerToken(
            type=MarkerTokenType.TEXT,
            value="x",
            index=None,
            start_pos=0,
            end_pos=1,
        )
        # Should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError
            token.value = "changed"  # type: ignore[misc]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_marker_lexer.py -v`
Expected: ImportError (MarkerToken doesn't exist yet)

**Step 3: Write the implementation**

Add to `src/promptgrimoire/export/latex.py` after the existing imports (around line 20):

```python
from dataclasses import dataclass
from enum import Enum


class MarkerTokenType(Enum):
    """Token types for marker lexer."""

    TEXT = "TEXT"
    HLSTART = "HLSTART"
    HLEND = "HLEND"
    ANNMARKER = "ANNMARKER"


@dataclass(frozen=True, slots=True)
class MarkerToken:
    """A token from the marker lexer.

    Attributes:
        type: The token type (TEXT, HLSTART, HLEND, ANNMARKER)
        value: The raw string value matched
        index: For marker tokens, the highlight index (e.g., 1 from HLSTART{1}ENDHL).
               None for TEXT tokens.
        start_pos: Start byte position in input
        end_pos: End byte position in input
    """

    type: MarkerTokenType
    value: str
    index: int | None
    start_pos: int
    end_pos: int
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_marker_lexer.py::TestMarkerTokenDataclass -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/latex.py tests/unit/test_marker_lexer.py
git commit -m "feat(latex): add MarkerToken dataclass for lexer output"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create Lark grammar and tokenize_markers function

**Files:**
- Modify: `src/promptgrimoire/export/latex.py`
- Modify: `tests/unit/test_marker_lexer.py`

**Step 1: Write the tests**

Add to `tests/unit/test_marker_lexer.py`:

```python
from promptgrimoire.export.latex import (
    MarkerToken,
    MarkerTokenType,
    tokenize_markers,
)


class TestTokenizeMarkers:
    """Tests for tokenize_markers function."""

    def test_empty_input(self) -> None:
        """Empty string returns empty list."""
        assert tokenize_markers("") == []

    def test_text_only_no_markers(self) -> None:
        """Plain text without markers returns single TEXT token."""
        tokens = tokenize_markers("Hello world")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.TEXT
        assert tokens[0].value == "Hello world"
        assert tokens[0].index is None

    def test_single_hlstart(self) -> None:
        """Single HLSTART marker is tokenized correctly."""
        tokens = tokenize_markers("HLSTART{1}ENDHL")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.HLSTART
        assert tokens[0].value == "HLSTART{1}ENDHL"
        assert tokens[0].index == 1

    def test_single_hlend(self) -> None:
        """Single HLEND marker is tokenized correctly."""
        tokens = tokenize_markers("HLEND{42}ENDHL")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.HLEND
        assert tokens[0].value == "HLEND{42}ENDHL"
        assert tokens[0].index == 42

    def test_single_annmarker(self) -> None:
        """Single ANNMARKER is tokenized correctly."""
        tokens = tokenize_markers("ANNMARKER{7}ENDMARKER")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.ANNMARKER
        assert tokens[0].value == "ANNMARKER{7}ENDMARKER"
        assert tokens[0].index == 7

    def test_complete_highlight_pair(self) -> None:
        """HLSTART...text...HLEND produces correct token sequence."""
        tokens = tokenize_markers("HLSTART{1}ENDHL hello HLEND{1}ENDHL")
        assert len(tokens) == 3
        assert tokens[0].type == MarkerTokenType.HLSTART
        assert tokens[0].index == 1
        assert tokens[1].type == MarkerTokenType.TEXT
        assert tokens[1].value == " hello "
        assert tokens[2].type == MarkerTokenType.HLEND
        assert tokens[2].index == 1

    def test_preserves_spaces_in_text(self) -> None:
        """Whitespace in TEXT tokens is preserved exactly."""
        tokens = tokenize_markers("  spaces  HLSTART{1}ENDHL  more  ")
        text_tokens = [t for t in tokens if t.type == MarkerTokenType.TEXT]
        assert text_tokens[0].value == "  spaces  "
        assert text_tokens[1].value == "  more  "

    def test_preserves_newlines_in_text(self) -> None:
        """Newlines in TEXT tokens are preserved."""
        tokens = tokenize_markers("line1\nline2\nHLSTART{1}ENDHL")
        assert tokens[0].type == MarkerTokenType.TEXT
        assert tokens[0].value == "line1\nline2\n"

    def test_adjacent_markers_no_text_between(self) -> None:
        """Adjacent markers with no text between produce no TEXT token."""
        tokens = tokenize_markers("HLSTART{1}ENDHLHLSTART{2}ENDHL")
        assert len(tokens) == 2
        assert tokens[0].type == MarkerTokenType.HLSTART
        assert tokens[0].index == 1
        assert tokens[1].type == MarkerTokenType.HLSTART
        assert tokens[1].index == 2

    def test_multiple_highlights_sequential(self) -> None:
        """Multiple non-overlapping highlights tokenize correctly."""
        tokens = tokenize_markers(
            "a HLSTART{1}ENDHL b HLEND{1}ENDHL c HLSTART{2}ENDHL d HLEND{2}ENDHL e"
        )
        types = [t.type for t in tokens]
        assert types == [
            MarkerTokenType.TEXT,      # "a "
            MarkerTokenType.HLSTART,   # {1}
            MarkerTokenType.TEXT,      # " b "
            MarkerTokenType.HLEND,     # {1}
            MarkerTokenType.TEXT,      # " c "
            MarkerTokenType.HLSTART,   # {2}
            MarkerTokenType.TEXT,      # " d "
            MarkerTokenType.HLEND,     # {2}
            MarkerTokenType.TEXT,      # " e"
        ]

    def test_nested_markers(self) -> None:
        """Properly nested markers tokenize correctly."""
        # Example A from design: nested
        tokens = tokenize_markers(
            "The HLSTART{1}ENDHLquick HLSTART{2}ENDHLfoxHLEND{2}ENDHL brownHLEND{1}ENDHL dog"
        )
        types = [(t.type, t.index) for t in tokens]
        assert types == [
            (MarkerTokenType.TEXT, None),       # "The "
            (MarkerTokenType.HLSTART, 1),
            (MarkerTokenType.TEXT, None),       # "quick "
            (MarkerTokenType.HLSTART, 2),
            (MarkerTokenType.TEXT, None),       # "fox"
            (MarkerTokenType.HLEND, 2),
            (MarkerTokenType.TEXT, None),       # " brown"
            (MarkerTokenType.HLEND, 1),
            (MarkerTokenType.TEXT, None),       # " dog"
        ]

    def test_interleaved_markers(self) -> None:
        """Interleaved (not properly nested) markers tokenize correctly."""
        # Example B from design: interleaved
        tokens = tokenize_markers(
            "The HLSTART{1}ENDHLquick HLSTART{2}ENDHLfoxHLEND{1}ENDHL overHLEND{2}ENDHL dog"
        )
        types = [(t.type, t.index) for t in tokens]
        assert types == [
            (MarkerTokenType.TEXT, None),       # "The "
            (MarkerTokenType.HLSTART, 1),
            (MarkerTokenType.TEXT, None),       # "quick "
            (MarkerTokenType.HLSTART, 2),
            (MarkerTokenType.TEXT, None),       # "fox"
            (MarkerTokenType.HLEND, 1),
            (MarkerTokenType.TEXT, None),       # " over"
            (MarkerTokenType.HLEND, 2),
            (MarkerTokenType.TEXT, None),       # " dog"
        ]

    def test_extracts_correct_indices(self) -> None:
        """Indices are correctly extracted as integers."""
        tokens = tokenize_markers("HLSTART{0}ENDHL HLSTART{999}ENDHL HLEND{123}ENDHL")
        indices = [t.index for t in tokens if t.type != MarkerTokenType.TEXT]
        assert indices == [0, 999, 123]

    def test_latex_commands_in_text_preserved(self) -> None:
        """LaTeX commands in TEXT are preserved verbatim."""
        tokens = tokenize_markers(r"\textbf{bold} HLSTART{1}ENDHL \emph{italic}")
        text_values = [t.value for t in tokens if t.type == MarkerTokenType.TEXT]
        assert text_values[0] == r"\textbf{bold} "
        assert text_values[1] == r" \emph{italic}"

    def test_start_positions_are_correct(self) -> None:
        """Token start_pos values are accurate byte offsets."""
        tokens = tokenize_markers("abc HLSTART{1}ENDHL xyz")
        assert tokens[0].start_pos == 0   # "abc "
        assert tokens[1].start_pos == 4   # HLSTART{1}ENDHL
        assert tokens[2].start_pos == 20  # " xyz"

    def test_end_positions_are_correct(self) -> None:
        """Token end_pos values are accurate byte offsets."""
        tokens = tokenize_markers("abc HLSTART{1}ENDHL xyz")
        assert tokens[0].end_pos == 4    # "abc " ends at 4
        assert tokens[1].end_pos == 20   # HLSTART{1}ENDHL ends at 20
        assert tokens[2].end_pos == 24   # " xyz" ends at 24
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_marker_lexer.py::TestTokenizeMarkers -v`
Expected: ImportError (tokenize_markers doesn't exist yet)

**Step 3: Write the implementation**

Add to `src/promptgrimoire/export/latex.py` after the MarkerToken class:

```python
from lark import Lark

# Lark grammar for marker tokenization
# Literals have higher priority than regex, so markers match first
# TEXT catches everything else with negative lookahead
_MARKER_GRAMMAR = r'''
    HLSTART: "HLSTART{" /[0-9]+/ "}ENDHL"
    HLEND: "HLEND{" /[0-9]+/ "}ENDHL"
    ANNMARKER: "ANNMARKER{" /[0-9]+/ "}ENDMARKER"

    // TEXT matches any character that isn't the start of a marker
    // Uses negative lookahead to stop before marker sequences
    TEXT: /(?:(?!HLSTART\{|HLEND\{|ANNMARKER\{).)+/s
'''

# Compile once at module load
_marker_lexer = Lark(_MARKER_GRAMMAR, parser=None, lexer='basic')

# Regex to extract index from marker value
_INDEX_EXTRACT_PATTERN = re.compile(r'\{(\d+)\}')


def tokenize_markers(latex: str) -> list[MarkerToken]:
    """Tokenize LaTeX text containing highlight markers.

    Converts a string containing HLSTART{n}ENDHL, HLEND{n}ENDHL, and
    ANNMARKER{n}ENDMARKER markers into a list of MarkerToken objects.
    All text between markers becomes TEXT tokens.

    Args:
        latex: LaTeX string potentially containing markers

    Returns:
        List of MarkerToken objects preserving order and positions

    Example:
        >>> tokens = tokenize_markers("Hello HLSTART{1}ENDHL world")
        >>> [(t.type.value, t.value) for t in tokens]
        [('TEXT', 'Hello '), ('HLSTART', 'HLSTART{1}ENDHL'), ('TEXT', ' world')]
    """
    if not latex:
        return []

    tokens: list[MarkerToken] = []

    for lark_token in _marker_lexer.lex(latex):
        token_type = MarkerTokenType[lark_token.type]

        # Extract index for marker tokens
        index: int | None = None
        if token_type != MarkerTokenType.TEXT:
            match = _INDEX_EXTRACT_PATTERN.search(lark_token.value)
            if match:
                index = int(match.group(1))

        tokens.append(
            MarkerToken(
                type=token_type,
                value=lark_token.value,
                index=index,
                start_pos=lark_token.start_pos,
                end_pos=lark_token.end_pos,
            )
        )

    return tokens
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_marker_lexer.py::TestTokenizeMarkers -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/latex.py tests/unit/test_marker_lexer.py
git commit -m "feat(latex): add tokenize_markers() with Lark lexer"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add edge case tests (falsifiability)

**Files:**
- Modify: `tests/unit/test_marker_lexer.py`

**Step 1: Write additional edge case tests**

Add to `tests/unit/test_marker_lexer.py`:

```python
class TestTokenizeMarkersEdgeCases:
    """Edge case tests for tokenize_markers - falsifiability scenarios."""

    def test_marker_at_very_start(self) -> None:
        """Marker at position 0 (no preceding text)."""
        tokens = tokenize_markers("HLSTART{1}ENDHL after")
        assert tokens[0].type == MarkerTokenType.HLSTART
        assert tokens[0].start_pos == 0

    def test_marker_at_very_end(self) -> None:
        """Marker at end of string (no following text)."""
        tokens = tokenize_markers("before HLEND{1}ENDHL")
        assert tokens[-1].type == MarkerTokenType.HLEND

    def test_only_markers_no_text(self) -> None:
        """String with only markers, no text at all."""
        tokens = tokenize_markers("HLSTART{1}ENDHLHLEND{1}ENDHL")
        assert len(tokens) == 2
        assert all(t.type != MarkerTokenType.TEXT for t in tokens)

    def test_marker_like_text_not_marker(self) -> None:
        """Text containing 'HLSTART' without proper format is TEXT.

        This tests that partial matches don't confuse the lexer.
        'HLSTART' alone (without {n}ENDHL) should be TEXT.
        """
        tokens = tokenize_markers("The word HLSTART appears here")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.TEXT
        assert "HLSTART" in tokens[0].value

    def test_partial_marker_is_text(self) -> None:
        """Incomplete marker syntax is treated as TEXT."""
        tokens = tokenize_markers("HLSTART{123 is incomplete")
        assert len(tokens) == 1
        assert tokens[0].type == MarkerTokenType.TEXT

    def test_large_index_number(self) -> None:
        """Large index numbers are handled correctly."""
        tokens = tokenize_markers("HLSTART{999999}ENDHL")
        assert tokens[0].index == 999999

    def test_index_zero(self) -> None:
        """Index 0 is valid."""
        tokens = tokenize_markers("HLSTART{0}ENDHL")
        assert tokens[0].index == 0

    def test_unicode_in_text(self) -> None:
        """Unicode characters in TEXT are preserved."""
        tokens = tokenize_markers("Héllo wörld HLSTART{1}ENDHL émoji: ")
        text_values = [t.value for t in tokens if t.type == MarkerTokenType.TEXT]
        assert text_values[0] == "Héllo wörld "

    def test_backslash_sequences(self) -> None:
        """LaTeX backslash sequences don't confuse the lexer."""
        tokens = tokenize_markers(r"\begin{document} HLSTART{1}ENDHL \end{document}")
        assert len(tokens) == 3
        assert tokens[1].type == MarkerTokenType.HLSTART

    def test_curly_braces_in_text(self) -> None:
        """Curly braces in text (not part of markers) are TEXT."""
        tokens = tokenize_markers("some {text} with HLSTART{1}ENDHL braces {here}")
        text_tokens = [t for t in tokens if t.type == MarkerTokenType.TEXT]
        assert "{text}" in text_tokens[0].value
        assert "{here}" in text_tokens[1].value

    def test_newlines_between_markers(self) -> None:
        """Newlines between markers are preserved in TEXT."""
        tokens = tokenize_markers("HLSTART{1}ENDHL\n\n\nHLEND{1}ENDHL")
        assert len(tokens) == 3
        assert tokens[1].type == MarkerTokenType.TEXT
        assert tokens[1].value == "\n\n\n"

    def test_annmarker_with_other_markers(self) -> None:
        """ANNMARKER can appear alongside HLSTART/HLEND."""
        tokens = tokenize_markers(
            "HLSTART{1}ENDHL text ANNMARKER{1}ENDMARKER more HLEND{1}ENDHL"
        )
        types = [t.type for t in tokens]
        assert MarkerTokenType.ANNMARKER in types

    def test_positions_sum_to_input_length(self) -> None:
        """All token positions together cover entire input."""
        input_text = "abc HLSTART{1}ENDHL def HLEND{1}ENDHL ghi"
        tokens = tokenize_markers(input_text)

        # First token starts at 0
        assert tokens[0].start_pos == 0
        # Last token ends at input length
        assert tokens[-1].end_pos == len(input_text)
        # Each token starts where previous ended
        for i in range(1, len(tokens)):
            assert tokens[i].start_pos == tokens[i - 1].end_pos
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/test_marker_lexer.py::TestTokenizeMarkersEdgeCases -v`
Expected: All pass (if implementation is correct) or some fail (revealing bugs)

**Step 3: Fix any failures, then commit**

```bash
git add tests/unit/test_marker_lexer.py
git commit -m "test(latex): add edge case tests for marker tokenization"
```
<!-- END_TASK_4 -->

---

## Phase 1 UAT

After all tasks complete:

1. **Run all lexer tests:**
   ```bash
   uv run pytest tests/unit/test_marker_lexer.py -v
   ```
   Expected: All tests pass

2. **Manual verification with worked examples:**
   ```python
   from promptgrimoire.export.latex import tokenize_markers, MarkerTokenType

   # Example A: Simple nesting
   tokens = tokenize_markers(
       "The HLSTART{1}ENDHLquick HLSTART{2}ENDHLfoxHLEND{2}ENDHL brownHLEND{1}ENDHL dog"
   )
   for t in tokens:
       print(f"{t.type.value}: {t.value!r} index={t.index}")
   ```

   Expected output:
   ```
   TEXT: 'The ' index=None
   HLSTART: 'HLSTART{1}ENDHL' index=1
   TEXT: 'quick ' index=None
   HLSTART: 'HLSTART{2}ENDHL' index=2
   TEXT: 'fox' index=None
   HLEND: 'HLEND{2}ENDHL' index=2
   TEXT: ' brown' index=None
   HLEND: 'HLEND{1}ENDHL' index=1
   TEXT: ' dog' index=None
   ```
