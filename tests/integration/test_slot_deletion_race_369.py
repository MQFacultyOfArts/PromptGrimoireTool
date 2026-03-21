"""Red tests: NiceGUI slot deletion race conditions (#369).

These tests reproduce the error patterns observed in production telemetry
(incident.db, epochs 1-13, 1006 JSONL events, 550 journal error-seconds;
plus 88 error-seconds in Mar 19-21 data).

Root cause mechanism (discovered during investigation):
    1. A dialog is created inside a container's slot context
    2. NiceGUI creates a canary element in the caller's context
       (elements/dialog.py:31)
    3. weakref.finalize on the canary calls dialog.delete() when
       canary is GC'd
    4. User clicks a button inside the dialog
    5. handle_event captures parent_slot = button's slot (inside
       dialog)
    6. The handler clears the container that holds the canary
    7. Canary is GC'd -> finaliser fires -> dialog.delete()
    8. ui.notify() -> context.client -> slot.parent -> stale weakref
    9. RuntimeError: parent element has been deleted

Source verification (NiceGUI 3.9.0):
    - elements/dialog.py:30-34  canary + weakref.finalize ->
      guarded delete
    - elements/dialog.py:51-53  close() just sets value=False,
      does NOT delete
    - slot.py:22   Slot._parent = weakref.ref(parent_element)
    - context.py:41  context.client = self.slot.parent.client
    - events.py:445,457  parent_slot captured from sender, held
      in with block

Production evidence:
    - Traceback at 2026-03-19T08:46:38Z shows
      _open_confirm_delete dialog
    - result = _open_confirm_delete.<locals>._do_delete
      (events.py:16)
    - dlg = Dialog object (tag_management_rows.py:432)
    - on_confirmed calls render_tag_list which clears the tag
      container
    - The canary was created in the tag container's slot context
"""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING

import pytest
from nicegui import ui
from nicegui.context import context

if TYPE_CHECKING:
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.nicegui_ui,
]


# ---------------------------------------------------------------------------
# Category 3: Tag management callback
# Production pattern (tag_management.py:532-535):
#   _on_tag_deleted -> refresh -> render_tag_list (clear) -> notify
#
# The dialog's canary element is in the tag list container.
# clear() destroys the canary, finaliser deletes the dialog,
# the handler's slot context (inside the dialog) goes stale.
# ---------------------------------------------------------------------------


@pytest.mark.nicegui_ui
async def test_dialog_canary_triggers_slot_deletion(
    nicegui_user: User,
) -> None:
    """Category 3: dialog canary destruction stales the event slot.

    Prediction: When the container holding the dialog's canary is
    cleared, the canary is GC'd, the dialog is deleted via
    weakref.finalize, and context.client (accessed via the dialog
    button's parent_slot) raises RuntimeError.

    Falsification: If no error, the canary finaliser does not fire
    synchronously during gc.collect(), or the dialog deletion does
    not invalidate the slot weakref.
    """
    await nicegui_user.open("/login")

    with nicegui_user:
        tag_list_container = ui.column()

        # Create a dialog INSIDE the tag_list_container's slot
        # context.  This makes the canary a child of
        # tag_list_container.
        with tag_list_container:
            ui.label("Tag 1")
            ui.label("Tag 2")
            dlg = ui.dialog()

        with dlg, ui.card():
            btn = ui.button("Delete")

    # Capture the button's parent slot (inside the dialog).
    # This is what handle_event captures at events.py:445.
    parent_slot = btn.parent_slot
    assert parent_slot is not None, "Button must have a parent slot"

    # Production pattern: events.py:457 enters `with parent_slot:`
    # BEFORE the handler runs. The handler then clears the container
    # and calls ui.notify(), all INSIDE the same `with` block.
    with parent_slot:
        # Verify context.client works before the clear
        pre_clear_client = context.client
        assert pre_clear_client is not None

        # Handler body: close dialog, then render_tag_list() clears
        # container
        dlg.close()
        tag_list_container.clear()
        gc.collect()

        # Handler body continues: ui.notify() accesses
        # context.client.  This raises RuntimeError because the
        # dialog canary mechanism stales the weakref.  The fix
        # (reorder notify before clear) avoids reaching this point.
        with pytest.raises(RuntimeError, match="parent element"):
            _ = context.client


# ---------------------------------------------------------------------------
# Category 1: Card toggle after rebuild
# Same canary mechanism but with annotation card rebuilds.
# The dialog canary lives in annotations_container.
# ---------------------------------------------------------------------------


@pytest.mark.nicegui_ui
async def test_notify_before_rebuild_succeeds(
    nicegui_user: User,
) -> None:
    """Category 3 fix: ui.notify BEFORE container.clear() is safe.

    The fix for _on_tag_deleted moves ui.notify() before
    render_tag_list(). This test verifies that accessing
    context.client before the clear succeeds, even inside the
    dialog button's slot context.
    """
    await nicegui_user.open("/login")

    with nicegui_user:
        tag_list_container = ui.column()

        with tag_list_container:
            ui.label("Tag 1")
            dlg = ui.dialog()

        with dlg, ui.card():
            btn = ui.button("Delete")

    parent_slot = btn.parent_slot
    assert parent_slot is not None

    with parent_slot:
        # ui.notify() runs here -- BEFORE the clear.  Should
        # succeed.
        client = context.client
        assert client is not None

        # Now the handler does the rebuild
        dlg.close()
        tag_list_container.clear()
        gc.collect()

        # No further context.client access after the clear.
        # The handler is done.


@pytest.mark.nicegui_ui
async def test_dialog_canary_during_card_rebuild(
    nicegui_user: User,
) -> None:
    """Category 1: dialog canary destroyed by annotations rebuild.

    Same mechanism as Category 3 but triggered by CRDT broadcast
    calling _refresh_annotation_cards() which clears the
    annotations_container. Any dialog created in that container's
    context has its canary destroyed.
    """
    await nicegui_user.open("/login")

    with nicegui_user:
        annotations_container = ui.column()

        with annotations_container:
            ui.label("Card 1")
            dlg = ui.dialog()

        with dlg, ui.card():
            toggle_btn = ui.button("Toggle")

    parent_slot = toggle_btn.parent_slot
    assert parent_slot is not None

    # Rebuild: clear the container (destroys canary)
    with parent_slot:
        annotations_container.clear()
        gc.collect()

        # Bug: raises RuntimeError because canary destruction
        # deleted the dialog, staling the slot weakref.
        with pytest.raises(RuntimeError, match="parent element"):
            _ = context.client


# ---------------------------------------------------------------------------
# Category 2: Highlight deletion
# Production: cards.py:404 -> highlights.py:172
#
# Production traceback (2026-03-16T00:08:57Z) shows:
#   1. events.py:459 await result (do_delete)
#   2. cards.py:404 await _delete_highlight(state, hid, c)
#   3. highlights.py:172 card.delete()
#   4. element.py:504 parent_slot.children.remove(element)
#   5. ValueError: list.remove(x): x not in list
#   6. During exception handling: RuntimeError (stale slot)
#
# The ValueError proves the card was already removed from its
# parent slot's children list before card.delete() ran.  The
# specific trigger is unknown (see investigation doc C2.1a).
# The RuntimeError is secondary (exception handling path).
# ---------------------------------------------------------------------------


@pytest.mark.nicegui_ui
async def test_card_delete_after_concurrent_clear(
    nicegui_user: User,
) -> None:
    """Category 2 positive border: card.delete() on pre-removed card.

    Production traceback shows ValueError: list.remove(x) at
    element.py:504, proving the card was already removed before
    card.delete() ran. This test uses container.clear() as a
    synthetic way to reproduce that state, then shows card.delete()
    raises the same ValueError. The actual production trigger is
    unknown (see investigation doc C2.1a).
    """
    await nicegui_user.open("/login")

    with nicegui_user:
        container = ui.column()

        with container:
            card = ui.card()
            with card:
                ui.button("Delete highlight")

    # Step 1: something clears the container before card.delete()
    # runs (trigger unknown — see investigation doc C2.1a).
    container.clear()
    gc.collect()

    # Step 2: the delete handler calls card.delete().
    # element.delete() -> parent_slot.parent.remove(self)
    # -> parent_slot.children.remove(element)
    # Card already removed from children -> ValueError.
    with pytest.raises(ValueError, match="not in list"):
        card.delete()


@pytest.mark.nicegui_ui
async def test_delete_highlight_survives_pre_cleared_card(
    nicegui_user: User,
) -> None:
    """Category 2 negative border: _delete_highlight completes when
    the card has already been cleared by a concurrent rebuild.

    This exercises the real ``_delete_highlight`` function, not a
    reimplementation of the guard. The test:
    1. Builds a minimal PageState with a real annotations_container
    2. Creates a card inside the container
    3. Clears the container (simulating concurrent rebuild)
    4. Calls the real ``_delete_highlight`` on the cleared card
    5. Asserts: no ValueError, annotation_cards dict is cleaned up

    Without the ``if not card.is_deleted:`` guard at
    highlights.py:176, step 4 raises ValueError at element.py:504.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.highlights import (
        _delete_highlight,
    )

    await nicegui_user.open("/login")

    workspace_id = uuid4()
    doc_id = uuid4()
    highlight_id = "test-highlight-001"

    with nicegui_user:
        container = ui.column()
        with container:
            card = ui.card()
            with card:
                ui.label("Highlight content")

    # Build a minimal PageState with the real container and card
    state = PageState(workspace_id=workspace_id)
    state.annotations_container = container
    state.annotation_cards = {highlight_id: card}
    state.highlight_style = None  # skip CSS update
    state.broadcast_update = None  # skip broadcast

    # Mock the CRDT doc so remove_highlight is a no-op
    mock_crdt = MagicMock()
    mock_crdt.doc_id = doc_id
    state.crdt_doc = mock_crdt

    # Mock the persistence manager so force_persist_workspace
    # is a no-op (we don't need real DB persistence)
    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    # Simulate the race: the card is already gone when
    # _delete_highlight reaches card.delete().  Trigger unknown
    # (see investigation doc C2.1a).
    container.clear()
    gc.collect()

    # Verify precondition: card is already deleted
    assert card.is_deleted

    # Call the real _delete_highlight — without the guard this
    # raises ValueError: list.remove(x): x not in list
    with patch(
        "promptgrimoire.pages.annotation.highlights.get_persistence_manager",
        return_value=mock_pm,
    ):
        await _delete_highlight(state, highlight_id, card)

    # Verify side effects completed:
    # 1. highlight removed from CRDT
    mock_crdt.remove_highlight.assert_called_once_with(
        highlight_id,
    )
    # 2. persistence was triggered
    mock_pm.force_persist_workspace.assert_awaited_once_with(
        workspace_id,
    )
    # 3. annotation_cards dict was cleaned up
    assert highlight_id not in state.annotation_cards


# ---------------------------------------------------------------------------
# Category 1 Part 1: Primary TimeoutError
# Production: cards.py:558 -> ui.run_javascript(
#     "requestAnimationFrame(window._positionCards)")
#
# Production tracebacks (20/20 in Mar 19-21 data) show:
#   1. TimeoutError: JavaScript did not respond within 1.0 s
#   2. handle_exception -> context.client -> stale slot -> RuntimeError
#
# Hypothesis: if window._positionCards is undefined,
# requestAnimationFrame(undefined) throws TypeError.  NiceGUI's
# runJavascript (nicegui.js:327) catches only SyntaxError, re-throws
# all others, so javascript_response is never emitted.  Server times out.
# ---------------------------------------------------------------------------


@pytest.mark.nicegui_ui
async def test_missing_js_global_causes_timeout(
    nicegui_user: User,
) -> None:
    """Category 1 Part 1: missing JS global causes TimeoutError.

    Prediction: await ui.run_javascript(
        "requestAnimationFrame(window.__definitely_missing)")
    raises TimeoutError because:
      1. requestAnimationFrame(undefined) throws TypeError in browser
      2. NiceGUI's runJavascript catches only SyntaxError, re-throws
      3. Promise rejects without emitting javascript_response
      4. Server's JavaScriptRequest times out

    Limitation: NiceGUI's test user does NOT execute JS — it uses
    pattern-matching rules (testing/user.py:93).  Unmatched JS
    always times out.  This test confirms the server-side timeout
    machinery works, but the browser-side TypeError hypothesis
    requires E2E testing with a real browser.
    """
    await nicegui_user.open("/login")

    with nicegui_user:
        container = ui.column()

    with container, pytest.raises(TimeoutError, match="JavaScript did not respond"):
        await ui.run_javascript(
            "requestAnimationFrame(window.__definitely_missing)",
            timeout=1.0,
        )


@pytest.mark.nicegui_ui
async def test_guarded_js_global_resolves_with_rule(
    nicegui_user: User,
) -> None:
    """Category 1 Part 1 negative border: guard pattern resolves.

    NiceGUI's test user doesn't execute JS, so we register a
    javascript_rule that matches the guarded pattern and returns
    None.  This verifies the server-side resolution path: when
    the browser does respond, no timeout occurs.

    The actual browser-side behaviour (if-guard short-circuits,
    eval returns undefined, response emitted) requires E2E testing.
    """
    import re

    await nicegui_user.open("/login")

    # Register a rule that matches our guarded JS and returns None
    # (simulating the browser eval returning undefined)
    nicegui_user.javascript_rules[
        re.compile(r"if \(window\.__definitely_missing\)")
    ] = lambda _: None

    with nicegui_user:
        container = ui.column()

    with container:
        result = await ui.run_javascript(
            "if (window.__definitely_missing)"
            " requestAnimationFrame(window.__definitely_missing)",
            timeout=1.0,
        )
    assert result is None


# ---------------------------------------------------------------------------
# Category 1 Part 2: Secondary RuntimeError
# Concurrent rebuild stales the old card's child element's slot weakref.
#
# Hypothesis: container.clear() + annotation_cards[hl_id] overwrite
# drops all strong references to the old card.  CPython refcount
# collection frees it, making header_row's parent_slot._parent
# weakref return None.
# ---------------------------------------------------------------------------


@pytest.mark.nicegui_ui
async def test_container_clear_plus_dict_overwrite_stales_child_slot(
    nicegui_user: User,
) -> None:
    """Category 1 Part 2: container.clear() + dict overwrite stales weakref.

    Prediction: After container.clear() removes the card from
    client.elements and slot.children, and annotation_cards[hl_id]
    is overwritten with a new card, the old card is collected by
    CPython's reference counting.  The old header_row's
    parent_slot._parent weakref returns None.

    Falsification: If the weakref is still alive after clear +
    overwrite + gc.collect(), there is a hidden strong reference
    keeping the old card alive (e.g. NiceGUI outbox, binding
    system, or event handler registry).
    """
    await nicegui_user.open("/login")

    with nicegui_user:
        container = ui.column()

        with container:
            old_card = ui.card()
            with old_card:
                header_row = ui.row()

    # Capture the header_row's parent slot (owned by old_card)
    parent_slot = header_row.parent_slot
    assert parent_slot is not None
    # Verify the weakref is alive before the clear
    assert parent_slot._parent() is not None
    # Simulate annotation_cards dict
    annotation_cards: dict[str, ui.card] = {"hl-001": old_card}

    # Step 1: container.clear() — removes old_card from
    # client.elements and slot.children
    container.clear()

    # Step 2: rebuild creates a new card and overwrites the dict
    with container:
        new_card = ui.card()
    annotation_cards["hl-001"] = new_card

    # Step 3: drop the test's local reference to old_card
    # (in production, the loop variable in _refresh_annotation_cards
    # goes out of scope when the function returns)
    del old_card

    # Step 4: force GC in case refcount didn't collect immediately
    gc.collect()

    # The old card should be collected — weakref should be stale
    assert parent_slot._parent() is None, (
        "Expected weakref to be stale after container.clear() + "
        "dict overwrite, but old card is still alive. "
        "Hidden strong reference exists."
    )
