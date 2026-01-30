# Workspace Model Implementation Plan - Phase 3: New Route

**Goal:** `/annotation` route works with workspace model. Users can create workspaces, add documents, and annotate using the new CRDT structure.

**Architecture:** New NiceGUI page following patterns from `live_annotation_demo.py`. Uses workspace-aware CRDT loading/persistence from Phase 2. Workspace creation and document addition via forms.

**Tech Stack:** NiceGUI, pycrdt, SQLModel, Playwright (E2E tests)

**Scope:** 5 phases from original design (this is phase 3 of 5)

**Codebase verified:** 2026-01-31

**Design document:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/93-workspace-model/docs/design-plans/2026-01-30-workspace-model.md`

---

## UAT: Falsifiable Statement

> The `/annotation` route allows a user to create a workspace, paste text content that becomes a WorkspaceDocument, annotate that document with highlights, and have those annotations persist across page reloads.

**How to verify (E2E test in Task 5):**
1. Navigate to `/annotation`
2. Create a new workspace
3. Paste text content
4. Select text and create a highlight
5. Reload the page (with workspace ID in URL)
6. **Assert:** highlight is still visible

---

## Key Design Decisions

1. **Workspace ID in URL** - `/annotation?workspace_id=<uuid>` for direct linking and reload persistence
2. **Create-first flow** - User must create workspace before adding content (matches design)
3. **Reuse UI components** - Word-span processing, highlight rendering from `live_annotation_demo.py`
4. **Gradual migration** - This page exists alongside `/demo/live-annotation` (Phase 4 verifies both work)
5. **Client-side selection detection** - Note: Detecting browser text selection inherently requires JavaScript. The implementation uses `ui.run_javascript()` for this unavoidable browser API access. E2E TESTS correctly use Playwright's native mouse events to simulate user selection - they never inject JS.
6. **Observable persistence state** - Tests wait for a visible "Saved" indicator rather than arbitrary timeouts

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
## Task 1: Create basic /annotation page route

**Files:**
- Create: `src/promptgrimoire/pages/annotation.py`
- Modify: `src/promptgrimoire/main.py` (register route)
- Create: `tests/e2e/test_annotation_page.py`

**Step 1: Write the failing E2E test**

Create `tests/e2e/test_annotation_page.py`:

```python
"""E2E tests for /annotation page."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


class TestAnnotationPageBasic:
    """Basic page load tests."""

    def test_annotation_page_loads(self, page: Page, live_server: str) -> None:
        """Page loads without errors."""
        page.goto(f"{live_server}/annotation")
        expect(page.locator("body")).to_be_visible()

    def test_page_shows_create_workspace_option(self, page: Page, live_server: str) -> None:
        """Page shows option to create workspace when no workspace_id."""
        page.goto(f"{live_server}/annotation")

        # Should show create workspace button or form
        create_button = page.get_by_role("button", name=re.compile("create", re.IGNORECASE))
        expect(create_button).to_be_visible()

    def test_page_title_is_annotation(self, page: Page, live_server: str) -> None:
        """Page has appropriate title."""
        page.goto(f"{live_server}/annotation")
        expect(page).to_have_title(re.compile("annotation", re.IGNORECASE))
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/e2e/test_annotation_page.py::TestAnnotationPageBasic::test_annotation_page_loads -v`
Expected: FAIL with 404 or connection error (page doesn't exist)

**Step 3: Write minimal implementation**

Create `src/promptgrimoire/pages/annotation.py`:

```python
"""Annotation page with workspace model support.

This page provides the new workspace-based annotation flow:
1. User creates or enters a workspace
2. User pastes/uploads content to create WorkspaceDocument
3. User annotates document with highlights
4. All state persists via workspace CRDT
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.pages import page_route

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)


@page_route("/annotation", title="Annotation Workspace")
async def annotation_page(client: Client) -> None:
    """Annotation workspace page.

    Query params:
        workspace_id: UUID of existing workspace to load
    """
    # Get workspace_id from query params if present
    workspace_id = client.request.query_params.get("workspace_id")

    with ui.column().classes("w-full max-w-4xl mx-auto p-4"):
        ui.label("Annotation Workspace").classes("text-2xl font-bold mb-4")

        if workspace_id:
            # Show workspace view
            ui.label(f"Workspace: {workspace_id}").classes("text-gray-600")
            ui.label("Workspace content will appear here...")
        else:
            # Show create workspace form
            ui.label("No workspace selected. Create a new one:").classes("mb-2")
            ui.button("Create Workspace", on_click=lambda: ui.notify("TODO: implement"))
```

**Step 4: Register route in main.py**

Add import to `src/promptgrimoire/main.py` after line 20 (with other page imports):

```python
from promptgrimoire.pages import annotation  # noqa: F401
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/e2e/test_annotation_page.py::TestAnnotationPageBasic -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/promptgrimoire/pages/annotation.py src/promptgrimoire/main.py tests/e2e/test_annotation_page.py
git commit -m "feat(pages): add basic /annotation page route

- Page loads at /annotation
- Shows create workspace button when no workspace_id
- Accepts workspace_id query param for direct linking"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Implement workspace creation flow

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`
- Modify: `tests/e2e/test_annotation_page.py`

**Step 1: Write the failing E2E test**

Add to `tests/e2e/test_annotation_page.py`:

```python
import os
from uuid import UUID

import pytest

# Skip if no database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


class TestWorkspaceCreation:
    """Tests for workspace creation flow."""

    @pytestmark_db
    def test_create_workspace_redirects_with_id(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Creating workspace redirects to URL with workspace_id."""
        page.goto(f"{live_server}/annotation")

        # Click create button
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()

        # Wait for redirect
        page.wait_for_url(re.compile(r"workspace_id="))

        # Verify URL contains valid UUID
        url = page.url
        assert "workspace_id=" in url
        workspace_id = url.split("workspace_id=")[1].split("&")[0]
        UUID(workspace_id)  # Validates it's a valid UUID

    @pytestmark_db
    def test_workspace_persists_in_database(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Created workspace exists in database."""
        import asyncio
        from promptgrimoire.db.workspaces import get_workspace

        page.goto(f"{live_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        # Extract workspace_id
        url = page.url
        workspace_id = UUID(url.split("workspace_id=")[1].split("&")[0])

        # Verify in database
        workspace = asyncio.get_event_loop().run_until_complete(
            get_workspace(workspace_id)
        )
        assert workspace is not None
```

**Step 2: Add fixture for test user**

Add to `tests/e2e/conftest.py`:

```python
import os
from uuid import uuid4

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def db_test_user():
    """Create a test user for database tests.

    Uses pytest-asyncio for Python 3.14 compatibility.
    """
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL not set")

    from promptgrimoire.db.users import create_user

    user = await create_user(
        email=f"e2e-test-{uuid4().hex[:8]}@example.com",
        display_name="E2E Test User",
    )
    return {"id": user.id, "email": user.email}
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/e2e/test_annotation_page.py::TestWorkspaceCreation -v`
Expected: FAIL - create button doesn't actually create workspace

**Step 4: Write minimal implementation**

Update `src/promptgrimoire/pages/annotation.py`:

```python
"""Annotation page with workspace model support.

This page provides the new workspace-based annotation flow:
1. User creates or enters a workspace
2. User pastes/uploads content to create WorkspaceDocument
3. User annotates document with highlights
4. All state persists via workspace CRDT
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from nicegui import app, ui

from promptgrimoire.pages import page_route

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)


async def _create_workspace_and_redirect() -> None:
    """Create a new workspace and redirect to it."""
    from promptgrimoire.db.workspaces import create_workspace

    # For now, use a placeholder user ID
    # TODO: Get actual user from session once auth is integrated
    placeholder_user_id = uuid4()

    try:
        workspace = await create_workspace(created_by=placeholder_user_id)
        ui.navigate.to(f"/annotation?workspace_id={workspace.id}")
    except Exception as e:
        logger.exception("Failed to create workspace")
        ui.notify(f"Failed to create workspace: {e}", type="negative")


@page_route("/annotation", title="Annotation Workspace")
async def annotation_page(client: Client) -> None:
    """Annotation workspace page.

    Query params:
        workspace_id: UUID of existing workspace to load
    """
    workspace_id_str = client.request.query_params.get("workspace_id")
    workspace_id: UUID | None = None

    if workspace_id_str:
        try:
            workspace_id = UUID(workspace_id_str)
        except ValueError:
            ui.notify("Invalid workspace ID", type="negative")

    with ui.column().classes("w-full max-w-4xl mx-auto p-4"):
        ui.label("Annotation Workspace").classes("text-2xl font-bold mb-4")

        if workspace_id:
            await _render_workspace_view(workspace_id)
        else:
            _render_create_workspace_view()


def _render_create_workspace_view() -> None:
    """Render the create workspace UI."""
    ui.label("No workspace selected. Create a new one:").classes("mb-2")
    ui.button(
        "Create Workspace",
        on_click=_create_workspace_and_redirect,
    ).classes("bg-blue-500 text-white")


async def _render_workspace_view(workspace_id: UUID) -> None:
    """Render the workspace content view."""
    from promptgrimoire.db.workspaces import get_workspace

    workspace = await get_workspace(workspace_id)

    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")
    ui.label("Add content to annotate:").classes("mt-4")
    # Document addition will be added in Task 3
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/e2e/test_annotation_page.py::TestWorkspaceCreation -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/promptgrimoire/pages/annotation.py tests/e2e/test_annotation_page.py tests/e2e/conftest.py
git commit -m "feat(pages): implement workspace creation flow

- Create Workspace button creates DB record
- Redirects to /annotation?workspace_id=<uuid>
- Shows workspace view when ID in URL
- Shows error if workspace not found"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
## Task 3: Implement paste content → WorkspaceDocument flow

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`
- Modify: `tests/e2e/test_annotation_page.py`

**Step 1: Write the failing E2E test**

Add to `tests/e2e/test_annotation_page.py`:

```python
class TestDocumentCreation:
    """Tests for adding documents to workspace."""

    @pytestmark_db
    def test_paste_content_creates_document(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Pasting content creates a WorkspaceDocument."""
        # Create workspace first
        page.goto(f"{live_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        # Find textarea/input for content
        content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
        expect(content_input).to_be_visible()

        # Paste content
        test_content = "This is my test document content for annotation."
        content_input.fill(test_content)

        # Submit
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

        # Content should appear in the page
        page.wait_for_selector("text=" + test_content[:20])
        expect(page.locator(f"text={test_content[:20]}")).to_be_visible()

    @pytestmark_db
    def test_document_has_word_spans(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Document content is wrapped in word-level spans."""
        page.goto(f"{live_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        # Add content
        content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
        content_input.fill("Hello world test")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

        # Wait for content to render
        page.wait_for_selector("[data-word-index]")

        # Check word spans exist
        word_spans = page.locator("[data-word-index]")
        expect(word_spans.first).to_be_visible()
        assert word_spans.count() >= 3  # At least "Hello", "world", "test"

    @pytestmark_db
    def test_document_persists_after_reload(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Document content survives page reload."""
        page.goto(f"{live_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        # Save the URL for reload
        workspace_url = page.url

        # Add content
        test_content = "Persistent document content here"
        content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
        content_input.fill(test_content)
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

        # Wait for content
        page.wait_for_selector(f"text={test_content[:20]}")

        # Reload page
        page.goto(workspace_url)

        # Content should still be there
        expect(page.locator(f"text={test_content[:20]}")).to_be_visible()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/e2e/test_annotation_page.py::TestDocumentCreation -v`
Expected: FAIL - no content input field

**Step 3: Write minimal implementation**

Add to `src/promptgrimoire/pages/annotation.py`:

```python
from promptgrimoire.db.workspace_documents import add_document, list_documents


def _process_text_to_word_spans(text: str) -> str:
    """Convert plain text to HTML with word-level spans.

    Each word gets a span with data-word-index attribute for annotation targeting.
    """
    import html

    lines = text.split("\n")
    html_parts = []
    word_index = 0

    for line_num, line in enumerate(lines):
        if line.strip():
            words = line.split()
            line_spans = []
            for word in words:
                escaped = html.escape(word)
                span = f'<span class="word" data-word-index="{word_index}">{escaped}</span>'
                line_spans.append(span)
                word_index += 1
            html_parts.append(f'<p data-para="{line_num}">{" ".join(line_spans)}</p>')
        else:
            html_parts.append(f'<p data-para="{line_num}">&nbsp;</p>')

    return "\n".join(html_parts)


async def _add_document_to_workspace(
    workspace_id: UUID,
    content: str,
    document_container: ui.element,
) -> None:
    """Add a document to the workspace and render it."""
    # Create WorkspaceDocument
    html_content = _process_text_to_word_spans(content)
    doc = await add_document(
        workspace_id=workspace_id,
        type="source",
        content=html_content,
        raw_content=content,
        title=None,
    )

    # Re-render document area
    document_container.clear()
    with document_container:
        _render_document(doc.id, html_content)


def _render_document(doc_id: UUID, html_content: str) -> None:
    """Render a document with its HTML content."""
    with ui.element("div").classes("document-content border p-4 rounded bg-white"):
        ui.html(html_content).classes("prose")


async def _render_workspace_view(workspace_id: UUID) -> None:
    """Render the workspace content view."""
    from promptgrimoire.db.workspaces import get_workspace

    workspace = await get_workspace(workspace_id)

    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")

    # Load existing documents
    documents = await list_documents(workspace_id)

    # Document container (for live updates)
    document_container = ui.element("div").classes("w-full mt-4")

    if documents:
        # Render existing documents
        with document_container:
            for doc in documents:
                _render_document(doc.id, doc.content)
    else:
        # Show add content form
        ui.label("Add content to annotate:").classes("mt-4 font-semibold")

        content_input = ui.textarea(
            placeholder="Paste or type your content here..."
        ).classes("w-full min-h-32")

        async def handle_add():
            if content_input.value and content_input.value.strip():
                await _add_document_to_workspace(
                    workspace_id, content_input.value.strip(), document_container
                )
                content_input.value = ""
                content_input.visible = False

        ui.button("Add Document", on_click=handle_add).classes(
            "bg-green-500 text-white mt-2"
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/e2e/test_annotation_page.py::TestDocumentCreation -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/promptgrimoire/pages/annotation.py tests/e2e/test_annotation_page.py
git commit -m "feat(pages): implement paste content -> WorkspaceDocument

- Textarea for pasting content
- Converts text to word-level spans with data-word-index
- Persists as WorkspaceDocument in database
- Renders document after creation
- Documents survive page reload"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: Wire up annotation UI with workspace CRDT

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`
- Modify: `tests/e2e/test_annotation_page.py`

**Step 1: Write the failing E2E test**

Add to `tests/e2e/test_annotation_page.py`:

```python
class TestHighlightCreation:
    """Tests for creating highlights on documents."""

    @pytestmark_db
    def test_select_text_shows_highlight_menu(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Selecting text shows highlight creation menu."""
        # Setup workspace with document
        page.goto(f"{live_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
        content_input.fill("Select some words here to highlight them")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Select words by clicking and dragging
        first_word = page.locator("[data-word-index='0']")
        third_word = page.locator("[data-word-index='2']")

        first_word.scroll_into_view_if_needed()
        first_box = first_word.bounding_box()
        third_box = third_word.bounding_box()

        # Drag select
        page.mouse.move(first_box["x"] + 5, first_box["y"] + 5)
        page.mouse.down()
        page.mouse.move(third_box["x"] + third_box["width"] - 5, third_box["y"] + 5)
        page.mouse.up()

        # Should show highlight menu/card
        highlight_menu = page.locator("[data-testid='highlight-menu']")
        expect(highlight_menu).to_be_visible(timeout=5000)

    @pytestmark_db
    def test_create_highlight_applies_styling(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Creating a highlight applies visual styling."""
        # Setup
        page.goto(f"{live_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
        content_input.fill("Highlight this text please")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Select and highlight
        first_word = page.locator("[data-word-index='0']")
        second_word = page.locator("[data-word-index='1']")

        first_word.scroll_into_view_if_needed()
        first_box = first_word.bounding_box()
        second_box = second_word.bounding_box()

        page.mouse.move(first_box["x"] + 5, first_box["y"] + 5)
        page.mouse.down()
        page.mouse.move(second_box["x"] + second_box["width"] - 5, second_box["y"] + 5)
        page.mouse.up()

        # Click create highlight button
        page.get_by_role("button", name=re.compile("highlight|create", re.IGNORECASE)).click()

        # Words should have highlight class
        expect(first_word).to_have_class(re.compile("highlighted"))

    @pytestmark_db
    def test_highlight_persists_after_reload(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Highlights survive page reload via CRDT persistence."""
        # Setup
        page.goto(f"{live_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))
        workspace_url = page.url

        content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
        content_input.fill("Test highlight persistence")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Create highlight
        first_word = page.locator("[data-word-index='0']")
        second_word = page.locator("[data-word-index='1']")

        first_word.scroll_into_view_if_needed()
        first_box = first_word.bounding_box()
        second_box = second_word.bounding_box()

        page.mouse.move(first_box["x"] + 5, first_box["y"] + 5)
        page.mouse.down()
        page.mouse.move(second_box["x"] + second_box["width"] - 5, second_box["y"] + 5)
        page.mouse.up()

        page.get_by_role("button", name=re.compile("highlight|create", re.IGNORECASE)).click()

        # Wait for highlight to be applied
        expect(first_word).to_have_class(re.compile("highlighted"))

        # Wait for "Saved" indicator (observable state, not arbitrary timeout)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload
        page.goto(workspace_url)
        page.wait_for_selector("[data-word-index]")

        # Highlight should still be there
        first_word = page.locator("[data-word-index='0']")
        expect(first_word).to_have_class(re.compile("highlighted"))
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/e2e/test_annotation_page.py::TestHighlightCreation -v`
Expected: FAIL - no highlight functionality yet

**Step 3: Write minimal implementation**

This requires significant changes to `annotation.py`. Add highlight selection handling, CRDT integration, and CSS rendering.

Add to `src/promptgrimoire/pages/annotation.py` (complete rewrite of the render functions):

```python
"""Annotation page with workspace model support.

This page provides the new workspace-based annotation flow:
1. User creates or enters a workspace
2. User pastes/uploads content to create WorkspaceDocument
3. User annotates document with highlights
4. All state persists via workspace CRDT
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from nicegui import ui

from promptgrimoire.pages import page_route

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)


@dataclass
class PageState:
    """Per-page state for annotation."""

    workspace_id: UUID | None = None
    document_id: UUID | None = None
    selection_start: int | None = None
    selection_end: int | None = None
    user_name: str = "Anonymous"


def _process_text_to_word_spans(text: str) -> str:
    """Convert plain text to HTML with word-level spans."""
    lines = text.split("\n")
    html_parts = []
    word_index = 0

    for line_num, line in enumerate(lines):
        if line.strip():
            words = line.split()
            line_spans = []
            for word in words:
                escaped = html.escape(word)
                span = f'<span class="word" data-word-index="{word_index}">{escaped}</span>'
                line_spans.append(span)
                word_index += 1
            html_parts.append(f'<p data-para="{line_num}">{" ".join(line_spans)}</p>')
        else:
            html_parts.append(f'<p data-para="{line_num}">&nbsp;</p>')

    return "\n".join(html_parts)


def _build_highlight_css(highlights: list[dict]) -> str:
    """Generate CSS for highlighting words."""
    css_rules = []
    for hl in highlights:
        start = hl.get("start_word", 0)
        end = hl.get("end_word", 0)
        for i in range(start, end):
            css_rules.append(
                f'[data-word-index="{i}"] {{ '
                f"background-color: rgba(255, 235, 59, 0.5); "
                f"}}"
            )
    return "\n".join(css_rules)


async def _create_workspace_and_redirect() -> None:
    """Create a new workspace and redirect to it."""
    from promptgrimoire.db.workspaces import create_workspace

    placeholder_user_id = uuid4()  # TODO: Get from session

    try:
        workspace = await create_workspace(created_by=placeholder_user_id)
        ui.navigate.to(f"/annotation?workspace_id={workspace.id}")
    except Exception as e:
        logger.exception("Failed to create workspace")
        ui.notify(f"Failed to create workspace: {e}", type="negative")


async def _add_highlight(
    state: PageState,
    doc: "AnnotationDocument",
    highlights_container: ui.element,
    style_element: ui.element,
    save_status: ui.label,
) -> None:
    """Add a highlight from current selection."""
    if state.selection_start is None or state.selection_end is None:
        ui.notify("No selection", type="warning")
        return

    if state.document_id is None:
        ui.notify("No document", type="warning")
        return

    from promptgrimoire.crdt.persistence import get_persistence_manager

    # Update status to show saving
    save_status.text = "Saving..."

    # Add highlight to CRDT
    doc.add_highlight(
        start_word=state.selection_start,
        end_word=state.selection_end + 1,  # end_word is exclusive
        tag="highlight",
        text="",  # Could extract from DOM if needed
        author=state.user_name,
        document_id=str(state.document_id),
    )

    # Schedule persistence with callback to update status
    pm = get_persistence_manager()
    pm.mark_dirty_workspace(state.workspace_id, doc.doc_id, last_editor=state.user_name)

    # Force immediate save for test observability (removes debounce delay in tests)
    await pm.force_persist_workspace(state.workspace_id)
    save_status.text = "Saved"

    # Update CSS
    highlights = doc.get_highlights_for_document(str(state.document_id))
    css = _build_highlight_css(highlights)
    style_element.content = f"<style>{css}</style>"

    # Clear selection
    state.selection_start = None
    state.selection_end = None
    highlights_container.visible = False


async def _render_workspace_view(workspace_id: UUID) -> None:
    """Render the workspace content view."""
    from promptgrimoire.crdt.annotation_doc import AnnotationDocumentRegistry
    from promptgrimoire.db.workspace_documents import add_document, list_documents
    from promptgrimoire.db.workspaces import get_workspace

    workspace = await get_workspace(workspace_id)

    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return

    state = PageState(workspace_id=workspace_id)

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")

    # Save status indicator (for E2E test observability)
    save_status = ui.label("").classes("text-sm text-gray-500").props('data-testid="save-status"')

    # Load CRDT document
    registry = AnnotationDocumentRegistry()
    crdt_doc = await registry.get_or_create_for_workspace(workspace_id)

    # Style element for dynamic highlights
    style_el = ui.html("").classes("highlight-styles")

    # Load existing documents
    documents = await list_documents(workspace_id)

    if documents:
        doc = documents[0]  # For now, just first document
        state.document_id = doc.id

        # Load existing highlights
        highlights = crdt_doc.get_highlights_for_document(str(doc.id))
        css = _build_highlight_css(highlights)
        style_el.content = f"<style>{css}</style>"

        # Highlight creation menu (hidden by default)
        with ui.card().classes("absolute z-50 shadow-lg").props(
            'data-testid="highlight-menu"'
        ) as highlight_menu:
            highlight_menu.visible = False
            ui.button(
                "Highlight",
                on_click=lambda: _add_highlight(state, crdt_doc, highlight_menu, style_el, save_status),
            ).classes("bg-yellow-400")

        # Document content
        with ui.element("div").classes("document-content border p-4 rounded bg-white mt-4"):
            content_div = ui.html(doc.content).classes("prose selection:bg-blue-200")

            # Selection handling via JavaScript
            ui.run_javascript(
                f"""
                const container = document.querySelector('.document-content .prose');
                container.addEventListener('mouseup', () => {{
                    const selection = window.getSelection();
                    if (selection.rangeCount > 0 && !selection.isCollapsed) {{
                        const range = selection.getRangeAt(0);
                        const startEl = range.startContainer.parentElement.closest('[data-word-index]');
                        const endEl = range.endContainer.parentElement.closest('[data-word-index]');
                        if (startEl && endEl) {{
                            const start = parseInt(startEl.dataset.wordIndex);
                            const end = parseInt(endEl.dataset.wordIndex);
                            window.emitEvent('selection_made', {{start: Math.min(start, end), end: Math.max(start, end)}});
                        }}
                    }}
                }});
                """
            )

        # Handle selection events
        async def on_selection(e):
            state.selection_start = e.args["start"]
            state.selection_end = e.args["end"]
            highlight_menu.visible = True

        ui.on("selection_made", on_selection)

    else:
        # Show add content form
        ui.label("Add content to annotate:").classes("mt-4 font-semibold")

        content_input = ui.textarea(
            placeholder="Paste or type your content here..."
        ).classes("w-full min-h-32")

        document_container = ui.element("div").classes("w-full mt-4")

        async def handle_add():
            if content_input.value and content_input.value.strip():
                html_content = _process_text_to_word_spans(content_input.value.strip())
                doc = await add_document(
                    workspace_id=workspace_id,
                    type="source",
                    content=html_content,
                    raw_content=content_input.value.strip(),
                    title=None,
                )
                # Reload page to show document
                ui.navigate.to(f"/annotation?workspace_id={workspace_id}")

        ui.button("Add Document", on_click=handle_add).classes(
            "bg-green-500 text-white mt-2"
        )


@page_route("/annotation", title="Annotation Workspace")
async def annotation_page(client: Client) -> None:
    """Annotation workspace page."""
    workspace_id_str = client.request.query_params.get("workspace_id")
    workspace_id: UUID | None = None

    if workspace_id_str:
        try:
            workspace_id = UUID(workspace_id_str)
        except ValueError:
            ui.notify("Invalid workspace ID", type="negative")

    # Add highlighted word class
    ui.add_css(
        """
        .word.highlighted, [data-word-index].highlighted {
            background-color: rgba(255, 235, 59, 0.5) !important;
        }
        """
    )

    with ui.column().classes("w-full max-w-4xl mx-auto p-4"):
        ui.label("Annotation Workspace").classes("text-2xl font-bold mb-4")

        if workspace_id:
            await _render_workspace_view(workspace_id)
        else:
            ui.label("No workspace selected. Create a new one:").classes("mb-2")
            ui.button(
                "Create Workspace",
                on_click=_create_workspace_and_redirect,
            ).classes("bg-blue-500 text-white")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/e2e/test_annotation_page.py::TestHighlightCreation -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/promptgrimoire/pages/annotation.py tests/e2e/test_annotation_page.py
git commit -m "feat(pages): implement highlight creation with workspace CRDT

- Text selection shows highlight menu
- Create highlight stores in CRDT with document_id
- CSS dynamically updated to show highlights
- CRDT persistence via workspace-aware PersistenceManager
- Highlights survive page reload"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
## Task 5: Full E2E acceptance test

**Files:**
- Modify: `tests/e2e/test_annotation_page.py`

**Purpose:** Complete workflow test that matches the UAT statement.

**Step 1: Write the comprehensive E2E test**

Add to `tests/e2e/test_annotation_page.py`:

```python
class TestFullAnnotationWorkflow:
    """Complete workflow E2E tests matching UAT statement."""

    @pytestmark_db
    def test_complete_annotation_workflow(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """
        UAT: User creates workspace, pastes content, creates highlight,
        and highlight persists after reload.
        """
        # 1. Navigate to /annotation
        page.goto(f"{live_server}/annotation")
        expect(page.locator("body")).to_be_visible()

        # 2. Create a new workspace
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))
        workspace_url = page.url

        # 3. Paste text content
        test_content = "This is a legal document about tort law. The defendant was negligent."
        content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
        expect(content_input).to_be_visible()
        content_input.fill(test_content)

        # Submit content
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()

        # Wait for word spans to appear
        page.wait_for_selector("[data-word-index]")

        # 4. Select text and create a highlight
        # Select "tort law" (words at indices 6 and 7)
        word_tort = page.locator("[data-word-index='6']")
        word_law = page.locator("[data-word-index='7']")

        word_tort.scroll_into_view_if_needed()
        tort_box = word_tort.bounding_box()
        law_box = word_law.bounding_box()

        page.mouse.move(tort_box["x"] + 5, tort_box["y"] + 5)
        page.mouse.down()
        page.mouse.move(law_box["x"] + law_box["width"] - 5, law_box["y"] + 5)
        page.mouse.up()

        # Wait for highlight menu
        highlight_menu = page.locator("[data-testid='highlight-menu']")
        expect(highlight_menu).to_be_visible(timeout=5000)

        # Create highlight
        page.get_by_role("button", name=re.compile("highlight", re.IGNORECASE)).click()

        # Verify highlight is applied
        expect(word_tort).to_have_class(re.compile("highlighted"))

        # 5. Wait for "Saved" indicator (observable state, not arbitrary timeout)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # 6. Reload the page
        page.goto(workspace_url)

        # Wait for page to fully load
        page.wait_for_selector("[data-word-index]")

        # 7. Assert: highlight is still visible
        word_tort_after_reload = page.locator("[data-word-index='6']")
        expect(word_tort_after_reload).to_have_class(re.compile("highlighted"))

    @pytestmark_db
    def test_multiple_highlights_persist(
        self, page: Page, live_server: str, db_test_user: dict
    ) -> None:
        """Multiple highlights on same document all persist."""
        page.goto(f"{live_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))
        workspace_url = page.url

        # Add content
        content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
        content_input.fill("First highlight here. Second highlight there. Third highlight everywhere.")
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-word-index]")

        # Create first highlight (words 0-1: "First highlight")
        def create_highlight(start_idx: int, end_idx: int):
            start_word = page.locator(f"[data-word-index='{start_idx}']")
            end_word = page.locator(f"[data-word-index='{end_idx}']")

            start_word.scroll_into_view_if_needed()
            start_box = start_word.bounding_box()
            end_box = end_word.bounding_box()

            page.mouse.move(start_box["x"] + 5, start_box["y"] + 5)
            page.mouse.down()
            page.mouse.move(end_box["x"] + end_box["width"] - 5, end_box["y"] + 5)
            page.mouse.up()

            page.locator("[data-testid='highlight-menu']").wait_for(state="visible")
            page.get_by_role("button", name=re.compile("highlight", re.IGNORECASE)).click()
            page.wait_for_timeout(500)  # Let CSS update

        create_highlight(0, 1)  # "First highlight"
        create_highlight(3, 4)  # "Second highlight"
        create_highlight(6, 7)  # "Third highlight"

        # Wait for "Saved" indicator (observable state)
        saved_indicator = page.locator("[data-testid='save-status']")
        expect(saved_indicator).to_contain_text("Saved", timeout=10000)

        # Reload
        page.goto(workspace_url)
        page.wait_for_selector("[data-word-index]")

        # All three highlights should be visible
        for idx in [0, 1, 3, 4, 6, 7]:
            word = page.locator(f"[data-word-index='{idx}']")
            expect(word).to_have_class(re.compile("highlighted"))
```

**Step 2: Run all E2E tests**

Run: `uv run pytest tests/e2e/test_annotation_page.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/e2e/test_annotation_page.py
git commit -m "test: add full annotation workflow E2E tests

- Complete UAT workflow: create, paste, highlight, reload, verify
- Multiple highlights persistence test
- Validates Phase 3 acceptance criteria"
```
<!-- END_TASK_5 -->

---

## Phase 3 Verification

Run all Phase 3 tests:

```bash
uv run pytest tests/e2e/test_annotation_page.py -v
```

Expected: All tests pass

Also verify previous phases still pass:

```bash
uv run pytest tests/unit/test_workspace*.py tests/unit/test_highlight_document_id.py tests/integration/test_workspace*.py -v
```

---

## UAT Checklist

- [ ] `/annotation` page loads (Task 1)
- [ ] Create Workspace button creates DB record and redirects (Task 2)
- [ ] Paste content creates WorkspaceDocument with word spans (Task 3)
- [ ] Text selection shows highlight menu (Task 4)
- [ ] Creating highlight applies visual styling (Task 4)
- [ ] Highlights persist after reload via CRDT (Task 4)
- [ ] Full workflow E2E test passes (Task 5)
- [ ] `/demo/live-annotation` still works (no regressions - Phase 4 will verify)

**If all tests pass:** Phase 3 complete. New `/annotation` route works with workspace model. Proceed to Phase 4.

**If E2E tests fail:** Debug highlight creation or CRDT persistence. Check browser console for JS errors.
