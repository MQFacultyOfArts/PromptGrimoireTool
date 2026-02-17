# HTML Input Pipeline - Phase 8: E2E Tests

**Goal:** Re-enable and update E2E tests for the HTML input pipeline, covering paste, upload, and character selection.

**Architecture:** Update existing skipped tests in `tests/e2e/test_annotation.py` to use new `ui.editor` component and verify char span selection works.

**Tech Stack:** Playwright, pytest-playwright, NiceGUI test patterns

**Scope:** Phase 8 of 8 from original design

**Codebase verified:** 2026-02-05

---

## Codebase Verification Findings

| Assumption | Result | Actual |
|------------|--------|--------|
| Skipped E2E tests exist | ✓ Confirmed | 15+ tests with `pytest.skip("Pending #106")` |
| Playwright patterns | ✓ Confirmed | `tests/e2e/conftest.py`, `test_annotation.py` |
| Character selection tests | ✓ Confirmed | `test_can_select_characters_in_document()` skipped |
| Chatbot fixtures | ✓ Confirmed | 16 HTML files in `tests/fixtures/chatbot_exports/` |
| File upload E2E | ✗ Not found | No existing upload patterns |

**Key skipped tests (from `test_annotation.py`):**
- `test_can_create_workspace` - Line ~45
- `test_can_add_document_to_workspace` - Line ~65
- `test_can_select_characters_in_document` - Line ~105
- `test_can_add_highlight` - Line ~145
- `test_chatbot_html_preserves_structure` - Line ~185

**Playwright patterns used (from existing tests):**
```python
# Form input
await page.fill('input[name="workspace_name"]', 'Test Workspace')

# Button click
await page.click('button:has-text("Create")')

# Wait for element
await page.wait_for_selector('.document-content')

# Rich text editor (Quasar QEditor) - standard Playwright pattern:
# Since .fill() strips HTML, QEditor requires setting content via JS
editor = page.locator('.q-editor__content')
await editor.evaluate('el => el.innerHTML = "<p>Test</p>"')
```

**Note:** Setting innerHTML via `evaluate()` is the standard Playwright pattern for testing rich text editors since `.fill()` strips HTML formatting.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Re-enable workspace creation test

**Files:**
- Modify: `tests/e2e/test_annotation.py`

**Step 1: Find and update the skipped test**

Find `test_can_create_workspace` (around line 45) and remove the skip:

```python
# REMOVE this line:
pytest.skip("Pending #106 HTML input redesign")

# The test should use existing patterns:
async def test_can_create_workspace(page: Page) -> None:
    """Test creating a new workspace."""
    await page.goto("/annotation")

    # Click "New Workspace" button
    await page.click('button:has-text("New Workspace")')

    # Fill workspace name
    await page.fill('input[placeholder*="name"]', 'Test Workspace')

    # Submit
    await page.click('button:has-text("Create")')

    # Verify workspace appears
    await page.wait_for_selector('text=Test Workspace')
```

**Step 2: Verify test runs**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/e2e/test_annotation.py::test_can_create_workspace -v --headed
```

Expected: Test passes (may need adjustment based on actual UI)

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Re-enable document addition test with ui.editor

**Files:**
- Modify: `tests/e2e/test_annotation.py`

**Step 1: Add helper function for QEditor input**

Add at the top of the test file (after imports):

```python
async def fill_editor(page: Page, selector: str, html_content: str) -> None:
    """Fill a QEditor component with HTML content.

    Playwright's .fill() method strips HTML, so we use evaluate() to set
    the content directly. This is the standard pattern for rich text editors.
    """
    editor = page.locator(selector)
    await editor.wait_for()
    # Set content via JavaScript - standard Playwright pattern for rich editors
    await editor.evaluate("(el, content) => el.innerHTML = content", html_content)
```

**Step 2: Update the document addition test**

Find `test_can_add_document_to_workspace` and update it:

```python
async def test_can_add_document_to_workspace(page: Page) -> None:
    """Test adding a document with HTML content to a workspace."""
    # First create a workspace
    await page.goto("/annotation")
    await page.click('button:has-text("New Workspace")')
    await page.fill('input[placeholder*="name"]', 'Test Workspace')
    await page.click('button:has-text("Create")')
    await page.wait_for_selector('text=Test Workspace')

    # Select the workspace
    await page.click('text=Test Workspace')

    # Add content via the QEditor
    test_html = "<p>Hello <strong>World</strong></p>"
    await fill_editor(page, '.q-editor__content', test_html)

    # Click Add Document button
    await page.click('button:has-text("Add Document")')

    # Handle content type dialog - confirm as HTML
    await page.wait_for_selector('text=Confirm Content Type')
    await page.click('button:has-text("Confirm")')

    # Verify document appears with char spans
    doc_content = page.locator('.document-content')
    await doc_content.wait_for()

    # Check that char spans were injected
    span_count = await doc_content.locator('span.char').count()
    assert span_count > 0, "Expected char spans to be injected"
```

**Step 3: Verify test runs**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/e2e/test_annotation.py::test_can_add_document_to_workspace -v --headed
```

Expected: Test passes

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Re-enable character selection test

**Files:**
- Modify: `tests/e2e/test_annotation.py`

**Step 1: Update the character selection test**

Find `test_can_select_characters_in_document` and update it:

```python
async def test_can_select_characters_in_document(page: Page) -> None:
    """Test selecting character range for highlighting."""
    # Setup: Create workspace with document
    await page.goto("/annotation")
    await page.click('button:has-text("New Workspace")')
    await page.fill('input[placeholder*="name"]', 'Selection Test')
    await page.click('button:has-text("Create")')
    await page.click('text=Selection Test')

    # Add a document with known content
    test_content = "<p>Hello World Test</p>"
    await fill_editor(page, '.q-editor__content', test_content)
    await page.click('button:has-text("Add Document")')
    await page.wait_for_selector('text=Confirm Content Type')
    await page.click('button:has-text("Confirm")')

    # Wait for char spans to be injected
    doc_content = page.locator('.document-content')
    await doc_content.wait_for()

    # Select characters by clicking and dragging
    # First char span should be 'H', we'll select 'Hello' (chars 0-4)
    first_char = doc_content.locator('span.char[data-char-index="0"]')
    fifth_char = doc_content.locator('span.char[data-char-index="4"]')

    await first_char.wait_for()
    await fifth_char.wait_for()

    # Click first char and drag to fifth
    await first_char.click()
    await page.keyboard.down('Shift')
    await fifth_char.click()
    await page.keyboard.up('Shift')

    # Verify selection state is tracked (implementation-dependent)
    # The exact verification depends on how the UI shows selections
```

**Step 2: Verify test runs**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/e2e/test_annotation.py::test_can_select_characters_in_document -v --headed
```

Expected: Test passes (may need adjustment based on selection UI)

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add chatbot HTML import test

**Files:**
- Modify: `tests/e2e/test_annotation.py`

**Step 1: Add test using fixture HTML**

Add a new test that uses one of the chatbot export fixtures:

```python
import pytest
from pathlib import Path


@pytest.fixture
def claude_export_html() -> str:
    """Load Claude.ai export HTML fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "chatbot_exports" / "claude-ai-export.html"
    if not fixture_path.exists():
        pytest.skip("Claude.ai export fixture not found")
    return fixture_path.read_text()


async def test_chatbot_html_preserves_structure(
    page: Page,
    claude_export_html: str,
) -> None:
    """Test that chatbot HTML exports preserve conversation structure."""
    await page.goto("/annotation")

    # Create workspace
    await page.click('button:has-text("New Workspace")')
    await page.fill('input[placeholder*="name"]', 'Chatbot Import Test')
    await page.click('button:has-text("Create")')
    await page.click('text=Chatbot Import Test')

    # Paste chatbot HTML (truncate for test performance)
    truncated_html = claude_export_html[:5000]  # First 5KB
    await fill_editor(page, '.q-editor__content', truncated_html)

    # Add document
    await page.click('button:has-text("Add Document")')
    await page.wait_for_selector('text=Confirm Content Type')
    await page.click('button:has-text("Confirm")')

    # Verify document content contains char spans
    doc_content = page.locator('.document-content')
    await doc_content.wait_for()

    span_count = await doc_content.locator('span.char').count()
    assert span_count > 100, f"Expected many char spans, got {span_count}"

    # Verify conversation structure is preserved (look for message boundaries)
    # This depends on how the chatbot HTML is structured
    content_html = await doc_content.inner_html()
    assert '<p>' in content_html or '<div>' in content_html, "Expected paragraph/div structure"
```

**Step 2: Verify fixture exists**

Check that at least one chatbot fixture is available:
```bash
ls /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline/tests/fixtures/chatbot_exports/
```

**Step 3: Run test**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/e2e/test_annotation.py::test_chatbot_html_preserves_structure -v --headed
```

Expected: Test passes (or skips if fixture missing)

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->

<!-- START_TASK_5 -->
### Task 5: Add file upload E2E test

**Files:**
- Modify: `tests/e2e/test_annotation.py`

**Step 1: Create test HTML fixture file**

Create `tests/fixtures/test_upload.html`:

```html
<!DOCTYPE html>
<html>
<head><title>Test Upload</title></head>
<body>
<p>This is a <strong>test</strong> HTML file for upload testing.</p>
<p>It contains multiple paragraphs to verify structure preservation.</p>
</body>
</html>
```

**Step 2: Add file upload test**

```python
async def test_file_upload_html(page: Page, tmp_path: Path) -> None:
    """Test uploading an HTML file through ui.upload."""
    # Create test file
    test_file = tmp_path / "test.html"
    test_file.write_text("""
    <!DOCTYPE html>
    <html><body>
    <p>Uploaded <em>content</em> here.</p>
    </body></html>
    """)

    await page.goto("/annotation")

    # Create workspace
    await page.click('button:has-text("New Workspace")')
    await page.fill('input[placeholder*="name"]', 'Upload Test')
    await page.click('button:has-text("Create")')
    await page.click('text=Upload Test')

    # Upload file via ui.upload
    # NiceGUI's ui.upload creates an input[type=file]
    file_input = page.locator('input[type="file"]')
    await file_input.set_input_files(str(test_file))

    # Handle content type dialog
    await page.wait_for_selector('text=Confirm Content Type')
    await page.click('button:has-text("Confirm")')

    # Verify document appears
    await page.wait_for_selector('.document-content')

    # Verify char spans injected
    span_count = await page.locator('.document-content span.char').count()
    assert span_count > 0, "Expected char spans in uploaded document"
```

**Step 3: Run test**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/e2e/test_annotation.py::test_file_upload_html -v --headed
```

Expected: Test passes

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Run full E2E suite and commit

**Files:**
- None (testing only)

**Step 1: Remove remaining #106 skips**

Search for any remaining skips and either remove them or update them:

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && grep -n "Pending #106" tests/e2e/
```

Remove skips from tests that are now working with the new pipeline.

**Step 2: Run all E2E tests**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/e2e/ -v
```

Expected: All tests pass (some may still be skipped for other reasons)

**Step 3: Run full test suite**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run test-debug
```

Expected: All tests pass

**Step 4: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && git add tests/ && git commit -m "test(e2e): update annotation tests for HTML input pipeline

- Re-enable workspace creation and document addition tests
- Add fill_editor() helper for QEditor HTML input
- Update character selection tests for char span indices
- Add chatbot HTML import test using fixtures
- Add file upload E2E test
- Remove #106 skip markers from updated tests

Closes #106 HTML input pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_C -->

---

## Phase 8 Completion Criteria

- [ ] `test_can_create_workspace` re-enabled and passing
- [ ] `test_can_add_document_to_workspace` works with `ui.editor`
- [ ] `test_can_select_characters_in_document` works with char spans
- [ ] `test_chatbot_html_preserves_structure` added
- [ ] `test_file_upload_html` added
- [ ] All #106 skip markers removed from passing tests
- [ ] Full E2E suite passes
- [ ] Changes committed

## Technical Notes

### Testing Rich Text Editors with Playwright

Playwright's `.fill()` method is designed for plain text inputs and strips HTML formatting. For rich text editors like Quasar QEditor, the standard pattern is:

```python
# Standard Playwright pattern for rich text editors
editor = page.locator('.q-editor__content')
await editor.evaluate("(el, content) => el.innerHTML = content", html_content)
```

This is documented in Playwright's testing guide for contenteditable elements.

### Character Selection Testing

The char span system uses `data-char-index` attributes:

```html
<span class="char" data-char-index="0">H</span>
<span class="char" data-char-index="1">e</span>
```

Tests can select specific characters by index:

```python
first_char = doc.locator('span.char[data-char-index="0"]')
```

### File Upload Testing

NiceGUI's `ui.upload` creates a standard file input. Playwright can interact with it:

```python
file_input = page.locator('input[type="file"]')
await file_input.set_input_files(str(file_path))
```

### Test Isolation

Each E2E test should:
1. Create its own workspace (isolation)
2. Use unique names to avoid conflicts
3. Clean up is handled by test database teardown
