# HTML Input Pipeline - Phase 7: Format Conversion

**Goal:** Add RTF, DOCX, and PDF to HTML conversion using LibreOffice and pdftohtml.

**Architecture:** Extend `process_input()` in `html_input.py` with async subprocess calls to external tools. Follow existing patterns from `parsers/rtf.py` and `export/pdf.py`.

**Tech Stack:** LibreOffice (headless), pdftohtml (poppler-utils), asyncio subprocess

**Scope:** Phase 7 of 8 from original design

**Codebase verified:** 2026-02-05

---

## Codebase Verification Findings

| Assumption | Result | Actual |
|------------|--------|--------|
| Subprocess patterns exist | ✓ Confirmed | `export/pdf.py` (async), `parsers/rtf.py` (sync) |
| LibreOffice usage | ✓ Confirmed | `parsers/rtf.py:57-100` for RTF→HTML |
| Async pattern | ✓ Confirmed | `asyncio.create_subprocess_exec()` in `pdf.py`, `latex.py` |
| PDF→HTML tool | ✗ Not found | No existing pdftohtml integration |
| Tool dependency handling | ✓ Confirmed | `@requires_latexmk`, `@requires_pandoc` patterns |

**Existing LibreOffice pattern (from `parsers/rtf.py`):**
```python
subprocess.run([
    "libreoffice",
    "--headless",
    "--convert-to", "html",
    "--outdir", tmpdir,
    str(input_path),
], capture_output=True, text=True, timeout=60, check=False)
```

**Async subprocess pattern (from `pdf.py`):**
```python
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await proc.communicate()
```

**Note:** Python's `asyncio.create_subprocess_exec()` is the safe non-shell subprocess API (similar to Node's `execFile` vs `exec`). All arguments are passed as a list, preventing shell injection.

**External tool references:**
- [LibreOffice CLI conversion](https://technicallywewrite.com/2025/08/21/libreoffice)
- [pdftohtml manual](https://manpages.debian.org/testing/poppler-utils/pdftohtml.1.en.html)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Implement convert_to_html() function

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/html_input.py`

**Step 1: Add conversion imports and helper functions**

Add at the top of `html_input.py`:

```python
import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path


def _has_libreoffice() -> bool:
    """Check if LibreOffice is available."""
    return shutil.which("libreoffice") is not None or shutil.which("soffice") is not None


def _has_pdftohtml() -> bool:
    """Check if pdftohtml (poppler-utils) is available."""
    return shutil.which("pdftohtml") is not None


def _get_libreoffice_cmd() -> str:
    """Get LibreOffice command name."""
    if shutil.which("libreoffice"):
        return "libreoffice"
    if shutil.which("soffice"):
        return "soffice"
    raise FileNotFoundError("LibreOffice not found. Install with: apt install libreoffice")
```

**Step 2: Implement convert_to_html() function**

Add the main conversion function:

```python
async def convert_to_html(
    content: bytes,
    source_type: ContentType,
) -> str:
    """Convert RTF, DOCX, or PDF to HTML.

    Args:
        content: File content as bytes.
        source_type: Source format ("rtf", "docx", or "pdf").

    Returns:
        HTML string.

    Raises:
        NotImplementedError: If format not supported.
        FileNotFoundError: If required tool not installed.
        subprocess.CalledProcessError: If conversion fails.
    """
    if source_type == "html":
        # Already HTML, just decode
        return content.decode("utf-8")

    if source_type == "text":
        # Plain text, wrap in paragraphs
        return _text_to_html(content.decode("utf-8"))

    if source_type in ("rtf", "docx"):
        return await _convert_with_libreoffice(content, source_type)

    if source_type == "pdf":
        return await _convert_pdf_to_html(content)

    raise NotImplementedError(f"Conversion from {source_type} not supported")


async def _convert_with_libreoffice(content: bytes, source_type: str) -> str:
    """Convert RTF or DOCX to HTML using LibreOffice headless mode.

    Uses asyncio.create_subprocess_exec (safe, non-shell) for non-blocking execution.
    """
    if not _has_libreoffice():
        raise FileNotFoundError(
            "LibreOffice not found. Install with:\n"
            "  Ubuntu/Debian: apt install libreoffice\n"
            "  macOS: brew install --cask libreoffice"
        )

    lo_cmd = _get_libreoffice_cmd()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Write content to temp file with correct extension
        input_file = tmpdir_path / f"input.{source_type}"
        input_file.write_bytes(content)

        # Run LibreOffice conversion (args as list, no shell)
        cmd = [
            lo_cmd,
            "--headless",
            "--convert-to", "html",
            "--outdir", str(tmpdir_path),
            str(input_file),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, stderr.decode()
            )

        # Find output file
        output_file = tmpdir_path / "input.html"
        if not output_file.exists():
            raise FileNotFoundError(
                f"LibreOffice conversion produced no output. stderr: {stderr.decode()}"
            )

        return output_file.read_text(encoding="utf-8")


async def _convert_pdf_to_html(content: bytes) -> str:
    """Convert PDF to HTML using pdftohtml (poppler-utils).

    Uses asyncio.create_subprocess_exec (safe, non-shell) for non-blocking execution.
    """
    if not _has_pdftohtml():
        raise FileNotFoundError(
            "pdftohtml not found. Install with:\n"
            "  Ubuntu/Debian: apt install poppler-utils\n"
            "  macOS: brew install poppler"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Write PDF to temp file
        input_file = tmpdir_path / "input.pdf"
        input_file.write_bytes(content)

        # Output base (pdftohtml adds .html)
        output_base = tmpdir_path / "output"

        # Run pdftohtml with options (args as list, no shell):
        # -s: single page output (not multi-page)
        # -dataurls: embed images as data URLs
        # -noframes: don't generate frame structure
        cmd = [
            "pdftohtml",
            "-s",           # Single HTML file
            "-dataurls",    # Embed images as base64
            "-noframes",    # No frame structure
            str(input_file),
            str(output_base),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, stderr.decode()
            )

        # pdftohtml creates output-html.html or outputs.html
        output_file = tmpdir_path / "output-html.html"
        if not output_file.exists():
            output_file = tmpdir_path / "outputs.html"
        if not output_file.exists():
            # Try without suffix
            output_file = tmpdir_path / "output.html"
        if not output_file.exists():
            raise FileNotFoundError(
                f"pdftohtml conversion produced no output. stderr: {stderr.decode()}"
            )

        return output_file.read_text(encoding="utf-8")
```

**Step 3: Verify module compiles**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.input_pipeline.html_input import convert_to_html; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update process_input() to use convert_to_html()

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/html_input.py`

**Step 1: Update process_input() to call conversion**

Update the `process_input()` function to use `convert_to_html()`:

```python
async def process_input(
    content: str | bytes,
    source_type: ContentType,
    platform_hint: str | None = None,
) -> str:
    """Full input processing pipeline: convert → preprocess → inject spans.

    Args:
        content: Raw input content (string or bytes).
        source_type: Confirmed content type.
        platform_hint: Optional platform hint for chatbot exports.

    Returns:
        Processed HTML with char spans ready for annotation.

    Pipeline steps:
        1. Convert to HTML (if not already HTML)
        2. Preprocess for export (remove chrome, inject speaker labels)
        3. Inject character spans for selection
    """
    # Ensure we have bytes for conversion
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content

    # Step 1: Convert to HTML
    html = await convert_to_html(content_bytes, source_type)

    # Step 2: Preprocess (remove chrome, inject speaker labels)
    preprocessed = preprocess_for_export(html, platform_hint=platform_hint)

    # Step 3: Inject char spans
    result = inject_char_spans(preprocessed)

    return result
```

**Step 2: Update exports in __init__.py**

Update `src/promptgrimoire/input_pipeline/__init__.py`:

```python
"""HTML input pipeline for processing various document formats."""

from promptgrimoire.input_pipeline.html_input import (
    CONTENT_TYPES,
    ContentType,
    convert_to_html,
    detect_content_type,
    inject_char_spans,
    process_input,
    strip_char_spans,
)

__all__ = [
    "CONTENT_TYPES",
    "ContentType",
    "convert_to_html",
    "detect_content_type",
    "inject_char_spans",
    "process_input",
    "strip_char_spans",
]
```

**Step 3: Verify syntax**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.input_pipeline import process_input, convert_to_html; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Write tests for format conversion

**Files:**
- Create: `tests/unit/input_pipeline/test_format_conversion.py`

**Step 1: Write unit tests**

Write to `tests/unit/input_pipeline/test_format_conversion.py`:

```python
"""Tests for format conversion functions.

These tests check the module structure and tool detection.
Full conversion tests require external tools (LibreOffice, pdftohtml)
and are marked for conditional execution.
"""

import pytest

from promptgrimoire.input_pipeline.html_input import (
    _has_libreoffice,
    _has_pdftohtml,
    convert_to_html,
)


class TestToolDetection:
    """Tests for tool detection functions."""

    def test_has_libreoffice_returns_bool(self) -> None:
        """Function returns boolean."""
        result = _has_libreoffice()
        assert isinstance(result, bool)

    def test_has_pdftohtml_returns_bool(self) -> None:
        """Function returns boolean."""
        result = _has_pdftohtml()
        assert isinstance(result, bool)


# Conditional decorator for LibreOffice tests
requires_libreoffice = pytest.mark.skipif(
    not _has_libreoffice(),
    reason="LibreOffice not installed"
)

# Conditional decorator for pdftohtml tests
requires_pdftohtml = pytest.mark.skipif(
    not _has_pdftohtml(),
    reason="pdftohtml (poppler-utils) not installed"
)


class TestConvertToHtml:
    """Tests for convert_to_html function."""

    @pytest.mark.asyncio
    async def test_html_passthrough(self) -> None:
        """HTML content passes through unchanged (just decoded)."""
        html = b"<p>Hello world</p>"
        result = await convert_to_html(html, source_type="html")
        assert result == "<p>Hello world</p>"

    @pytest.mark.asyncio
    async def test_text_wrapped_in_paragraphs(self) -> None:
        """Plain text is wrapped in paragraph tags."""
        text = b"Hello world"
        result = await convert_to_html(text, source_type="text")
        assert "<p>" in result
        assert "Hello" in result

    @pytest.mark.asyncio
    async def test_unsupported_format_raises(self) -> None:
        """Unsupported formats raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await convert_to_html(b"content", source_type="unknown")  # type: ignore

    @requires_libreoffice
    @pytest.mark.asyncio
    async def test_rtf_conversion(self) -> None:
        """RTF content is converted to HTML."""
        rtf = rb"{\rtf1\ansi\deff0 Hello RTF}"
        result = await convert_to_html(rtf, source_type="rtf")
        # LibreOffice produces full HTML document
        assert "<html" in result.lower() or "<body" in result.lower()


class TestMissingTools:
    """Tests for graceful handling of missing tools."""

    @pytest.mark.asyncio
    async def test_rtf_without_libreoffice_error_message(self) -> None:
        """RTF conversion without LibreOffice shows helpful error."""
        if _has_libreoffice():
            pytest.skip("LibreOffice is installed")

        with pytest.raises(FileNotFoundError) as exc_info:
            await convert_to_html(b"rtf content", source_type="rtf")

        assert "LibreOffice" in str(exc_info.value)
        assert "apt install" in str(exc_info.value) or "brew install" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pdf_without_pdftohtml_error_message(self) -> None:
        """PDF conversion without pdftohtml shows helpful error."""
        if _has_pdftohtml():
            pytest.skip("pdftohtml is installed")

        with pytest.raises(FileNotFoundError) as exc_info:
            await convert_to_html(b"pdf content", source_type="pdf")

        assert "pdftohtml" in str(exc_info.value)
        assert "poppler" in str(exc_info.value).lower()
```

**Step 2: Run tests**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/input_pipeline/test_format_conversion.py -v
```

Expected: Tests pass (some may be skipped if tools not installed)

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Integration tests and commit

**Files:**
- None (testing only)

**Step 1: Run all import tests**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/input_pipeline/ -v
```

Expected: All tests pass

**Step 2: Run full test suite**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run test-debug
```

Expected: All tests pass (conversion tests may skip if tools not installed)

**Step 3: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && git add src/promptgrimoire/input_pipeline/ tests/unit/input_pipeline/test_format_conversion.py && git commit -m "feat(import): add RTF, DOCX, PDF to HTML conversion

- Add convert_to_html() with LibreOffice for RTF/DOCX
- Add pdftohtml (poppler-utils) integration for PDF
- Async subprocess execution following existing patterns
- Helpful error messages when tools not installed
- Unit tests with conditional execution based on tool availability

Part of #106 HTML input pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

---

## Phase 7 Completion Criteria

- [ ] `convert_to_html()` handles RTF, DOCX, PDF, HTML, and text
- [ ] LibreOffice conversion works for RTF and DOCX
- [ ] pdftohtml conversion works for PDF
- [ ] `process_input()` calls `convert_to_html()` instead of raising NotImplementedError
- [ ] Tool detection functions work correctly
- [ ] Missing tools show helpful installation instructions
- [ ] Unit tests pass
- [ ] Changes committed

## Technical Notes

### External Tool Dependencies

| Format | Tool | Package | Install Command |
|--------|------|---------|-----------------|
| RTF | LibreOffice | libreoffice | `apt install libreoffice` / `brew install --cask libreoffice` |
| DOCX | LibreOffice | libreoffice | same |
| PDF | pdftohtml | poppler-utils | `apt install poppler-utils` / `brew install poppler` |

### LibreOffice Headless Mode

```bash
libreoffice --headless --convert-to html --outdir /tmp input.docx
```

- `--headless`: No GUI
- `--convert-to html`: Output format
- `--outdir`: Output directory
- Produces `input.html` in outdir

### pdftohtml Options

```bash
pdftohtml -s -dataurls -noframes input.pdf output
```

- `-s`: Single HTML file (not multi-page)
- `-dataurls`: Embed images as base64 data URLs
- `-noframes`: No frame structure
- Produces `output-html.html` or similar

### Async vs Sync

The existing `parsers/rtf.py` uses sync `subprocess.run()`. This phase uses async `asyncio.create_subprocess_exec()` to match the pattern in `export/pdf.py` and avoid blocking the NiceGUI event loop during conversion.

### Security Note

We use `asyncio.create_subprocess_exec()` which passes arguments as a list (not through a shell), preventing command injection vulnerabilities. This is equivalent to Node.js's `execFile()` vs `exec()`.
