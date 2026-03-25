# Tag Deletion Guards & Import Hardening — Phase 2: UI Error Handling for Deletion Guards

**Goal:** Surface deletion guard errors as user-friendly warning notifications instead of unhandled exceptions that trigger Discord alerting.

**Architecture:** `_open_confirm_delete` gains a `BusinessLogicError` catch before its generic `Exception` catch, logging at WARNING level and showing amber notifications. `_do_delete_document` gains a specific `HasAnnotationsError` catch following its existing `OwnershipError`/`ProtectedDocumentError` pattern.

**Tech Stack:** Python 3.14, NiceGUI (ui.notify), structlog

**Scope:** Phase 2 of 4 from original design (depends on Phase 1)

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-deletion-guards-413.AC1: Tag group deletion blocked when group has tags
- **tag-deletion-guards-413.AC1.3 Failure:** UI shows warning notification naming the tag count when deletion is blocked

### tag-deletion-guards-413.AC2: Tag deletion blocked when tag has highlights
- **tag-deletion-guards-413.AC2.3 Failure:** UI shows warning notification naming the highlight count when deletion is blocked

### tag-deletion-guards-413.AC3: Document deletion blocked when document has annotations
- **tag-deletion-guards-413.AC3.3 Failure:** UI shows warning notification naming the annotation count when deletion is blocked

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add BusinessLogicError catch to _open_confirm_delete

**Verifies:** tag-deletion-guards-413.AC1.3, tag-deletion-guards-413.AC2.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tag_management_rows.py:420-431` (`_do_delete` inner function in `_open_confirm_delete`)

**Implementation:**

In `_open_confirm_delete` (line 391), the `_do_delete` inner function (line 420) currently catches `Exception` generically with `logger.exception` (ERROR level → Discord). Add a specific `BusinessLogicError` catch before the generic catch.

The `BusinessLogicError` catch should:
1. Log at WARNING level (expected business rejection, not error)
2. Show `ui.notify(str(exc), type="warning")` (amber, not red)
3. Close the dialog and return (same flow as the generic catch)

```python
async def _do_delete() -> None:
    try:
        await delete_fn()
    except BusinessLogicError as exc:
        logger.warning(
            "delete_entity_blocked",
            operation="delete_entity",
            entity_name=entity_name,
            reason=str(exc),
        )
        ui.notify(str(exc), type="warning")
        dlg.close()
        return
    except Exception as exc:
        logger.exception(
            "delete_entity_failed",
            operation="delete_entity",
            entity_name=entity_name,
        )
        ui.notify(str(exc), type="negative")
        dlg.close()
        return
    dlg.close()
    await on_confirmed(entity_name)
```

Import `BusinessLogicError` from `promptgrimoire.db.exceptions` at the top of the file.

**Testing:**

E2E tests are the natural verification here — they test that the UI shows the right notification type. However, the E2E tests for this require setup that creates tags with highlights and tag groups with tags, which is complex.

For the unit/integration lane, test that the DB-layer guards (Phase 1) raise the correct exceptions — these are already covered by Phase 1 tests. The UI handling is defence-in-depth that's best verified via E2E or manual testing.

If the project has existing E2E tests for tag deletion, extend them. Otherwise, document as requiring manual UAT verification.

Tests should verify:
- tag-deletion-guards-413.AC1.3: Delete a group with tags → amber warning notification appears with tag count text
- tag-deletion-guards-413.AC2.3: Delete a tag with highlights → amber warning notification appears with highlight count text
- Group/tag still exists after the blocked deletion (dialog closed, entity survived)

Test file: `tests/e2e/test_tag_deletion_guards.py` (new E2E test file)

**Verification:**
Run: `uv run grimoire test all`
Expected: All existing tests pass (no regressions from the catch reordering)

**Commit:** `feat(ui): catch BusinessLogicError as warning in tag deletion dialogs (#413)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add HasAnnotationsError catch to _do_delete_document

**Verifies:** tag-deletion-guards-413.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/document_management.py:308-326` (`_do_delete_document` function)

**Implementation:**

In `_do_delete_document` (line 308), after the existing `except ProtectedDocumentError` block (line 319-322), add a catch for `HasAnnotationsError`:

```python
except HasAnnotationsError as exc:
    logger.warning(
        "document_delete_blocked",
        operation="delete_document",
        document_id=str(doc.id),
        highlight_count=exc.highlight_count,
    )
    ui.notify(
        f"Cannot delete: {exc.highlight_count} "
        f"annotation{'s' if exc.highlight_count != 1 else ''} "
        "on this document",
        type="warning",
    )
    return
```

Import `HasAnnotationsError` from `promptgrimoire.db.exceptions` at the top of the file (alongside the existing `OwnershipError`, `ProtectedDocumentError` imports).

Note: This is defence-in-depth. Phase 1's `can_delete_document` update already hides the delete button when annotations exist. This catch handles the race condition where annotations are added between button render and click.

**Testing:**

Tests must verify:
- tag-deletion-guards-413.AC3.3: Calling `_do_delete_document` when document has annotations → warning notification with annotation count, no navigation redirect

This is best tested as an E2E test or integration test that sets up a document with annotations and attempts deletion. Can be included in the same `tests/e2e/test_tag_deletion_guards.py` file.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat(ui): catch HasAnnotationsError in document deletion handler (#413)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: E2E tests for deletion guard notifications

**Verifies:** tag-deletion-guards-413.AC1.3, tag-deletion-guards-413.AC2.3, tag-deletion-guards-413.AC3.3

**Files:**
- Create: `tests/e2e/test_tag_deletion_guards.py`

**Implementation:**

Create E2E tests that verify the UI shows warning notifications when deletion is blocked. Each test sets up the precondition (group with tags, tag with highlights, document with annotations) and attempts deletion via the UI.

Follow existing E2E patterns from `tests/e2e/test_tag_sync.py`:
- Use `setup_workspace_with_content` from `fixture_loaders.py` to create a workspace with content
- Use `_seed_tags_for_workspace` from `tag_helpers.py` to seed tags
- Add CRDT highlights via the UI (select text, click tag) or via sync DB seeding
- Use `data-testid` locators exclusively (never text-based)
- For notification assertions: `ui.notify()` renders framework-controlled elements without injectable `data-testid` attributes — this is a legitimate exception to the testid-only rule. Use `page.get_by_role("alert").filter(has_text="...")` since Quasar renders notifications as `role="alert"` elements

Tests:

**test_delete_group_with_tags_shows_warning:**
1. Set up workspace with seeded tags (tags have a group)
2. Open tag management dialog (`data-testid="tag-management-btn"`)
3. Click delete on a group that has tags
4. Confirm deletion in dialog
5. Assert warning notification appears containing "tag" and a count
6. Assert group still exists (not deleted)

**test_delete_tag_with_highlights_shows_warning:**
1. Set up workspace with content and seeded tags
2. Create a highlight on the content using one of the tags
3. Open tag management dialog
4. Click delete on the tag that has highlights
5. Confirm deletion in dialog
6. Assert warning notification appears containing "highlight" and a count
7. Assert tag still visible in toolbar

**test_delete_document_with_annotations_shows_warning:**
1. Set up workspace with content, add a highlight
2. Open document management (settings/documents area)
3. Click delete on the document
4. Assert warning notification appears containing "annotation" and a count
5. Assert document still present

All tests use `@pytest.mark.e2e` marker to run in the Playwright lane.

**Verification:**
Run: `uv run grimoire e2e run tests/e2e/test_tag_deletion_guards.py`
Expected: All 3 tests pass

**Commit:** `test(e2e): verify deletion guard warning notifications (#413)`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
