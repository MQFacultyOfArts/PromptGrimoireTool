# Unicode Robustness Implementation Plan - Phase 3

**Goal:** Wrap detected unicode in appropriate LaTeX commands

**Architecture:** `escape_unicode_latex()` wraps CJK in `\cjktext{}` and emoji in `\emoji{}` commands. A `UNICODE_PREAMBLE` constant defines the required LaTeX setup (luatexja-fontspec, emoji package, Noto fonts).

**Tech Stack:** Python, luatexja-fontspec (LaTeX), emoji package (LaTeX)

**Scope:** Phase 3 of 7 from design plan

**Codebase verified:** 2026-01-31

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add escape_unicode_latex() function

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/unicode_latex.py`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_unicode_handling.py`

**Step 1: Write failing tests**

Add to `tests/unit/test_unicode_handling.py`:

```python
from promptgrimoire.export.unicode_latex import escape_unicode_latex


class TestEscapeUnicodeLaTeX:
    """Test unicode-aware LaTeX escaping."""

    def test_ascii_special_chars_escaped(self) -> None:
        """ASCII special characters are escaped."""
        assert escape_unicode_latex("a & b") == r"a \& b"
        assert escape_unicode_latex("100%") == r"100\%"
        assert escape_unicode_latex("$10") == r"\$10"

    def test_cjk_wrapped_in_font_command(self) -> None:
        """CJK text is wrapped in \\cjktext{} command."""
        result = escape_unicode_latex("Hello 世界")
        assert "\\cjktext{世界}" in result
        assert "Hello " in result

    def test_multiple_cjk_runs_wrapped_separately(self) -> None:
        """Multiple CJK runs are wrapped separately."""
        result = escape_unicode_latex("A 世界 B 中文 C")
        assert result.count("\\cjktext{") == 2

    def test_mixed_cjk_scripts(self) -> None:
        """Different CJK scripts (Chinese, Japanese, Korean) wrapped."""
        result = escape_unicode_latex("日本語 한글 中文")
        # All should be wrapped (language-agnostic for now)
        assert "\\cjktext{" in result

    def test_emoji_wrapped_in_emoji_command(self) -> None:
        """Emoji is wrapped in \\emoji{} command."""
        result = escape_unicode_latex("Test 🎉!")
        # Emoji library converts to name format
        assert "\\emoji{" in result

    def test_pure_ascii_unchanged(self) -> None:
        """Pure ASCII without special chars passes through."""
        assert escape_unicode_latex("Hello world") == "Hello world"

    def test_mixed_cjk_emoji_ascii(self) -> None:
        """Mixed content handles all types correctly."""
        result = escape_unicode_latex("Hello 世界 🎉!")
        assert "\\cjktext{世界}" in result
        assert "\\emoji{" in result
        assert "Hello " in result
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestEscapeUnicodeLaTeX -v`

Expected: FAIL with `ImportError: cannot import name 'escape_unicode_latex'`

**Step 3: Write implementation**

Add to `unicode_latex.py`:

```python
# ASCII special characters for LaTeX (from existing _escape_latex)
_LATEX_SPECIAL_CHARS = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]


def _escape_ascii_special(text: str) -> str:
    """Escape ASCII special characters for LaTeX."""
    for char, replacement in _LATEX_SPECIAL_CHARS:
        text = text.replace(char, replacement)
    return text


def escape_unicode_latex(text: str) -> str:
    """Escape text for LaTeX with unicode handling.

    - ASCII special characters (& % $ # _ { } ~ ^) are escaped
    - CJK text is wrapped in \\cjktext{} command
    - Emoji are wrapped in \\emoji{} command with name format

    Args:
        text: Input text potentially containing unicode.

    Returns:
        LaTeX-safe string with appropriate wrapping.
    """
    if not text:
        return text

    # First, identify emoji spans (must do before any modifications)
    emoji_spans = get_emoji_spans(text)

    # Build result by processing character by character
    result: list[str] = []
    i = 0
    cjk_buffer: list[str] = []

    def flush_cjk() -> None:
        """Flush accumulated CJK characters as wrapped command."""
        if cjk_buffer:
            escaped = _escape_ascii_special("".join(cjk_buffer))
            result.append(f"\\cjktext{{{escaped}}}")
            cjk_buffer.clear()

    while i < len(text):
        # Check if we're at an emoji span
        emoji_match = None
        for start, end, emoji_char in emoji_spans:
            if i == start:
                emoji_match = (end, emoji_char)
                break

        if emoji_match:
            flush_cjk()
            end, emoji_char = emoji_match
            # Convert emoji to name using emoji library
            emoji_name = emoji_lib.demojize(emoji_char, delimiters=("", ""))
            # Remove colons if present and convert to LaTeX emoji format
            emoji_name = emoji_name.strip(":").replace("_", "-")
            result.append(f"\\emoji{{{emoji_name}}}")
            i = end
        elif is_cjk(text[i]):
            cjk_buffer.append(text[i])
            i += 1
        else:
            flush_cjk()
            # Escape ASCII special chars
            result.append(_escape_ascii_special(text[i]))
            i += 1

    flush_cjk()
    return "".join(result)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestEscapeUnicodeLaTeX -v`

Expected: All 7 tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/unicode_latex.py tests/unit/test_unicode_handling.py
git commit -m "feat(export): add escape_unicode_latex() with CJK and emoji wrapping (#101)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add LaTeX preamble commands for cjktext and emoji

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/unicode_latex.py`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_unicode_handling.py`

**Step 1: Write failing test for preamble**

Add to `tests/unit/test_unicode_handling.py`:

```python
from promptgrimoire.export.unicode_latex import UNICODE_PREAMBLE


class TestUnicodePreamble:
    """Test LaTeX preamble for unicode support."""

    def test_preamble_includes_luatexja(self) -> None:
        """Preamble includes luatexja-fontspec."""
        assert "luatexja-fontspec" in UNICODE_PREAMBLE

    def test_preamble_includes_emoji_package(self) -> None:
        """Preamble includes emoji package."""
        assert "\\usepackage{emoji}" in UNICODE_PREAMBLE

    def test_preamble_defines_cjktext_command(self) -> None:
        """Preamble defines \\cjktext command."""
        assert "\\newcommand{\\cjktext}" in UNICODE_PREAMBLE

    def test_preamble_sets_cjk_font(self) -> None:
        """Preamble sets CJK font (Noto)."""
        assert "Noto" in UNICODE_PREAMBLE
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestUnicodePreamble -v`

Expected: FAIL with `ImportError: cannot import name 'UNICODE_PREAMBLE'`

**Step 3: Write implementation**

Add to top of `unicode_latex.py` (after imports):

```python
UNICODE_PREAMBLE = r"""
% Unicode support for CJK and Emoji (added by unicode_latex.py)
\usepackage[match]{luatexja-fontspec}
\usepackage{emoji}

% CJK font setup - Noto fonts for broad unicode coverage
\newjfontfamily\notocjk{Noto Sans CJK SC}

% Command for wrapping CJK text (used by escape_unicode_latex)
\newcommand{\cjktext}[1]{{\notocjk #1}}

% Emoji font setup
\setemojifont{Noto Color Emoji}
"""
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestUnicodePreamble -v`

Expected: All 4 tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/unicode_latex.py tests/unit/test_unicode_handling.py
git commit -m "feat(export): add UNICODE_PREAMBLE for CJK and emoji support (#101)"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 3 Verification

**Done when:**
- [ ] `escape_unicode_latex("Hello 世界")` wraps CJK correctly
- [ ] `escape_unicode_latex("Test 🎉")` wraps emoji correctly
- [ ] Mixed content handled correctly
- [ ] `UNICODE_PREAMBLE` defines required LaTeX commands
- [ ] All unit tests pass

**Verification commands:**

```bash
# Run all Phase 3 tests
uv run pytest tests/unit/test_unicode_handling.py -v

# Type check
uvx ty check src/promptgrimoire/export/unicode_latex.py

# Test escaping manually
uv run python -c "from promptgrimoire.export.unicode_latex import escape_unicode_latex; print(escape_unicode_latex('Hello 世界 🎉'))"
```
