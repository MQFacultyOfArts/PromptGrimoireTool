# HTML Input Pipeline - Phase 5: UI Integration

**Goal:** Integrate HTML input pipeline into the annotation page with `ui.editor` for paste and `ui.upload` for file uploads.

**Architecture:** Replace textarea with `ui.editor` (Quasar QEditor) for HTML paste support. Add file upload component. Connect to `process_input()` pipeline with content type dialog.

**Tech Stack:** NiceGUI (`ui.editor`, `ui.upload`, `ui.dialog`)

**Scope:** Phase 5 of 8 from original design

**Codebase verified:** 2026-02-05

---

## Codebase Verification Findings

| Assumption | Result | Actual |
|------------|--------|--------|
| Current input via textarea | ✓ Confirmed | `annotation.py` lines 1451-1487, plain `ui.textarea` |
| `handle_add_document()` | ✓ Confirmed | Nested in `_render_workspace_view()` at lines 1459-1487 |
| File upload pattern exists | ✓ Confirmed | `roleplay.py` ~line 240 has `ui.upload` example |
| Document creation via `add_document()` | ✓ Confirmed | `db/workspace_documents.py` lines 10-54 |
| Content rendering | ✓ Confirmed | `ui.html(doc.content, sanitize=False)` at line 1055 |
| Spike winner: `ui.editor` | ✓ Confirmed | Design doc spike results show SUCCESS |

**NiceGUI APIs (from Context7):**

```python
# ui.editor - WYSIWYG HTML editor
editor = ui.editor(placeholder='Type or paste here')
html_content = editor.value  # Returns HTML string

# ui.upload - File upload
ui.upload(
    on_upload=handler,
    auto_upload=True,
    label="Upload file",
).props('accept=".html,.txt"')

# UploadEventArguments
async def handler(e: events.UploadEventArguments):
    name = e.file.name
    content = await e.file.read()  # bytes
    text = await e.file.text()     # string
```

**Prerequisites:** Phase 1 (schema changes) and Phase 3 (input pipeline) must be complete.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Replace textarea with ui.editor for HTML paste

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Find the current textarea implementation**

The current implementation is in `_render_workspace_view()` around lines 1448-1460. Look for:

```python
content_input = ui.textarea(
    placeholder="Paste or type your content here..."
).classes("w-full min-h-32")
```

**Step 2: Replace with ui.editor**

Replace the textarea with:

```python
# HTML-aware editor for paste support (Quasar QEditor)
content_input = ui.editor(
    placeholder="Paste HTML content or type plain text here..."
).classes("w-full min-h-32").props("toolbar=[]")  # Hide toolbar for minimal UI
```

Note: `.props("toolbar=[]")` hides the editor toolbar for a cleaner paste-focused interface. If you want basic formatting tools, use:
```python
.props('toolbar=[["bold", "italic", "underline"]]')
```

**Step 3: Verify the page loads**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.pages.annotation import create_annotation_page; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add file upload component

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Add file upload below the editor**

After the `content_input` editor, add a file upload component:

```python
# File upload for HTML, RTF, DOCX, PDF, TXT files
file_upload = ui.upload(
    label="Or upload a file",
    on_upload=handle_file_upload,
    auto_upload=True,
    max_file_size=10 * 1024 * 1024,  # 10 MB limit
).props('accept=".html,.htm,.rtf,.docx,.pdf,.txt"').classes("w-full")
```

**Step 2: Add placeholder handler**

Add a placeholder `handle_file_upload` function (will be implemented in Task 3):

```python
async def handle_file_upload(e: events.UploadEventArguments) -> None:
    """Handle file upload - placeholder for Task 3."""
    ui.notify(f"File upload not yet implemented: {e.file.name}")
```

**Step 3: Verify the page loads**

Run the app and navigate to annotation page:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && timeout 5 uv run python -m promptgrimoire || true
```

Expected: App starts without errors (will timeout after 5 seconds)

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Implement handle_add_document() with pipeline integration

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Add imports at top of file**

Add these imports to `annotation.py`:

```python
from promptgrimoire.input_pipeline.html_input import detect_content_type, process_input
from promptgrimoire.pages.dialogs import show_content_type_dialog
```

**Step 2: Rewrite handle_add_document()**

Replace the current `handle_add_document()` function (lines ~1459-1487) with:

```python
async def handle_add_document() -> None:
    """Process input and add document to workspace."""
    content = content_input.value
    if not content or not content.strip():
        ui.notify("Please enter or paste some content", type="warning")
        return

    # Detect content type
    detected_type = detect_content_type(content)

    # Show confirmation dialog
    confirmed_type = await show_content_type_dialog(
        detected_type=detected_type,
        preview=content[:500],
    )

    if confirmed_type is None:
        # User cancelled
        return

    try:
        # Process through HTML pipeline
        processed_html = await process_input(
            content=content,
            source_type=confirmed_type,
            platform_hint=None,  # Auto-detect platform
        )

        # Add to database
        await add_document(
            workspace_id=workspace_id,
            type="source",
            content=processed_html,
            source_type=confirmed_type,
            title=None,
        )

        # Clear input and refresh
        content_input.value = ""
        ui.notify("Document added successfully", type="positive")
        await refresh_documents()

    except Exception as e:
        ui.notify(f"Failed to add document: {e}", type="negative")
```

**Step 3: Verify syntax**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.pages.annotation import create_annotation_page; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Implement handle_file_upload()

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Implement file upload handler**

Replace the placeholder `handle_file_upload()` with:

```python
async def handle_file_upload(e: events.UploadEventArguments) -> None:
    """Handle file upload through HTML pipeline."""
    filename = e.file.name
    content_type = e.file.content_type

    # Read file content
    try:
        content_bytes = await e.file.read()
    except Exception as err:
        ui.notify(f"Failed to read file: {err}", type="negative")
        return

    # Detect type from extension and content
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext_to_type = {
        "html": "html",
        "htm": "html",
        "rtf": "rtf",
        "docx": "docx",
        "pdf": "pdf",
        "txt": "text",
    }
    detected_type = ext_to_type.get(ext)

    if detected_type is None:
        # Fall back to content detection
        detected_type = detect_content_type(content_bytes)

    # Try to get preview text
    try:
        if detected_type in ("html", "text"):
            preview = content_bytes.decode("utf-8")[:500]
        else:
            preview = f"[Binary file: {filename}]"
    except UnicodeDecodeError:
        preview = f"[Binary file: {filename}]"

    # Show confirmation dialog
    confirmed_type = await show_content_type_dialog(
        detected_type=detected_type,
        preview=preview,
    )

    if confirmed_type is None:
        ui.notify("Upload cancelled", type="info")
        return

    try:
        # Process through HTML pipeline
        processed_html = await process_input(
            content=content_bytes,
            source_type=confirmed_type,
            platform_hint=None,
        )

        # Add to database
        await add_document(
            workspace_id=workspace_id,
            type="source",
            content=processed_html,
            source_type=confirmed_type,
            title=filename,
        )

        ui.notify(f"Uploaded: {filename}", type="positive")
        await refresh_documents()

    except NotImplementedError as e:
        ui.notify(f"Format not yet supported: {e}", type="warning")
    except Exception as e:
        ui.notify(f"Failed to process file: {e}", type="negative")
```

**Step 2: Add events import if not present**

Ensure this import exists at the top of the file:

```python
from nicegui import events
```

**Step 3: Verify syntax**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.pages.annotation import create_annotation_page; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->

<!-- START_TASK_5 -->
### Task 5: Remove _process_text_to_char_spans() usage

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Identify _process_text_to_char_spans() calls**

Search for uses of the old function:

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && grep -n "_process_text_to_char_spans" src/promptgrimoire/pages/annotation.py
```

**Step 2: Remove or deprecate the function**

The old `_process_text_to_char_spans()` function (around line 213-255) is no longer needed since the pipeline now uses `inject_char_spans()` from the input_pipeline module. Options:

1. **If no other callers:** Delete the function entirely
2. **If other callers exist:** Add deprecation comment and redirect to new pipeline

For now, keep the function but add a deprecation comment:

```python
def _process_text_to_char_spans(text: str) -> tuple[str, list[str]]:
    """DEPRECATED: Use promptgrimoire.input_pipeline.html_input.inject_char_spans() instead.

    This function remains for backward compatibility but will be removed.
    """
    # ... existing implementation ...
```

**Step 3: Verify no regressions**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/ -v -k "annotation or char" --tb=short
```

Expected: Tests pass

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Integration test and commit

**Files:**
- Modify: Tests as needed

**Step 1: Run full test suite**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run test-debug
```

Expected: All tests pass (or only unrelated skips)

**Step 2: Manual smoke test**

Start the app:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -m promptgrimoire
```

Test:
1. Navigate to annotation page
2. Create a workspace
3. Paste HTML content (e.g., from Claude.ai conversation)
4. Verify content type dialog appears
5. Confirm and verify document appears with char spans

**Step 3: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && git add src/promptgrimoire/pages/annotation.py && git commit -m "feat(ui): integrate HTML input pipeline into annotation page

- Replace textarea with ui.editor for HTML paste support
- Add ui.upload for file uploads (.html, .rtf, .docx, .pdf, .txt)
- Integrate with content type detection and confirmation dialog
- Connect to process_input() pipeline for char span injection
- Update handle_add_document() to use new schema (source_type)
- Deprecate _process_text_to_char_spans() in favor of input_pipeline module

Part of #106 HTML input pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_C -->

---

## Phase 5 Completion Criteria

- [ ] `ui.editor` replaces textarea for HTML paste support
- [ ] `ui.upload` component added for file uploads
- [ ] Content type detection and dialog integrated
- [ ] `handle_add_document()` uses new pipeline
- [ ] `handle_file_upload()` processes uploaded files
- [ ] Uses new schema (`source_type` instead of `raw_content`)
- [ ] Manual smoke test passes
- [ ] Changes committed

## Technical Notes

### ui.editor vs textarea

| Feature | textarea | ui.editor |
|---------|----------|-----------|
| Plain text | ✓ | ✓ |
| HTML paste | ✗ (strips formatting) | ✓ (preserves structure) |
| Rich editing | ✗ | ✓ (optional toolbar) |
| .value type | string | HTML string |

### Spike Winner Rationale

From design doc spike results:
- **ui.editor (Spike D)**: 260KB HTML preserved from Claude.ai paste
- Clean `.value` access returns HTML
- NiceGUI-native component
- No custom JavaScript required

### File Type Support

| Extension | Content Type | Status |
|-----------|--------------|--------|
| .html, .htm | HTML | ✓ Full support |
| .txt | Plain text | ✓ Full support |
| .rtf | RTF | ⏳ Phase 7 (LibreOffice) |
| .docx | Word | ⏳ Phase 7 (LibreOffice) |
| .pdf | PDF | ⏳ Phase 7 (pdftohtml) |

RTF, DOCX, and PDF uploads will show "Format not yet supported" until Phase 7 adds conversion.
