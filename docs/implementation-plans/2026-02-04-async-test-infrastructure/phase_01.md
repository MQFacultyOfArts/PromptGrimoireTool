# Async Test Infrastructure Implementation Plan

**Goal:** Convert LaTeX export pipeline to async for parallel test execution

**Architecture:** Use asyncio async subprocess pattern established in compile_latex()

**Tech Stack:** Python asyncio, pytest-asyncio

**Scope:** 3 phases from original design

**Codebase verified:** 2026-02-04

---

## Phase 1: Async Pandoc Conversion

**Goal:** Convert `convert_html_to_latex()` to async

**Components:**
- `src/promptgrimoire/export/latex.py` - convert_html_to_latex() and convert_html_with_annotations()
- `src/promptgrimoire/export/pdf_export.py` - caller update
- `tests/unit/export/test_css_fidelity.py` - 14 calls to convert_html_to_latex
- `tests/integration/test_chatbot_fixtures.py` - 3 calls to convert_html_to_latex
- `tests/integration/test_pdf_export.py` - 1 call to convert_html_to_latex

**Done when:** `convert_html_to_latex()` is async, all callers (source and test) await it, tests pass

---

<!-- START_TASK_1 -->
### Task 1: Convert `convert_html_to_latex()` to async

**Files:**
- Modify: `src/promptgrimoire/export/latex.py:1186-1235`

**Step 1: Add asyncio import at top of file**

Add `import asyncio` to the imports section.

**Step 2: Change function signature to async**

Change line 1186 from:
```python
def convert_html_to_latex(html: str, filter_path: Path | None = None) -> str:
```
to:
```python
async def convert_html_to_latex(html: str, filter_path: Path | None = None) -> str:
```

**Step 3: Replace subprocess.run with async subprocess**

Replace line 1230:
```python
result = subprocess.run(cmd, capture_output=True, text=True, check=True)
```
with:
```python
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout_bytes, stderr_bytes = await proc.communicate()
if proc.returncode != 0:
    raise subprocess.CalledProcessError(
        proc.returncode, cmd, stderr_bytes.decode()
    )
```

Note: `asyncio.subprocess` is a submodule accessed via the `asyncio` import added in Step 1 — no separate import needed.

**Step 4: Update result usage**

Change:
```python
latex = result.stdout
```
to:
```python
latex = stdout_bytes.decode()
```

**Step 5: Verify tests compile (they will fail until callers updated)**

Run: `uvx ty check`
Expected: Type errors about missing await (expected at this stage)

**Step 6: Commit**

```bash
git add src/promptgrimoire/export/latex.py
git commit -m "feat: convert convert_html_to_latex to async subprocess"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Convert `convert_html_with_annotations()` to async

**Files:**
- Modify: `src/promptgrimoire/export/latex.py:1240`

**Step 1: Change function signature to async**

Find `def convert_html_with_annotations(` and change to `async def convert_html_with_annotations(`.

**Step 2: Update call to convert_html_to_latex to await**

Find the call to `convert_html_to_latex(` inside this function (around line 1302) and add `await`:
```python
latex = await convert_html_to_latex(marked_html, filter_path=filter_path)
```

**Step 3: Verify all callers identified**

Run: `grep -r "convert_html_to_latex\|convert_html_with_annotations" src/ tests/`
Expected callers:
- `src/promptgrimoire/export/latex.py` (definition and internal call)
- `src/promptgrimoire/export/pdf_export.py` (caller to update in Task 3)
- `tests/unit/export/test_css_fidelity.py` (14 calls - Task 4)
- `tests/integration/test_chatbot_fixtures.py` (3 calls - Task 4)
- `tests/integration/test_pdf_export.py` (1 call - Task 4)

All test file callers will be updated in Task 4.

**Step 4: Verify types**

Run: `uvx ty check`
Expected: Type errors about missing await in pdf_export.py (expected)

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/latex.py
git commit -m "feat: convert convert_html_with_annotations to async"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update pdf_export.py caller to await

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py`

**Step 1: Update call to await**

Find the call to `convert_html_with_annotations(` in the `export_annotation_pdf` function and add `await`:
```python
latex_body = await convert_html_with_annotations(
    html=processed_html,
    highlights=highlights,
    tag_colours=tag_colours,
    filter_path=_LIBREOFFICE_FILTER,
    word_to_legal_para=word_to_legal_para,
    escape_text=escape_text_after_markers,
)
```

**Step 2: Verify types pass**

Run: `uvx ty check`
Expected: No type errors

**Step 3: Run tests to verify**

Run: `uv run test-debug`
Expected: All tests pass

**Step 4: Commit**

```bash
git add src/promptgrimoire/export/pdf_export.py
git commit -m "feat: await async convert_html_with_annotations in pdf_export"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Convert test files to async

**Files:**
- Modify: `tests/unit/export/test_css_fidelity.py`
- Modify: `tests/integration/test_chatbot_fixtures.py`
- Modify: `tests/integration/test_pdf_export.py`

**Step 1: Update test_css_fidelity.py**

Add `@pytest.mark.asyncio` decorator to all test methods that call `convert_html_to_latex()`:
- `TestTableColumnWidths` class (2 tests)
- `TestMarginLeft` class (4 tests)
- `TestOrderedListStart` class (3 tests)
- `TestListValueNormalization` class (1 test)
- `TestUnitConversion` class (4 tests)

For each test method:
1. Change `def test_...` to `async def test_...`
2. Change `convert_html_to_latex(...)` to `await convert_html_to_latex(...)`

Example transformation:
```python
# Before
def test_50_percent_table(self) -> None:
    html = '<table style="width:50%"><tr><td>Cell</td></tr></table>'
    result = convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)
    ...

# After
@pytest.mark.asyncio
async def test_50_percent_table(self) -> None:
    html = '<table style="width:50%"><tr><td>Cell</td></tr></table>'
    result = await convert_html_to_latex(html, filter_path=LIBREOFFICE_FILTER)
    ...
```

**Step 2: Update test_chatbot_fixtures.py**

Add `@pytest.mark.asyncio` decorator to test methods:
- `TestChatbotFixturesToLatex.test_fixture_converts_to_latex` (line 81)
- `TestSpeakerLabelsInjected.test_speaker_labels_in_latex` (line 110)
- `TestSpeakerLabelsInjected.test_partial_conversation_has_user_label` (line 122)

For each:
1. Change `def test_...` to `async def test_...`
2. Change `convert_html_to_latex(...)` to `await convert_html_to_latex(...)`

**Step 3: Update test_pdf_export.py**

Find `test_legal_document_structure` (or the test calling `convert_html_to_latex`) and:
1. Add `@pytest.mark.asyncio` decorator
2. Change `def test_...` to `async def test_...`
3. Change `convert_html_to_latex(...)` to `await convert_html_to_latex(...)`

**Step 4: Run tests to verify**

Run: `uv run test-debug`
Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/unit/export/test_css_fidelity.py tests/integration/test_chatbot_fixtures.py tests/integration/test_pdf_export.py
git commit -m "test: convert test files to async for convert_html_to_latex"
```
<!-- END_TASK_4 -->
