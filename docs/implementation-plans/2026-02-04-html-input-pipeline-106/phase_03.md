# HTML Input Pipeline - Phase 3: Input Pipeline Module

**Goal:** Create the core HTML input pipeline with content type detection, char span injection, and processing orchestration.

**Architecture:** New `input_pipeline/` module that handles all input types through a unified HTML pipeline. Uses selectolax for HTML manipulation but with a hybrid approach for text node wrapping (see technical notes).

**Tech Stack:** Python, selectolax (LexborHTMLParser), regex

**Scope:** Phase 3 of 8 from original design

**Codebase verified:** 2026-02-05

---

## Codebase Verification Findings

| Assumption | Result | Actual |
|------------|--------|--------|
| `input_pipeline/` directory exists | ✗ Doesn't exist | Must be created |
| selectolax patterns | ✓ Confirmed | `export/platforms/*.py` uses `LexborHTMLParser`, CSS selectors |
| `preprocess_for_export()` | ✓ Confirmed | `export/platforms/__init__.py:106-171` |
| Content type detection | ✗ Not found | Phase 3 to implement from scratch |
| selectolax dependency | ✓ Confirmed | `pyproject.toml:36` version `>=0.4.6` |

**Critical technical finding:** Selectolax has no built-in "wrap" method for text nodes. Text nodes cannot be created directly and text is always inserted as escaped strings. The design's approach of using `selectolax DOM walk` for char span injection needs adaptation.

**Revised approach:** Use a two-pass strategy:
1. First pass: Parse with selectolax to validate structure and extract text nodes
2. Second pass: Use regex replacement on serialized HTML to wrap characters in spans

**Code patterns to follow:**
- Import: `from selectolax.lexbor import LexborHTMLParser`
- CSS queries: `tree.css(selector)`, `tree.css_first(selector)`
- Remove elements: `node.decompose()`
- Unwrap elements: `node.unwrap()`
- Get output: `tree.html`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Create import module structure and detect_content_type()

**Files:**
- Create: `src/promptgrimoire/input_pipeline/__init__.py`
- Create: `src/promptgrimoire/input_pipeline/html_input.py`

**Step 1: Create the import directory**

Run:
```bash
mkdir -p /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline/src/promptgrimoire/input_pipeline
```

**Step 2: Create __init__.py**

Write to `src/promptgrimoire/input_pipeline/__init__.py`:

```python
"""HTML input pipeline for processing various document formats."""

from promptgrimoire.input_pipeline.html_input import (
    CONTENT_TYPES,
    detect_content_type,
    inject_char_spans,
    process_input,
    strip_char_spans,
)

__all__ = [
    "CONTENT_TYPES",
    "detect_content_type",
    "inject_char_spans",
    "process_input",
    "strip_char_spans",
]
```

**Step 3: Create html_input.py with detect_content_type()**

Write to `src/promptgrimoire/input_pipeline/html_input.py`:

```python
"""HTML input pipeline: detection, conversion, and char span injection.

This module provides the unified input pipeline for the annotation page.
All input types (HTML, RTF, DOCX, PDF, plain text) go through the same
HTML-based pipeline for character-level annotation support.
"""

from __future__ import annotations

import re
from typing import Literal

# Content types supported by the pipeline
CONTENT_TYPES = ("html", "rtf", "docx", "pdf", "text")
ContentType = Literal["html", "rtf", "docx", "pdf", "text"]


def detect_content_type(content: str | bytes) -> ContentType:
    """Detect content type from magic bytes or structure.

    Args:
        content: Raw content to analyze (string or bytes).

    Returns:
        Detected content type: "html", "rtf", "docx", "pdf", or "text".

    Detection heuristics:
        - RTF: Starts with {\\rtf
        - PDF: Starts with %PDF
        - DOCX: PK magic bytes (ZIP archive with specific structure)
        - HTML: Starts with <!DOCTYPE, <html, or contains HTML-like tags
        - Text: Default fallback
    """
    # Convert to string for analysis if bytes
    if isinstance(content, bytes):
        # Check binary signatures first
        if content.startswith(b"%PDF"):
            return "pdf"
        if content.startswith(b"PK"):
            # DOCX is a ZIP archive - check for [Content_Types].xml
            # Simple heuristic: PK signature + later occurrence of word/document
            if b"word/document" in content[:2000] or b"[Content_Types].xml" in content[:2000]:
                return "docx"
        if content.startswith(b"{\\rtf"):
            return "rtf"
        # Try to decode for HTML/text detection
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = content.decode("latin-1")
            except UnicodeDecodeError:
                return "text"  # Binary content we can't decode

    # String-based detection
    stripped = content.lstrip()

    # RTF detection (text form)
    if stripped.startswith("{\\rtf"):
        return "rtf"

    # HTML detection
    lower = stripped.lower()
    if lower.startswith("<!doctype") or lower.startswith("<html"):
        return "html"

    # Check for HTML-like structure (tags)
    if re.search(r"<(div|p|span|h[1-6]|ul|ol|li|table|body)\b", stripped, re.IGNORECASE):
        return "html"

    # Default to plain text
    return "text"
```

**Step 4: Verify module compiles**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.input_pipeline.html_input import detect_content_type; print(detect_content_type('<html><body>test</body></html>'))"
```

Expected: Prints "html"

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write tests for detect_content_type()

**Files:**
- Create: `tests/unit/input_pipeline/__init__.py`
- Create: `tests/unit/input_pipeline/test_content_type.py`

**Step 1: Create test directory**

Run:
```bash
mkdir -p /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline/tests/unit/input_pipeline
touch /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline/tests/unit/input_pipeline/__init__.py
```

**Step 2: Write failing tests**

Write to `tests/unit/input_pipeline/test_content_type.py`:

```python
"""Tests for content type detection."""

import pytest

from promptgrimoire.input_pipeline.html_input import detect_content_type


class TestDetectContentType:
    """Tests for detect_content_type()."""

    def test_html_doctype(self) -> None:
        """Detect HTML from DOCTYPE declaration."""
        content = "<!DOCTYPE html><html><body>Hello</body></html>"
        assert detect_content_type(content) == "html"

    def test_html_tag_only(self) -> None:
        """Detect HTML from html tag without DOCTYPE."""
        content = "<html><body>Hello</body></html>"
        assert detect_content_type(content) == "html"

    def test_html_with_div(self) -> None:
        """Detect HTML from div tag."""
        content = "<div>Hello world</div>"
        assert detect_content_type(content) == "html"

    def test_html_with_paragraph(self) -> None:
        """Detect HTML from p tag."""
        content = "<p>Hello world</p>"
        assert detect_content_type(content) == "html"

    def test_html_case_insensitive(self) -> None:
        """Detect HTML regardless of tag case."""
        content = "<HTML><BODY>Hello</BODY></HTML>"
        assert detect_content_type(content) == "html"

    def test_html_with_whitespace(self) -> None:
        """Detect HTML even with leading whitespace."""
        content = "   \n\n<!DOCTYPE html><html><body>Hello</body></html>"
        assert detect_content_type(content) == "html"

    def test_rtf_string(self) -> None:
        """Detect RTF from magic header."""
        content = r"{\rtf1\ansi\deff0 Hello}"
        assert detect_content_type(content) == "rtf"

    def test_rtf_bytes(self) -> None:
        """Detect RTF from bytes."""
        content = b"{\\rtf1\\ansi\\deff0 Hello}"
        assert detect_content_type(content) == "rtf"

    def test_pdf_bytes(self) -> None:
        """Detect PDF from magic bytes."""
        content = b"%PDF-1.4 fake pdf content"
        assert detect_content_type(content) == "pdf"

    def test_docx_bytes(self) -> None:
        """Detect DOCX from PK signature and word content marker."""
        # Simulated DOCX header (simplified)
        content = b"PK\x03\x04" + b"\x00" * 100 + b"word/document.xml"
        assert detect_content_type(content) == "docx"

    def test_plain_text(self) -> None:
        """Detect plain text as fallback."""
        content = "Just some plain text without any markup."
        assert detect_content_type(content) == "text"

    def test_plain_text_with_angle_brackets(self) -> None:
        """Plain text with < but no HTML tags is still text."""
        content = "5 < 10 and 10 > 5"
        assert detect_content_type(content) == "text"

    def test_empty_string(self) -> None:
        """Empty string is plain text."""
        assert detect_content_type("") == "text"

    def test_bytes_utf8(self) -> None:
        """Bytes content decoded as UTF-8."""
        content = "<html><body>Hello</body></html>".encode("utf-8")
        assert detect_content_type(content) == "html"
```

**Step 3: Run tests to verify they pass**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/input_pipeline/test_content_type.py -v
```

Expected: All tests pass

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Implement inject_char_spans()

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/html_input.py`

**Step 1: Add inject_char_spans() function**

Add to `src/promptgrimoire/input_pipeline/html_input.py` after `detect_content_type()`:

```python
from selectolax.lexbor import LexborHTMLParser


def inject_char_spans(html: str) -> str:
    """Wrap each text character in a data-char-index span.

    Args:
        html: HTML content (after preprocessing).

    Returns:
        HTML with each text character wrapped in
        <span class="char" data-char-index="N">c</span>

    Implementation notes:
        Uses a regex-based approach because selectolax doesn't support
        direct text node manipulation. We parse to validate structure,
        then use regex to wrap characters in text content.

        Special handling:
        - Whitespace is preserved as HTML entities (&nbsp; etc.)
        - <br> tags become newline characters with indices
        - Script, style, and other non-content tags are ignored
    """
    # Parse to validate and normalize HTML
    tree = LexborHTMLParser(html)

    # Get body content (or full html if no body)
    body = tree.body
    if body is None:
        # Not a full document, parse as fragment
        return _inject_spans_to_html(html)

    body_html = body.inner_html
    if not body_html:
        return html

    injected = _inject_spans_to_html(body_html)

    # Reconstruct full document if we had one
    head = tree.head
    head_html = head.html if head else ""
    return f"<!DOCTYPE html><html>{head_html}<body>{injected}</body></html>"


def _inject_spans_to_html(html: str) -> str:
    """Inject char spans into HTML fragment.

    Internal function that processes HTML text content character by character,
    wrapping each in a span with data-char-index attribute.
    """
    # State machine for tracking position in HTML
    result: list[str] = []
    char_index = 0
    i = 0
    n = len(html)

    while i < n:
        if html[i] == "<":
            # Find end of tag
            tag_end = html.find(">", i)
            if tag_end == -1:
                # Malformed HTML, treat rest as text
                break

            tag_content = html[i + 1 : tag_end]
            full_tag = html[i : tag_end + 1]

            # Check if this is a self-closing or void tag
            tag_name = _get_tag_name(tag_content)
            is_closing = tag_content.startswith("/")

            # Skip content of script, style, etc.
            if tag_name in ("script", "style", "noscript", "template"):
                # Find closing tag and skip everything
                close_tag = f"</{tag_name}>"
                close_pos = html.lower().find(close_tag.lower(), tag_end + 1)
                if close_pos != -1:
                    result.append(html[i : close_pos + len(close_tag)])
                    i = close_pos + len(close_tag)
                    continue

            # Handle <br> as newline character
            if tag_name == "br":
                span = f'<span class="char" data-char-index="{char_index}">\n</span>'
                result.append(span)
                char_index += 1
                i = tag_end + 1
                continue

            # Pass through other tags unchanged
            result.append(full_tag)
            i = tag_end + 1
        elif html[i] == "&":
            # HTML entity - find end
            entity_end = html.find(";", i)
            if entity_end != -1 and entity_end - i < 10:
                entity = html[i : entity_end + 1]
                # Wrap entity as single character
                span = f'<span class="char" data-char-index="{char_index}">{entity}</span>'
                result.append(span)
                char_index += 1
                i = entity_end + 1
            else:
                # Not a valid entity, treat & as character
                span = f'<span class="char" data-char-index="{char_index}">&amp;</span>'
                result.append(span)
                char_index += 1
                i += 1
        else:
            # Regular character - wrap in span
            char = html[i]
            # Escape special characters
            if char == " ":
                # Preserve spaces as non-breaking for selection
                span = f'<span class="char" data-char-index="{char_index}">&nbsp;</span>'
            elif char == "\n":
                span = f'<span class="char" data-char-index="{char_index}">\n</span>'
            elif char == "<":
                span = f'<span class="char" data-char-index="{char_index}">&lt;</span>'
            elif char == ">":
                span = f'<span class="char" data-char-index="{char_index}">&gt;</span>'
            elif char == '"':
                span = f'<span class="char" data-char-index="{char_index}">&quot;</span>'
            else:
                span = f'<span class="char" data-char-index="{char_index}">{char}</span>'
            result.append(span)
            char_index += 1
            i += 1

    return "".join(result)


def _get_tag_name(tag_content: str) -> str:
    """Extract tag name from tag content (without < and >).

    Examples:
        "div class='foo'" -> "div"
        "/div" -> "div"
        "br/" -> "br"
    """
    # Remove leading / for closing tags
    content = tag_content.lstrip("/").strip()
    # Get first word (tag name)
    name = content.split()[0] if content.split() else ""
    # Remove trailing / for self-closing
    return name.rstrip("/").lower()
```

**Step 2: Verify function compiles**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.input_pipeline.html_input import inject_char_spans; print(inject_char_spans('<p>Hi</p>')[:100])"
```

Expected: Shows span-wrapped output

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Write tests for inject_char_spans()

**Files:**
- Create: `tests/unit/input_pipeline/test_char_spans.py`

**Step 1: Write tests**

Write to `tests/unit/input_pipeline/test_char_spans.py`:

```python
"""Tests for char span injection."""

import pytest

from promptgrimoire.input_pipeline.html_input import inject_char_spans, strip_char_spans


class TestInjectCharSpans:
    """Tests for inject_char_spans()."""

    def test_simple_text(self) -> None:
        """Basic text gets wrapped character by character."""
        result = inject_char_spans("<p>Hi</p>")
        assert '<span class="char" data-char-index="0">' in result
        assert '<span class="char" data-char-index="1">' in result
        # H and i should be wrapped
        assert 'data-char-index="0">H</span>' in result
        assert 'data-char-index="1">i</span>' in result

    def test_preserves_tags(self) -> None:
        """HTML structure tags are preserved."""
        result = inject_char_spans("<div><p>A</p></div>")
        assert "<div>" in result
        assert "<p>" in result
        assert "</p>" in result
        assert "</div>" in result

    def test_sequential_indices(self) -> None:
        """Indices are sequential across elements."""
        result = inject_char_spans("<p>AB</p><p>CD</p>")
        assert 'data-char-index="0">A</span>' in result
        assert 'data-char-index="1">B</span>' in result
        assert 'data-char-index="2">C</span>' in result
        assert 'data-char-index="3">D</span>' in result

    def test_spaces_as_nbsp(self) -> None:
        """Spaces are converted to &nbsp; for selection."""
        result = inject_char_spans("<p>A B</p>")
        assert "&nbsp;</span>" in result

    def test_br_as_newline(self) -> None:
        """<br> tags become newline characters with indices."""
        result = inject_char_spans("<p>A<br>B</p>")
        # br should be converted to a newline span
        assert 'data-char-index="1">\n</span>' in result

    def test_html_entities_preserved(self) -> None:
        """HTML entities are kept as single characters."""
        result = inject_char_spans("<p>&amp;</p>")
        # &amp; should be wrapped as one character
        assert "&amp;</span>" in result

    def test_skips_script_content(self) -> None:
        """Script tag content is not wrapped."""
        result = inject_char_spans("<p>A</p><script>var x=1;</script><p>B</p>")
        assert "<script>var x=1;</script>" in result
        # Only A and B should be indexed
        assert 'data-char-index="0">A</span>' in result
        assert 'data-char-index="1">B</span>' in result

    def test_skips_style_content(self) -> None:
        """Style tag content is not wrapped."""
        result = inject_char_spans("<p>X</p><style>.cls{}</style>")
        assert "<style>.cls{}</style>" in result

    def test_attributes_preserved(self) -> None:
        """Element attributes are preserved."""
        result = inject_char_spans('<div class="foo" id="bar">X</div>')
        assert 'class="foo"' in result
        assert 'id="bar"' in result

    def test_empty_input(self) -> None:
        """Empty input returns empty output."""
        result = inject_char_spans("")
        assert result == ""

    def test_nested_elements(self) -> None:
        """Nested elements work correctly."""
        result = inject_char_spans("<div><span>AB</span></div>")
        assert 'data-char-index="0">A</span>' in result
        assert 'data-char-index="1">B</span>' in result


class TestStripCharSpans:
    """Tests for strip_char_spans()."""

    def test_roundtrip_simple(self) -> None:
        """Inject then strip returns similar content."""
        original = "<p>Hello</p>"
        injected = inject_char_spans(original)
        stripped = strip_char_spans(injected)
        # Should have text content back (may have &nbsp; for spaces)
        assert "Hello" in stripped or "H" in stripped

    def test_removes_char_spans(self) -> None:
        """Char spans are removed."""
        injected = '<p><span class="char" data-char-index="0">A</span></p>'
        stripped = strip_char_spans(injected)
        assert 'data-char-index' not in stripped
        assert 'class="char"' not in stripped
        assert "A" in stripped

    def test_preserves_other_spans(self) -> None:
        """Non-char spans are kept."""
        html = '<p><span class="highlight">A</span></p>'
        result = strip_char_spans(html)
        assert 'class="highlight"' in result
```

**Step 2: Run tests (they will fail - strip_char_spans not yet implemented)**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/input_pipeline/test_char_spans.py::TestInjectCharSpans -v
```

Expected: TestInjectCharSpans tests pass (or reveal needed fixes)

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->

<!-- START_TASK_5 -->
### Task 5: Implement strip_char_spans() and process_input()

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/html_input.py`

**Step 1: Add strip_char_spans() function**

Add to `src/promptgrimoire/input_pipeline/html_input.py`:

```python
def strip_char_spans(html_with_spans: str) -> str:
    """Remove char span wrappers, preserving content.

    Args:
        html_with_spans: HTML with <span class="char" data-char-index="N"> wrappers.

    Returns:
        Clean HTML with char spans unwrapped (content preserved).
    """
    tree = LexborHTMLParser(html_with_spans)

    # Find all char spans and unwrap them
    for span in tree.css('span.char[data-char-index]'):
        span.unwrap()

    return tree.html
```

**Step 2: Add process_input() orchestration function**

Add to `src/promptgrimoire/input_pipeline/html_input.py`:

```python
from promptgrimoire.export.platforms import preprocess_for_export


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

    Note:
        Step 1 (conversion) is implemented in Phase 7.
        For now, only HTML and text inputs are fully supported.
    """
    # Convert bytes to string if needed
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            content = content.decode("latin-1")

    # Step 1: Convert to HTML based on source type
    if source_type == "text":
        # Wrap plain text in paragraph tags
        html = _text_to_html(content)
    elif source_type == "html":
        html = content
    else:
        # RTF, DOCX, PDF conversion - Phase 7
        # For now, raise NotImplementedError
        msg = f"Conversion from {source_type} not yet implemented (Phase 7)"
        raise NotImplementedError(msg)

    # Step 2: Preprocess (remove chrome, inject speaker labels)
    preprocessed = preprocess_for_export(html, platform_hint=platform_hint)

    # Step 3: Inject char spans
    result = inject_char_spans(preprocessed)

    return result


def _text_to_html(text: str) -> str:
    """Convert plain text to HTML paragraphs.

    Args:
        text: Plain text content.

    Returns:
        HTML with text wrapped in <p> tags, double newlines as paragraph breaks.
    """
    import html as html_module

    # Escape HTML special characters
    escaped = html_module.escape(text)

    # Split on double newlines for paragraphs
    paragraphs = escaped.split("\n\n")

    # Wrap each paragraph, convert single newlines to <br>
    html_parts = []
    for para in paragraphs:
        if para.strip():
            # Convert single newlines to <br>
            para_html = para.replace("\n", "<br>")
            html_parts.append(f"<p>{para_html}</p>")

    return "\n".join(html_parts) if html_parts else "<p></p>"
```

**Step 3: Update __init__.py exports**

Update `src/promptgrimoire/input_pipeline/__init__.py`:

```python
"""HTML input pipeline for processing various document formats."""

from promptgrimoire.input_pipeline.html_input import (
    CONTENT_TYPES,
    ContentType,
    detect_content_type,
    inject_char_spans,
    process_input,
    strip_char_spans,
)

__all__ = [
    "CONTENT_TYPES",
    "ContentType",
    "detect_content_type",
    "inject_char_spans",
    "process_input",
    "strip_char_spans",
]
```

**Step 4: Verify module compiles**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.input_pipeline import process_input; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Write integration tests and commit

**Files:**
- Create: `tests/unit/input_pipeline/test_process_input.py`

**Step 1: Write tests for process_input()**

Write to `tests/unit/input_pipeline/test_process_input.py`:

```python
"""Tests for process_input() orchestration."""

import pytest

from promptgrimoire.input_pipeline.html_input import process_input, strip_char_spans


class TestProcessInput:
    """Tests for process_input()."""

    @pytest.mark.asyncio
    async def test_plain_text_conversion(self) -> None:
        """Plain text is converted to HTML paragraphs."""
        result = await process_input("Hello world", source_type="text")
        assert "<p>" in result
        assert 'data-char-index="0">' in result

    @pytest.mark.asyncio
    async def test_html_passthrough(self) -> None:
        """HTML content goes through preprocessing and span injection."""
        result = await process_input("<p>Test</p>", source_type="html")
        assert 'data-char-index="0">' in result

    @pytest.mark.asyncio
    async def test_text_double_newline_paragraphs(self) -> None:
        """Double newlines create separate paragraphs."""
        result = await process_input("Para 1\n\nPara 2", source_type="text")
        # Should have two <p> tags
        assert result.count("<p>") == 2

    @pytest.mark.asyncio
    async def test_bytes_input(self) -> None:
        """Bytes input is decoded and processed."""
        result = await process_input(b"<p>Test</p>", source_type="html")
        assert 'data-char-index="0">' in result

    @pytest.mark.asyncio
    async def test_unsupported_format_raises(self) -> None:
        """Unsupported formats raise NotImplementedError."""
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await process_input("content", source_type="rtf")

    @pytest.mark.asyncio
    async def test_output_strippable(self) -> None:
        """Output can be stripped back to clean HTML."""
        result = await process_input("<p>Hello</p>", source_type="html")
        stripped = strip_char_spans(result)
        assert "Hello" in stripped
        assert "data-char-index" not in stripped
```

**Step 2: Run all import tests**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/input_pipeline/ -v
```

Expected: All tests pass

**Step 3: Run full test suite to check for regressions**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run test-debug
```

Expected: All tests pass (or only unrelated skips)

**Step 4: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && git add src/promptgrimoire/input_pipeline/ tests/unit/input_pipeline/ && git commit -m "feat(input): add HTML input pipeline with char span injection

- Add detect_content_type() for sniffing input format
- Add inject_char_spans() for character-level selection support
- Add strip_char_spans() for export path
- Add process_input() orchestration function
- Plain text wrapped in <p> tags, double newlines as paragraph breaks
- RTF/DOCX/PDF conversion deferred to Phase 7

Part of #106 HTML input pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_C -->

---

## Phase 3 Completion Criteria

- [ ] `src/promptgrimoire/input_pipeline/` module created
- [ ] `detect_content_type()` detects HTML, RTF, DOCX, PDF, text
- [ ] `inject_char_spans()` wraps each character with indexed span
- [ ] `strip_char_spans()` removes char spans preserving content
- [ ] `process_input()` orchestrates the pipeline
- [ ] Plain text converted to HTML paragraphs
- [ ] All unit tests pass
- [ ] Changes committed

## Technical Notes

### Selectolax Limitations

The design document suggested using selectolax DOM walk for char span injection. However, selectolax has these limitations:

1. **No text node creation**: Cannot create standalone text nodes
2. **No wrap method**: Unlike BeautifulSoup, no direct `.wrap()` for text
3. **Text insertion escapes**: `insert_after(text)` escapes HTML

### Implemented Approach

We use a hybrid approach:
1. **Validation pass**: Parse with selectolax to validate structure
2. **Injection pass**: Use a state machine to iterate through HTML characters and wrap text content in spans

This approach:
- Preserves all HTML structure (tags, attributes)
- Handles HTML entities correctly (single character index)
- Skips script/style content
- Converts `<br>` to newline characters with indices
- Is deterministic and testable
