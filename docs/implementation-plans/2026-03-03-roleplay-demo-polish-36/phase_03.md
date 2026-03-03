# Roleplay Demo Polish — Phase 3: Export to Workspace

**Goal:** Add "Export to Workspace" button that converts roleplay session to an annotatable workspace document

**Architecture:** New export function converts in-memory `Session.turns` to HTML with `data-speaker`/`data-speaker-name` marker divs (sibling structure, not wrapping). Creates loose workspace, adds single `ai_conversation` document, grants owner ACL, navigates to annotation page.

**Design deviation (justified):** The design places the export function inline in `roleplay.py`. This plan creates a separate `roleplay_export.py` module because `session_to_html()` is a pure function with no side effects — separating it enables direct unit testing without mocking NiceGUI UI context. This is a testability improvement consistent with the project's functional-core-imperative-shell pattern.

**Tech Stack:** `markdown` library (transitive dep, v3.10.2), `db/workspaces.py`, `db/workspace_documents.py`, `db/acl.py`

**Scope:** 3 phases from original design (phase 3 of 3)

**Codebase verified:** 2026-03-03

**Testing reference:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/roleplay-36/docs/testing.md`

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-demo-polish-36.AC3: Export creates annotatable workspace
- **roleplay-demo-polish-36.AC3.1 Success:** Clicking "Export to Workspace" creates a loose workspace with a single `ai_conversation` document containing all turns
- **roleplay-demo-polish-36.AC3.2 Success:** Each turn in the exported document has correct `data-speaker` ("user"/"assistant") and `data-speaker-name` (actual character/user names) attributes
- **roleplay-demo-polish-36.AC3.3 Success:** Exported workspace opens in annotation page with speaker labels rendered via CSS `::before`
- **roleplay-demo-polish-36.AC3.4 Failure:** Export button is disabled or hidden when no session is active (no character loaded)

---

<!-- START_TASK_1 -->
### Task 1: Verify markdown library availability

**Verifies:** None (infrastructure pre-check)

**Step 1: Confirm markdown is importable**

```bash
uv run python -c "import markdown; print(f'markdown {markdown.__version__}')"
```

Expected: `markdown 3.10.2` (or similar version — confirms transitive dependency is available).

If this fails, add as direct dependency: `uv add markdown`

**No commit needed** — this is a pre-check for Task 2.
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->
<!-- START_TASK_2 -->
### Task 2: Write failing unit tests for session_to_html (TDD: Red)

**Verifies:** roleplay-demo-polish-36.AC3.2

**Files:**
- Create: `tests/unit/test_roleplay_export.py`

**Testing:**

Write tests first (TDD). Tests must verify:
- roleplay-demo-polish-36.AC3.2: Output contains `data-speaker="user"` and `data-speaker-name="{user_name}"` for user turns
- roleplay-demo-polish-36.AC3.2: Output contains `data-speaker="assistant"` and `data-speaker-name="{char_name}"` for AI turns
- Markdown formatting is converted to HTML (e.g., `*italics*` becomes `<em>italics</em>`)
- Marker divs are siblings to content, not wrapping it (marker div is self-closing/empty, followed by rendered HTML)
- Multiple turns produce alternating marker/content blocks
- Empty session produces empty string

Create test fixtures using `Session` and `Turn` dataclasses from `promptgrimoire.models.scenario`:

```python
from promptgrimoire.models import Character, Session

# Create a minimal Character for testing
character = Character(name="Becky Bennett", description="Test character")

# Create Session with test turns
session = Session(character=character, user_name="Jane")
session.add_turn("Hello Becky", is_user=True)
session.add_turn("*shifts uncomfortably* Hi there", is_user=False)
```

Test the output HTML contains the expected `data-speaker` attributes and that the structure is correct (marker div as sibling, not parent).

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_export.py -v`
Expected: Tests FAIL (module does not exist yet — TDD Red step)

**Commit:** `test: add failing tests for session-to-HTML export (TDD red)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement session_to_html to pass tests (TDD: Green)

**Verifies:** roleplay-demo-polish-36.AC3.2

**Files:**
- Create: `src/promptgrimoire/pages/roleplay_export.py`

**Implementation:**

Create a pure function `session_to_html(session: Session) -> str` in a new module `roleplay_export.py`:

1. Import `markdown`
2. For each `Turn` in `session.turns`:
   - Determine role: `"user"` if `turn.is_user`, `"system"` if `turn.is_system`, else `"assistant"`
   - Determine speaker name: `session.user_name` if user, `session.character.name` otherwise
   - Render `turn.content` (markdown) to HTML via `markdown.markdown(turn.content)`
   - Prepend an **empty sibling** marker div: `<div data-speaker="{role}" data-speaker-name="{name}"></div>`
   - The rendered HTML follows as a sibling, NOT wrapped inside the marker div
3. Concatenate all turns and return the full HTML string

The marker div structure must match the existing pattern from `export/platforms/__init__.py:166`:
```html
<div data-speaker="user" data-speaker-name="Jane"></div>
<p>I'd like to ask about what happened.</p>

<div data-speaker="assistant" data-speaker-name="Becky Bennett"></div>
<p><em>shifts uncomfortably</em> Well, it started about three months ago...</p>
```

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_export.py -v`
Expected: All tests now PASS (TDD Green)

**Commit:** `feat: add session-to-HTML conversion for workspace export`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Write integration test for workspace creation from session

**Verifies:** roleplay-demo-polish-36.AC3.1

**Files:**
- Create: `tests/integration/test_roleplay_workspace_export.py`

**Testing:**

Integration test that verifies the full export flow with a real database:
- roleplay-demo-polish-36.AC3.1: Creates a workspace with a single `ai_conversation` document containing all turns

The test should:
1. Create a `Session` with known turns
2. Convert to HTML via `session_to_html()`
3. Call `create_workspace()` to create a loose workspace
4. Call `add_document()` with `type="ai_conversation"`, the HTML content, and a title
5. Call `grant_permission(workspace.id, test_user_id, "owner")`
6. Verify the workspace exists and has one document of the correct type
7. Verify document content contains the expected `data-speaker` markers
8. Verify ACL entry exists with `"owner"` permission for the test user

Requires `db_session` fixture and `TEST_DATABASE_URL` skip guard (follow pattern from `tests/integration/conftest.py`).

**Verification:**

Run: `uv run pytest tests/integration/test_roleplay_workspace_export.py -v` (requires TEST_DATABASE_URL)
Expected: All tests pass

**Commit:** `test: add integration test for roleplay workspace export`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_5 -->
### Task 5: Write failing test for export button disabled state (TDD: Red)

**Verifies:** roleplay-demo-polish-36.AC3.4

**Files:**
- Modify: `tests/unit/test_roleplay_visual.py` (add new test class)

**Testing:**

Write test first (TDD). Test must verify:
- roleplay-demo-polish-36.AC3.4: Export button starts disabled when no session is active

Since this involves NiceGUI UI state, mock the button creation and verify that the initial `disabled` state is set correctly. Alternatively, test the state management logic (if the button enable/disable is driven by a state dict, test that state dict directly).

Follow the same mocking pattern used for avatar tests in the same file.

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_visual.py -v`
Expected: Test FAILS (button does not exist yet — TDD Red step)

**Commit:** `test: add failing test for export button disabled state (TDD red)`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Add Export to Workspace button and handler to roleplay page

**Verifies:** roleplay-demo-polish-36.AC3.1, roleplay-demo-polish-36.AC3.3, roleplay-demo-polish-36.AC3.4

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py` (`roleplay_page()` function)

**Implementation:**

1. Import the new export function and database operations:
   ```python
   from promptgrimoire.pages.roleplay_export import session_to_html
   from promptgrimoire.db.workspaces import create_workspace
   from promptgrimoire.db.workspace_documents import add_document
   from promptgrimoire.db.acl import grant_permission
   ```

2. Add an "Export to Workspace" button in the chat card section (alongside or below the send button row). The button should:
   - Have `data-testid="roleplay-export-btn"` for E2E testability
   - Be **disabled** initially (no session active) — satisfies AC3.4
   - Be **enabled** after a session is loaded and at least one exchange has occurred

3. Create async handler `_handle_export()`:
   - Get `auth_user` from `app.storage.user`
   - Extract `user_id = UUID(str(auth_user["user_id"]))`
   - Call `session_to_html(session)` to generate HTML
   - Call `create_workspace()` to create loose workspace
   - Set workspace title using inline `get_session()` context (no helper exists in `db/workspaces.py`):
     ```python
     from promptgrimoire.db import get_session
     from promptgrimoire.db.models import Workspace

     async with get_session() as db:
         ws = await db.get(Workspace, workspace.id)
         ws.title = f"Roleplay: {session.character.name} — {datetime.now():%Y-%m-%d}"
         await db.flush()
     ```
   - Call `add_document(workspace_id=workspace.id, type="ai_conversation", content=html, source_type="html", title=f"Roleplay: {session.character.name}")`
   - Call `grant_permission(workspace.id, user_id, "owner")`
   - Navigate to annotation page: `ui.navigate.to(f"/annotation/{workspace.id}")`
   - Show success notification before navigating

4. Enable the export button after the session is set up (in the auto-load flow from Phase 2 Task 4, and after each successful message exchange).

**Verification:**

Run: `uv run python -m promptgrimoire`, navigate to `/roleplay`, have a conversation, click Export
Expected: New workspace created, browser navigates to annotation page, conversation displays with speaker labels

**Commit:** `feat: add export-to-workspace button on roleplay page`
<!-- END_TASK_6 -->

## UAT Steps (Phase 3)

1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: `/roleplay`
3. [ ] Verify export button is disabled/hidden before conversation starts
4. [ ] Have a brief conversation (send one message, wait for response)
5. [ ] Click "Export to Workspace"
6. [ ] Verify: Browser navigates to annotation page
7. [ ] Verify: Conversation displays with speaker labels ("Jane:" / "Becky Bennett:")
8. [ ] Verify: All turns from the roleplay appear in the exported document

## Evidence Required
- [ ] Screenshot of annotation page showing exported conversation with speaker labels
- [ ] Test output showing all unit and integration tests green
