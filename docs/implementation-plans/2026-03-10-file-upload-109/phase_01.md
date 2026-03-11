# File Upload Support: DOCX & PDF Import — Phase 1

**Goal:** DOCX and PDF files convert to HTML via new converter module, plugged into the existing input pipeline.

**Architecture:** Two converter functions in a new `converters.py` module. DOCX uses mammoth (sync, in-memory). PDF uses pymupdf4llm for extraction + pandoc for HTML conversion (async, subprocess). Both integrate at the `NotImplementedError` seam in `html_input.py:853`.

**Tech Stack:** mammoth, pymupdf4llm, pymupdf (fitz), pandoc CLI, asyncio

**Scope:** 5 phases from original design (phase 1 of 5)

**Codebase verified:** 2026-03-10

---

## Acceptance Criteria Coverage

This phase implements and tests:

### file-upload-109.AC1: DOCX converts to annotatable HTML
- **file-upload-109.AC1.1 Success:** DOCX with paragraphs, headings, bold/italic produces semantic HTML (`<p>`, `<h1>`-`<h6>`, `<strong>`, `<em>`)
- **file-upload-109.AC1.2 Success:** Shen v R fixture renders correctly through full pipeline (upload → annotate → export PDF)
- **file-upload-109.AC1.3 Failure:** Corrupt/empty DOCX returns user-visible error, not crash

### file-upload-109.AC2: PDF converts to annotatable HTML
- **file-upload-109.AC2.1 Success:** PDF with numbered paragraphs produces HTML with paragraph structure preserved
- **file-upload-109.AC2.2 Success:** Lawlis v R fixture renders correctly through full pipeline (upload → annotate → export PDF)
- **file-upload-109.AC2.3 Failure:** Corrupt/empty PDF returns user-visible error, not crash

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create converters module with DOCX and PDF converter functions

**Verifies:** file-upload-109.AC1.1, file-upload-109.AC2.1

**Files:**
- Create: `src/promptgrimoire/input_pipeline/converters.py`

**Implementation:**

Create a new module with two converter functions:

**`convert_docx_to_html(content: bytes) -> str`** (sync):
- Wrap `content` in `io.BytesIO`
- Call `mammoth.convert_to_html(file_obj)`
- Return `result.value` (the HTML string)
- Log any `result.messages` at warning level
- Raise `ValueError` if mammoth raises an exception (corrupt/empty file)

**`convert_pdf_to_html(content: bytes) -> str`** (async):
- Create `fitz.Document` from bytes: `fitz.open(stream=content, filetype="pdf")`
- Extract markdown: `pymupdf4llm.to_markdown(doc)`
- Convert markdown to HTML via pandoc subprocess:
  - Use `asyncio.create_subprocess_exec("pandoc", "-f", "markdown", "-t", "html", stdin=PIPE, stdout=PIPE, stderr=PIPE)`
  - Write markdown bytes to stdin, read HTML from stdout
  - Check returncode, raise `ValueError` on failure
- Follow the async subprocess pattern from `export/pandoc.py:282-293`
- Raise `ValueError` for corrupt/empty PDFs (pymupdf raises `RuntimeError` for invalid PDFs)

**Testing:**
Tests must verify each AC listed above:
- file-upload-109.AC1.1: DOCX with paragraphs, headings, bold/italic produces `<p>`, `<h1>`-`<h6>`, `<strong>`, `<em>` tags
- file-upload-109.AC2.1: PDF produces HTML with `<p>` paragraph structure

Follow project testing patterns. Task-implementor generates actual test code at execution time.

Test file: `tests/unit/input_pipeline/test_converters.py`

Load fixtures with:
```python
from pathlib import Path
FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "conversations"
docx_bytes = (FIXTURES_DIR / "2025 LAWS1000 case.docx").read_bytes()
pdf_bytes = (FIXTURES_DIR / "Lawlis v R [2025] NSWCCA 183 (3 November 2025).pdf").read_bytes()
```

**Verification:**
Run: `uv run pytest tests/unit/input_pipeline/test_converters.py -v`
Expected: All tests pass

**Commit:** `feat: add DOCX and PDF converter functions (#109)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add error handling tests for corrupt files

**Verifies:** file-upload-109.AC1.3, file-upload-109.AC2.3

**Files:**
- Test: `tests/unit/input_pipeline/test_converters.py` (append to existing)

**Implementation:**

No new implementation code needed — error handling is built into Task 1's converters via try/except wrapping library exceptions into `ValueError`.

**Testing:**
Tests must verify each AC listed above:
- file-upload-109.AC1.3: Passing invalid bytes (e.g., `b"not a docx"`) to `convert_docx_to_html` raises `ValueError`
- file-upload-109.AC2.3: Passing invalid bytes (e.g., `b"not a pdf"`) to `convert_pdf_to_html` raises `ValueError`
- Empty bytes (`b""`) for both converters also raises `ValueError`

Test file: `tests/unit/input_pipeline/test_converters.py`

**Verification:**
Run: `uv run pytest tests/unit/input_pipeline/test_converters.py -v`
Expected: All tests pass including error cases

**Commit:** `test: add corrupt file error handling tests (#109)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Integrate converters into process_input() pipeline

**Verifies:** file-upload-109.AC1.1, file-upload-109.AC1.2, file-upload-109.AC2.1, file-upload-109.AC2.2

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/html_input.py:845-853` (replace NotImplementedError with converter calls)

**Implementation:**

Replace the `NotImplementedError` block in `process_input()` (lines ~845-853) with:
- `if source_type == "docx":` call `convert_docx_to_html(content)` (content must be bytes at this point)
- `elif source_type == "pdf":` call `await convert_pdf_to_html(content)`
- Keep the `else:` branch raising `NotImplementedError` for RTF (still unsupported)
- Import `convert_docx_to_html` and `convert_pdf_to_html` from `.converters`

**Note:** `content` parameter is `str | bytes`. For DOCX/PDF branches, assert `isinstance(content, bytes)` — these formats are always binary. If somehow a string arrives, raise `TypeError`.

**Testing:**
Tests must verify each AC listed above:
- file-upload-109.AC1.1: `await process_input(docx_bytes, "docx")` returns HTML with semantic tags
- file-upload-109.AC1.2: Shen v R DOCX fixture produces valid HTML through full pipeline
- file-upload-109.AC2.1: `await process_input(pdf_bytes, "pdf")` returns HTML with paragraph structure
- file-upload-109.AC2.2: Lawlis v R PDF fixture produces valid HTML through full pipeline

Test file: `tests/unit/input_pipeline/test_process_input.py` (append new test class)

**Verification:**
Run: `uv run pytest tests/unit/input_pipeline/test_process_input.py -v`
Expected: All tests pass, including new DOCX and PDF cases

Run: `uv run pytest tests/unit/input_pipeline/ -v`
Expected: All input_pipeline tests pass (no regressions)

**Commit:** `feat: integrate DOCX and PDF converters into process_input (#109)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update input_pipeline public API exports

**Verifies:** None (infrastructure)

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/__init__.py`

**Implementation:**

Add exports for the new converter functions so they're accessible from the package:
- Import and re-export `convert_docx_to_html` and `convert_pdf_to_html` from `.converters`
- Follow the existing export pattern in `__init__.py`

**Verification:**
Run: `uv run pytest tests/unit/input_pipeline/test_public_api.py -v`
Expected: Public API tests still pass (no regressions)

Run: `uv run ruff check src/promptgrimoire/input_pipeline/`
Expected: No lint errors

**Commit:** `chore: export converter functions from input_pipeline package (#109)`
<!-- END_TASK_4 -->
