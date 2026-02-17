# HTML Input Pipeline - Phase 4: Content Type Dialog

**Goal:** Create an awaitable content type confirmation dialog for the input pipeline.

**Architecture:** New `pages/dialogs.py` module with `show_content_type_dialog()` that uses NiceGUI's awaitable dialog pattern.

**Tech Stack:** NiceGUI (`ui.dialog`, `ui.select`, `ui.button`)

**Scope:** Phase 4 of 8 from original design

**Codebase verified:** 2026-02-05

---

## Codebase Verification Findings

| Assumption | Result | Actual |
|------------|--------|--------|
| `pages/dialogs.py` exists | ✗ Doesn't exist | Must be created |
| NiceGUI dialog patterns | ✓ Confirmed | `ui.dialog()` is awaitable with `dialog.submit(value)` |
| Existing select patterns | ✓ Confirmed | `ui.select(options, value=...).props("dense")` |
| Existing button patterns | ✓ Confirmed | `.props("flat dense")`, `.props("color=primary")` |

**NiceGUI dialog API (from Context7):**
```python
with ui.dialog() as dialog, ui.card():
    ui.label('Content')
    ui.button('OK', on_click=lambda: dialog.submit('result'))

result = await dialog  # Returns submitted value or None if cancelled
```

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Create pages/dialogs.py with show_content_type_dialog()

**Files:**
- Create: `src/promptgrimoire/pages/dialogs.py`

**Step 1: Create the dialogs module**

Write to `src/promptgrimoire/pages/dialogs.py`:

```python
"""Reusable dialog components for NiceGUI pages."""

from __future__ import annotations

from nicegui import events, ui

from promptgrimoire.input_pipeline.html_input import CONTENT_TYPES, ContentType


async def show_content_type_dialog(
    detected_type: ContentType,
    preview: str = "",
) -> ContentType | None:
    """Show awaitable modal to confirm or override detected content type.

    Args:
        detected_type: The auto-detected content type to show as default.
        preview: Optional preview of the content (first ~200 chars).

    Returns:
        Selected content type, or None if cancelled.

    Usage:
        detected = detect_content_type(content)
        confirmed = await show_content_type_dialog(detected, preview=content[:200])
        if confirmed is None:
            return  # User cancelled
        # Use confirmed type
    """
    # Build options dict for select
    type_options = {t: t.upper() for t in CONTENT_TYPES}

    selected_type: ContentType = detected_type

    def on_type_change(e: events.ValueChangeEventArguments) -> None:
        nonlocal selected_type
        selected_type = e.value

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Confirm Content Type").classes("text-lg font-bold mb-2")

        if preview:
            with ui.expansion("Preview", icon="visibility").classes("w-full mb-4"):
                ui.label(preview[:500]).classes("text-xs text-gray-600 whitespace-pre-wrap font-mono")

        ui.label("Detected type:").classes("text-sm text-gray-600")
        ui.select(
            options=type_options,
            value=detected_type,
            on_change=on_type_change,
            label="Content Type",
        ).props("dense outlined").classes("w-full mb-4")

        ui.label(
            "Override if detection is incorrect. "
            "HTML preserves formatting; Text treats content as plain text."
        ).classes("text-xs text-gray-500 mb-4")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button(
                "Confirm",
                on_click=lambda: dialog.submit(selected_type),
            ).props("color=primary")

    dialog.open()
    result = await dialog
    return result
```

**Step 2: Verify module compiles**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.pages.dialogs import show_content_type_dialog; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add dialog exports to pages __init__.py

**Files:**
- Modify: `src/promptgrimoire/pages/__init__.py`

**Step 1: Check current __init__.py content**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && cat src/promptgrimoire/pages/__init__.py
```

**Step 2: Add dialogs import if not present**

If `__init__.py` is empty or doesn't export dialogs, add:

```python
"""NiceGUI page modules."""

from promptgrimoire.pages.dialogs import show_content_type_dialog

__all__ = ["show_content_type_dialog"]
```

If it already has exports, append to the existing imports and `__all__` list.

**Step 3: Verify import works**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.pages import show_content_type_dialog; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write tests and commit

**Files:**
- Create: `tests/unit/pages/__init__.py`
- Create: `tests/unit/pages/test_dialogs.py`

**Step 1: Create test directory**

Run:
```bash
mkdir -p /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline/tests/unit/pages
touch /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline/tests/unit/pages/__init__.py
```

**Step 2: Write unit tests**

Write to `tests/unit/pages/test_dialogs.py`:

```python
"""Tests for dialog components.

Note: Full dialog interaction tests require E2E testing with Playwright.
These unit tests verify the module structure and imports.
"""

import pytest


class TestContentTypeDialog:
    """Tests for show_content_type_dialog module structure."""

    def test_import_function(self) -> None:
        """Function can be imported."""
        from promptgrimoire.pages.dialogs import show_content_type_dialog

        assert callable(show_content_type_dialog)

    def test_import_from_pages(self) -> None:
        """Function can be imported from pages package."""
        from promptgrimoire.pages import show_content_type_dialog

        assert callable(show_content_type_dialog)

    def test_function_is_async(self) -> None:
        """Function is an async function."""
        import asyncio

        from promptgrimoire.pages.dialogs import show_content_type_dialog

        assert asyncio.iscoroutinefunction(show_content_type_dialog)

    def test_accepts_required_params(self) -> None:
        """Function signature accepts required parameters."""
        import inspect

        from promptgrimoire.pages.dialogs import show_content_type_dialog

        sig = inspect.signature(show_content_type_dialog)
        params = list(sig.parameters.keys())

        assert "detected_type" in params
        assert "preview" in params
```

**Step 3: Run tests**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/pages/test_dialogs.py -v
```

Expected: All tests pass

**Step 4: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && git add src/promptgrimoire/pages/dialogs.py src/promptgrimoire/pages/__init__.py tests/unit/pages/ && git commit -m "feat(ui): add content type confirmation dialog

- Create pages/dialogs.py with show_content_type_dialog()
- Awaitable dialog using NiceGUI ui.dialog pattern
- Shows detected type with option to override
- Preview expansion shows content snippet
- Returns selected type or None if cancelled

Part of #106 HTML input pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 4 Completion Criteria

- [ ] `src/promptgrimoire/pages/dialogs.py` created
- [ ] `show_content_type_dialog()` is async and awaitable
- [ ] Dialog shows detected type with override dropdown
- [ ] Dialog has Cancel (returns None) and Confirm (returns type) buttons
- [ ] Module exports added to `pages/__init__.py`
- [ ] Unit tests pass
- [ ] Changes committed

## Technical Notes

### NiceGUI Awaitable Dialog Pattern

```python
with ui.dialog() as dialog, ui.card():
    # Dialog content
    ui.button('OK', on_click=lambda: dialog.submit('result'))

dialog.open()  # Open the dialog
result = await dialog  # Wait for submit() or cancel
# result is submitted value, or None if cancelled (ESC or background click)
```

### Integration Point

Phase 5 will integrate this dialog into the annotation page's paste/upload flow:

```python
detected = detect_content_type(pasted_html)
confirmed = await show_content_type_dialog(detected, preview=pasted_html[:200])
if confirmed is None:
    return  # User cancelled
processed = await process_input(pasted_html, source_type=confirmed)
```
