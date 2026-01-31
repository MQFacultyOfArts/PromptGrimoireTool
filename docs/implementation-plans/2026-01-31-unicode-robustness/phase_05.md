# Unicode Robustness Implementation Plan - Phase 5

**Goal:** Replace `_escape_latex()` with unicode-aware version and integrate preamble

**Architecture:** Replace 8 call sites of `_escape_latex()` with `escape_unicode_latex()` in `_format_annot()`. Add `UNICODE_PREAMBLE` to `build_annotation_preamble()`. No changes needed to `pdf_export.py`.

**Tech Stack:** Python

**Scope:** Phase 5 of 7 from design plan

**Codebase verified:** 2026-01-31

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Replace `_escape_latex()` calls with `escape_unicode_latex()`

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/latex.py`

**Step 1: Add import at top of file**

Add after existing imports (around line 20):

```python
from promptgrimoire.export.unicode_latex import escape_unicode_latex
```

**Step 2: Replace all `_escape_latex()` calls**

Find and replace all 8 occurrences in `_format_annot()`:

- Line 642: `_escape_latex(tag_display)` → `escape_unicode_latex(tag_display)`
- Line 644: `_escape_latex(tag_display)` → `escape_unicode_latex(tag_display)`
- Line 649: `_escape_latex(author)` → `escape_unicode_latex(author)`
- Line 652: `_escape_latex(author)` → `escape_unicode_latex(author)`
- Line 664: `_escape_latex(c_author)` → `escape_unicode_latex(c_author)`
- Line 665: `_escape_latex(c_text)` → `escape_unicode_latex(c_text)`
- Line 669: `_escape_latex(c_author)` → `escape_unicode_latex(c_author)`
- Line 670: `_escape_latex(c_text)` → `escape_unicode_latex(c_text)`

**Step 3: Run existing tests to verify no regression**

Run: `uv run pytest tests/unit/export/test_latex_string_functions.py -v`

Expected: All existing tests pass (they use ASCII only)

**Step 4: Commit**

```bash
git add src/promptgrimoire/export/latex.py
git commit -m "refactor(export): replace _escape_latex with escape_unicode_latex (#101)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Integrate UNICODE_PREAMBLE into build_annotation_preamble()

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/latex.py`

**Step 1: Add import for UNICODE_PREAMBLE**

Update the import (around line 20):

```python
from promptgrimoire.export.unicode_latex import escape_unicode_latex, UNICODE_PREAMBLE
```

**Step 2: Modify build_annotation_preamble() to include UNICODE_PREAMBLE**

Update the function at lines 559-569:

```python
def build_annotation_preamble(tag_colours: dict[str, str]) -> str:
    """Build complete annotation preamble with tag colour definitions."""
    colour_defs = generate_tag_colour_definitions(tag_colours)
    return f"\\usepackage{{xcolor}}\n{colour_defs}\n{UNICODE_PREAMBLE}\n{ANNOTATION_PREAMBLE_BASE}"
```

**Step 3: Run existing tests**

Run: `uv run pytest tests/unit/export/ -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add src/promptgrimoire/export/latex.py
git commit -m "feat(export): add UNICODE_PREAMBLE to annotation preamble (#101)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add integration test for CJK in annotations

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/export/test_latex_string_functions.py`

**Step 1: Add test for CJK in annotation escaping**

Add to the test file:

```python
class TestUnicodeAnnotationEscaping:
    """Test unicode handling in annotation formatting."""

    def test_cjk_author_name_escaped(self) -> None:
        """CJK characters in author name are wrapped correctly."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("田中太郎")
        assert "\\cjktext{田中太郎}" in result

    def test_cjk_comment_text_escaped(self) -> None:
        """CJK characters in comment text are wrapped correctly."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("これは日本語のコメントです")
        assert "\\cjktext{" in result

    def test_emoji_in_comment_escaped(self) -> None:
        """Emoji in comment text are wrapped correctly."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("Great work! 🎉")
        assert "\\emoji{" in result

    def test_mixed_ascii_cjk_special_chars(self) -> None:
        """Mixed content with special chars handles all correctly."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("User & 田中 100%")
        assert "\\&" in result  # Special char escaped
        assert "\\cjktext{田中}" in result  # CJK wrapped
        assert "\\%" in result  # Special char escaped
```

**Step 2: Run new tests**

Run: `uv run pytest tests/unit/export/test_latex_string_functions.py::TestUnicodeAnnotationEscaping -v`

Expected: All 4 tests pass

**Step 3: Commit**

```bash
git add tests/unit/export/test_latex_string_functions.py
git commit -m "test(export): add unicode annotation escaping tests (#101)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 5 Verification

**Done when:**
- [ ] All 8 `_escape_latex()` calls replaced with `escape_unicode_latex()`
- [ ] `UNICODE_PREAMBLE` integrated into `build_annotation_preamble()`
- [ ] Existing PDF export tests still pass
- [ ] New unicode escaping tests pass

**Verification commands:**

```bash
# Run all export tests
uv run pytest tests/unit/export/ -v

# Run integration tests (if TinyTeX available)
uv run pytest tests/integration/test_pdf_export.py -v -m slow

# Verify preamble includes unicode setup
uv run python -c "from promptgrimoire.export.latex import build_annotation_preamble; p = build_annotation_preamble({}); print('luatexja-fontspec' in p, 'emoji' in p)"
```
