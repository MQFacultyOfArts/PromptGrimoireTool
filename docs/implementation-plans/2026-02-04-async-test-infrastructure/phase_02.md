## Phase 2: Fix Test Files

**Goal:** Remove sync subprocess calls from tests, use HTML fixture for LibreOffice

**Components:**
- `tests/integration/test_cross_env_highlights.py` - load HTML fixture directly
- `tests/unit/test_overlapping_highlights.py` - use compile_latex()
- `tests/unit/test_latex_packages.py` - use compile_latex()

**Done when:** No direct subprocess calls for LaTeX compilation in test files, tests pass

---

<!-- START_TASK_1 -->
### Task 1: Load HTML fixture directly in test_cross_env_highlights.py

**Files:**
- Modify: `tests/integration/test_cross_env_highlights.py`

**Step 1: Update imports**

Remove:
```python
from promptgrimoire.parsers.rtf import parse_rtf
```

Add:
```python
from promptgrimoire.models import ParsedRTF
```

**Step 2: Update fixture to load HTML directly**

Replace the `parsed_lawlis` fixture (lines 26-30) with:
```python
@pytest.fixture(scope="module")
def parsed_lawlis() -> ParsedRTF:
    """Load pre-converted HTML fixture (LibreOffice conversion done offline)."""
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    html_path = fixtures_dir / "183-libreoffice.html"
    rtf_path = fixtures_dir / "183.rtf"
    return ParsedRTF(
        original_blob=rtf_path.read_bytes(),
        html=html_path.read_text(encoding="utf-8"),
        source_filename="183.rtf",
    )
```

**Step 3: Remove xdist_group marker**

Remove this line (no longer need to share LibreOffice process):
```python
pytestmark = pytest.mark.xdist_group("rtf_parser")
```

**Step 4: Run test to verify**

Run: `uv run pytest tests/integration/test_cross_env_highlights.py -v`
Expected: Test passes

**Step 5: Commit**

```bash
git add tests/integration/test_cross_env_highlights.py
git commit -m "test: load HTML fixture directly in test_cross_env_highlights"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Use compile_latex in test_overlapping_highlights.py

**Files:**
- Modify: `tests/unit/test_overlapping_highlights.py`

**Step 1: Update imports**

Add near the top:
```python
import pytest
from promptgrimoire.export.pdf import compile_latex
```

Remove the now-unused `import subprocess` (line 10).

**Step 2: Convert test function to async**

Find the test function that contains the subprocess.run call and:
- Add `@pytest.mark.asyncio` decorator
- Change `def test_...` to `async def test_...`

**Step 3: Replace subprocess.run with compile_latex**

Find the subprocess.run call for latexmk (around lines 174-184) and replace:
```python
from promptgrimoire.export.pdf import get_latexmk_path

latexmk = get_latexmk_path()

result = subprocess.run(
    [str(latexmk), "-lualatex", "-interaction=nonstopmode", str(tex_file)],
    cwd=tmp_path,
    capture_output=True,
    text=True,
    timeout=60,
    check=False,
)

# Check compilation succeeded
assert result.returncode == 0, f"LaTeX compilation failed:\n{result.stderr}"
```

With:
```python
pdf_path = await compile_latex(tex_file, output_dir=tmp_path)
assert pdf_path.exists(), "LaTeX compilation failed"
```

Note: The `@requires_latexmk` decorator should remain — `compile_latex()` uses `get_latexmk_path()` which raises `FileNotFoundError` if latexmk is not available.

**Step 4: Run test to verify**

Run: `uv run pytest tests/unit/test_overlapping_highlights.py -v`
Expected: Test passes

**Step 5: Commit**

```bash
git add tests/unit/test_overlapping_highlights.py
git commit -m "test: use compile_latex in test_overlapping_highlights"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Use compile_latex in test_latex_packages.py

**Files:**
- Modify: `tests/unit/test_latex_packages.py`

**Step 1: Add compile_latex import**

Add near the top:
```python
from promptgrimoire.export.pdf import compile_latex
```

**Step 2: Convert test_unicode_preamble_compiles_without_tofu to async**

Find the test function in class `TestLaTeXPackages` and:
- Add `@pytest.mark.asyncio` decorator
- Change `def test_unicode_preamble_compiles_without_tofu` to `async def test_unicode_preamble_compiles_without_tofu`

**Step 3: Replace direct lualatex call with compile_latex**

Find the lualatex subprocess.run call (around lines 143-158) and replace:
```python
# Compile with LuaLaTeX (check=False because we verify via PDF existence)
compile_result = subprocess.run(
    [str(lualatex), "-interaction=nonstopmode", str(tex_file)],
    capture_output=True,
    text=True,
    cwd=tmp_path,
    check=False,
)

pdf_file = tmp_path / "test_unicode.pdf"
assert pdf_file.exists(), (
    f"LuaLaTeX compilation failed.\n"
    f"Return code: {compile_result.returncode}\n"
    f"Stdout: {compile_result.stdout[-2000:]}\n"
    f"Stderr: {compile_result.stderr[-500:]}"
)
```

With:
```python
pdf_file = await compile_latex(tex_file, output_dir=tmp_path)
assert pdf_file.exists(), "LuaLaTeX compilation failed"
```

Note: The pdftotext subprocess.run call later in the test (around lines 161-166) should remain synchronous — it's a quick local tool call for PDF text extraction, not a long-running compilation process.

**Step 4: Run test to verify**

Run: `uv run pytest tests/unit/test_latex_packages.py::TestLaTeXPackages::test_unicode_preamble_compiles_without_tofu -v`
Expected: Test passes

**Step 5: Commit**

```bash
git add tests/unit/test_latex_packages.py
git commit -m "test: use compile_latex in test_latex_packages"
```
<!-- END_TASK_3 -->
