# Documentation Flight Rules — Phase 5: In-App Help Button

**Goal:** Add a help button to the application header that opens Algolia DocSearch (when configured) or navigates to the docs site (MkDocs fallback).

**Architecture:** Conditional help button in `_render_header()` between the flex spacer and user email. When `help_backend="algolia"`: inject DocSearch v4 CDN CSS/JS via `ui.add_head_html()`, create a hidden container div, button click triggers DocSearch modal by simulating keyboard shortcut. When `help_backend="mkdocs"`: button opens docs site URL in a new tab. When `help_enabled=False`: no button rendered. E2E test verifies button renders and is clickable in `mkdocs` mode.

**Tech Stack:** NiceGUI, Algolia DocSearch v4, Playwright (E2E), Python

**Scope:** 5 of 5 phases from original design

**Codebase verified:** 2026-03-12

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-flight-rules-230.AC5: In-app help button works
- **docs-flight-rules-230.AC5.1 Success:** Help button with `data-testid="help-btn"` renders in header on every page when `help_enabled=True`
- **docs-flight-rules-230.AC5.2 Success:** With `help_backend="algolia"`, clicking help button opens DocSearch modal overlay
- **docs-flight-rules-230.AC5.3 Success:** With `help_backend="mkdocs"`, clicking help button opens MkDocs search in a modal
- **docs-flight-rules-230.AC5.4 Success:** When `help_enabled=False`, no help button is rendered
- **docs-flight-rules-230.AC5.5 Edge:** Help button does not interfere with existing header elements (logout, menu) on narrow viewports

**Design divergence on AC5.3:** The original design says "opens MkDocs search in a modal." Research found MkDocs search cannot be embedded in NiceGUI. Revised: clicking opens the docs site URL in a new tab. The AC intent (user can access search) is preserved, just via external navigation rather than an in-app modal.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add help button to `_render_header()` in `layout.py`

**Verifies:** docs-flight-rules-230.AC5.1, docs-flight-rules-230.AC5.2, docs-flight-rules-230.AC5.3, docs-flight-rules-230.AC5.4, docs-flight-rules-230.AC5.5

**Files:**
- Modify: `src/promptgrimoire/pages/layout.py` (lines 128-139, `_render_header()`)

**Context:**

Read these files before starting:
- `src/promptgrimoire/pages/layout.py` — `_render_header()` at lines 128-139, `get_settings()` import at line 13
- `src/promptgrimoire/config.py` — `HelpConfig` sub-model from Phase 4 (access via `get_settings().help`)

**Implementation:**

The current `_render_header()` (lines 128-139):
```python
def _render_header(title: str, user: dict | None) -> ui.button:
    with ui.header().classes("bg-primary items-center q-py-xs"):
        menu_btn = ui.button(icon="menu").props("flat color=white")
        ui.label(title).classes("text-h6 text-white q-ml-sm")
        ui.element("div").classes("flex-grow")
        if user:
            ui.label(user.get("email", "")).classes("text-white text-body2 q-mr-md")
            ui.button(icon="logout", on_click=lambda: ui.navigate.to("/logout")).props(
                "flat color=white"
            ).tooltip("Logout")
    return menu_btn
```

Insert the help button **after the flex-grow spacer** (after line 133) and **before the user email conditional** (line 134):

```python
def _render_header(title: str, user: dict | None) -> ui.button:
    with ui.header().classes("bg-primary items-center q-py-xs"):
        menu_btn = ui.button(icon="menu").props("flat color=white")
        ui.label(title).classes("text-h6 text-white q-ml-sm")
        ui.element("div").classes("flex-grow")
        _render_help_button()
        if user:
            ui.label(user.get("email", "")).classes("text-white text-body2 q-mr-md")
            ui.button(icon="logout", on_click=lambda: ui.navigate.to("/logout")).props(
                "flat color=white"
            ).tooltip("Logout")
    return menu_btn
```

Create the `_render_help_button()` function (before `_render_header()`):

```python
def _render_help_button() -> None:
    """Render help button in header if help is enabled.

    With ``help_backend="algolia"``, injects DocSearch CDN assets and
    opens the DocSearch modal on click. With ``help_backend="mkdocs"``,
    opens the docs site in a new tab.
    """
    help_config = get_settings().help
    if not help_config.help_enabled:
        return

    if help_config.help_backend == "algolia":
        _render_algolia_help(help_config)
    else:
        _render_mkdocs_help()
```

**Algolia backend:**

```python
def _render_algolia_help(help_config: HelpConfig) -> None:
    """Render help button that opens DocSearch modal."""
    # Inject DocSearch CSS and JS from CDN
    ui.add_head_html(
        '<link rel="stylesheet" '
        'href="https://cdn.jsdelivr.net/npm/@docsearch/css@4" />'
    )
    ui.add_head_html(
        '<script src="https://cdn.jsdelivr.net/npm/@docsearch/js@4">'
        "</script>"
    )

    # Create hidden container for DocSearch to mount into
    ui.html('<div id="docsearch-container" style="display:none"></div>')

    # Initialise DocSearch — it mounts a search button (hidden) and
    # listens for Cmd+K / Ctrl+K keyboard shortcuts
    ui.add_head_html(f"""<script>
    document.addEventListener('DOMContentLoaded', function() {{
        if (typeof docsearch !== 'undefined') {{
            docsearch({{
                container: '#docsearch-container',
                appId: '{help_config.algolia_app_id}',
                indexName: '{help_config.algolia_index_name}',
                apiKey: '{help_config.algolia_search_api_key}',
            }});
        }}
    }});
    </script>""")

    # Help button triggers DocSearch modal via keyboard event simulation
    ui.button(
        icon="help_outline",
        on_click=lambda: ui.run_javascript(
            "document.dispatchEvent("
            "new KeyboardEvent('keydown', "
            "{key: 'k', metaKey: true, ctrlKey: true}))"
        ),
    ).props(
        'flat color=white data-testid="help-btn"'
    ).tooltip("Search help")
```

Note: DocSearch v4 listens for Cmd+K (macOS) and Ctrl+K (Windows/Linux) by default. Dispatching a synthetic `keydown` event with both `metaKey: true` and `ctrlKey: true` ensures the modal opens on all platforms. This is the recommended workaround for programmatic opening without the React composable API.

**MkDocs backend:**

```python
def _render_mkdocs_help() -> None:
    """Render help button that opens docs site in new tab."""
    docs_url = get_settings().app.base_url.rstrip("/") + "/docs/"

    ui.button(
        icon="help_outline",
        on_click=lambda: ui.navigate.to(docs_url, new_tab=True),
    ).props(
        'flat color=white data-testid="help-btn"'
    ).tooltip("Help documentation")
```

Note: The docs URL is constructed from the app's base URL. If the docs site is hosted at a different URL, this can be made configurable in `HelpConfig` later. For now, convention-based URL is sufficient.

**Import:** `HelpConfig` is used as a runtime type annotation in the `_render_algolia_help(help_config: HelpConfig)` function parameter, so it must be a real import (not `TYPE_CHECKING`). Add alongside the existing `get_settings` import at the top of `layout.py`:
```python
from promptgrimoire.config import HelpConfig, get_settings
```

If `get_settings` is already imported separately, add `HelpConfig` to that import line. Alternatively, if the file uses `from __future__ import annotations`, a `TYPE_CHECKING` guard would work — check the file's existing import style.

**AC5.5 (narrow viewport):** The help button uses `icon="help_outline"` with `flat color=white` — same dimensions as the logout button. No additional responsive CSS needed. Both icon buttons are fixed-width (~40px) and fit in headers down to ~320px viewport width.

**Verification:**
```bash
uvx ty check src/promptgrimoire/pages/layout.py
# Expected: no errors

uv run ruff check src/promptgrimoire/pages/layout.py
# Expected: no errors

uv run complexipy src/promptgrimoire/pages/layout.py
# Expected: no functions > 15
```

**Commit:** `feat: add help button to application header (#281)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit test for help button rendering logic

**Verifies:** docs-flight-rules-230.AC5.1, docs-flight-rules-230.AC5.2 (routing only), docs-flight-rules-230.AC5.4

**Files:**
- Create: `tests/unit/test_help_button.py` (unit)

**Context:**

Read `src/promptgrimoire/pages/layout.py` — the `_render_help_button()` function from Task 1.

**Implementation:**

Unit tests for the conditional rendering logic. These test that `_render_help_button()` calls the right code path based on config, not that NiceGUI actually renders HTML (that's E2E territory).

**Testing:**

Tests must verify:
- docs-flight-rules-230.AC5.1: When `help_enabled=True`, help button rendering function is called
- docs-flight-rules-230.AC5.2 (routing): When `help_backend="algolia"`, the `_render_algolia_help()` path is called (verifies routing, not modal opening — modal opening requires live DocSearch CDN and valid Algolia credentials, which is UAT-only)
- docs-flight-rules-230.AC5.4: When `help_enabled=False`, no help button rendering occurs

Test structure:
- Mock `get_settings()` to return controlled `HelpConfig` instances
- Verify that with `help_enabled=False`, the function returns early without creating UI elements
- Verify that with `help_enabled=True` and `help_backend="algolia"`, the Algolia rendering path is called
- Verify that with `help_enabled=True` and `help_backend="mkdocs"`, the MkDocs rendering path is called

**AC5.2 coverage note:** Full verification of AC5.2 (clicking help button opens DocSearch modal) requires valid Algolia credentials and CDN access. This cannot be automated without standing up a real Algolia index. The unit test verifies the routing logic reaches `_render_algolia_help()`. Full AC5.2 verification is deferred to UAT (see UAT checklist below).

**Verification:**
```bash
uv run pytest tests/unit/test_help_button.py -v
# Expected: all tests pass

uvx ty check tests/unit/test_help_button.py
# Expected: no errors

uv run ruff check tests/unit/test_help_button.py
# Expected: no errors

uv run complexipy tests/unit/test_help_button.py
# Expected: no functions > 15
```

**Commit:** `test: add help button unit tests (#281)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: E2E test for help button

**Verifies:** docs-flight-rules-230.AC5.1, docs-flight-rules-230.AC5.3, docs-flight-rules-230.AC5.4

**Files:**
- Create: `tests/e2e/test_help_button.py` (e2e)

**Context:**

Read these files before starting:
- `tests/e2e/conftest.py` — E2E fixtures, server lifecycle, authentication helpers
- `src/promptgrimoire/pages/layout.py` — help button rendering from Task 1
- Any existing E2E test file for header/layout patterns

**Implementation:**

E2E test that verifies the help button renders and is clickable. Test in `mkdocs` mode (does not require Algolia credentials).

The E2E test server runs with `DEV__AUTH_MOCK=true`. The help button config can be controlled via environment variables:
- `HELP__HELP_ENABLED=true`
- `HELP__HELP_BACKEND=mkdocs`

**Testing:**

Tests must verify:
- docs-flight-rules-230.AC5.1: `page.get_by_test_id("help-btn")` is visible when `help_enabled=True`
- docs-flight-rules-230.AC5.3: Clicking the help button in `mkdocs` mode triggers navigation (new tab opens or page transitions to docs URL)
- docs-flight-rules-230.AC5.4: `page.get_by_test_id("help-btn")` is NOT visible when `help_enabled=False`

Test the `mkdocs` backend (does not require Algolia credentials):

```python
@pytest.mark.e2e
class TestHelpButton:
    def test_help_button_visible_when_enabled(self, page, base_url):
        """Help button renders when help_enabled=True."""
        # Navigate to any authenticated page
        page.goto(f"{base_url}/")
        help_btn = page.get_by_test_id("help-btn")
        help_btn.wait_for(state="visible", timeout=10000)

    def test_help_button_hidden_when_disabled(self, page, base_url):
        """Help button does not render when help_enabled=False."""
        page.goto(f"{base_url}/")
        expect(page.get_by_test_id("help-btn")).not_to_be_visible()
```

Note: The `help_enabled` state needs to be controllable at test time. If the E2E server's env vars are fixed, this test may need to check only one state. Alternatively, use the `HELP__HELP_ENABLED` env var in the test server configuration.

Check how the E2E conftest.py starts the server and whether env vars can be parametrised per test. If not, test only the enabled state (since the default is disabled, it will be tested implicitly by all other E2E tests).

**Verification:**
```bash
uv run grimoire e2e run -k test_help_button
# Expected: all tests pass

uvx ty check tests/e2e/test_help_button.py
# Expected: no errors

uv run ruff check tests/e2e/test_help_button.py
# Expected: no errors

uv run complexipy tests/e2e/test_help_button.py
# Expected: no functions > 15
```

**UAT Steps (Phase 5 — after Tasks 1-3 complete):**
1. [ ] Start the app: `HELP__HELP_ENABLED=true HELP__HELP_BACKEND=mkdocs uv run run.py`
2. [ ] Log in and verify a help button (question mark icon) appears in the header between the spacer and user email
3. [ ] Click the help button — verify a new tab opens to the docs site URL
4. [ ] Resize the browser to a narrow viewport (~320px) — verify help button and logout button both remain visible and don't overlap
5. [ ] Restart with `HELP__HELP_ENABLED=false` — verify no help button appears
6. [ ] **(AC5.2 — requires Algolia credentials):** Set `HELP__HELP_BACKEND=algolia` with valid `HELP__ALGOLIA_APP_ID`, `HELP__ALGOLIA_SEARCH_API_KEY`, `HELP__ALGOLIA_INDEX_NAME` — click help button and verify DocSearch modal opens
7. [ ] Run `uv run pytest tests/unit/test_help_button.py -v` — all pass
8. [ ] Run `uv run grimoire e2e run -k test_help_button` — all pass

**Commit:** `test: add E2E test for help button (#281)`
<!-- END_TASK_3 -->
