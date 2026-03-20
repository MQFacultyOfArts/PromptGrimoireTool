"""Red tests: NiceGUI slot deletion race conditions (#369).

These tests reproduce the error patterns observed in production telemetry
(incident.db, epochs 1-13, 1006 JSONL events, 550 journal error-seconds).

Root cause mechanism (discovered during investigation):
    1. A dialog is created inside a container's slot context
    2. NiceGUI creates a canary element in the caller's context (dialog.py:31)
    3. weakref.finalize on the canary calls dialog.delete() when canary is GC'd
    4. User clicks a button inside the dialog
    5. handle_event captures parent_slot = button's slot (inside dialog)
    6. The handler clears the container that holds the canary
    7. Canary is GC'd -> finaliser fires -> dialog.delete()
    8. ui.notify() -> context.client -> slot.parent -> stale weakref
    9. RuntimeError: parent element has been deleted

Source verification (NiceGUI 3.8.0):
    - dialog.py:30-35  canary element + weakref.finalize -> self.delete()
    - dialog.py:51-53  close() just sets value=False, does NOT delete
    - slot.py:22       Slot._parent = weakref.ref(parent_element)
    - context.py:41    context.client = self.slot.parent.client
    - events.py:440,452  parent_slot captured from sender, held in with block

Production evidence:
    - Traceback at 2026-03-19T08:46:38Z shows _open_confirm_delete dialog
    - result = _open_confirm_delete.<locals>._do_delete (events.py:16)
    - dlg = Dialog object (tag_management_rows.py:432)
    - on_confirmed calls render_tag_list which clears the tag container
    - The canary was created in the tag container's slot context
"""

from __future__ import annotations

import gc

import pytest
from nicegui import ui
from nicegui.context import context

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
async def test_dialog_canary_triggers_slot_deletion():
    """Category 3: dialog canary destruction stales the event slot.

    Prediction: When the container holding the dialog's canary is
    cleared, the canary is GC'd, the dialog is deleted via
    weakref.finalize, and context.client (accessed via the dialog
    button's parent_slot) raises RuntimeError.

    Falsification: If no error, the canary finaliser does not fire
    synchronously during gc.collect(), or the dialog deletion does
    not invalidate the slot weakref.
    """
    tag_list_container = ui.column()

    # Create a dialog INSIDE the tag_list_container's slot context.
    # This makes the canary a child of tag_list_container.
    with tag_list_container:
        ui.label("Tag 1")
        ui.label("Tag 2")
        dlg = ui.dialog()

    with dlg, ui.card():
        btn = ui.button("Delete")

    # Capture the button's parent slot (inside the dialog).
    # This is what handle_event captures at events.py:440.
    parent_slot = btn.parent_slot
    assert parent_slot is not None, "Button must have a parent slot"

    # Production pattern: events.py:452 enters `with parent_slot:`
    # BEFORE the handler runs. The handler then clears the container
    # and calls ui.notify(), all INSIDE the same `with` block.
    with parent_slot:
        # Verify context.client works before the clear
        pre_clear_client = context.client
        assert pre_clear_client is not None

        # Handler body: close dialog, then render_tag_list() clears container
        dlg.close()
        tag_list_container.clear()  # Destroys canary -> finaliser -> dlg.delete()
        gc.collect()

        # Handler body continues: ui.notify() accesses context.client.
        # This SHOULD succeed without error. Currently it raises
        # RuntimeError because the dialog canary mechanism stales
        # the weakref. This test fails (RuntimeError) until the bug
        # is fixed.
        _ = context.client  # Bug: raises RuntimeError here


# ---------------------------------------------------------------------------
# Category 1: Card toggle after rebuild
# Same canary mechanism but with annotation card rebuilds.
# The dialog canary lives in annotations_container.
# ---------------------------------------------------------------------------


@pytest.mark.nicegui_ui
async def test_notify_before_rebuild_succeeds():
    """Category 3 fix: ui.notify BEFORE container.clear() is safe.

    The fix for _on_tag_deleted moves ui.notify() before
    render_tag_list(). This test verifies that accessing
    context.client before the clear succeeds, even inside the
    dialog button's slot context.
    """
    tag_list_container = ui.column()

    with tag_list_container:
        ui.label("Tag 1")
        dlg = ui.dialog()

    with dlg, ui.card():
        btn = ui.button("Delete")

    parent_slot = btn.parent_slot
    assert parent_slot is not None

    with parent_slot:
        # ui.notify() runs here -- BEFORE the clear. Should succeed.
        client = context.client
        assert client is not None

        # Now the handler does the rebuild
        dlg.close()
        tag_list_container.clear()
        gc.collect()

        # No further context.client access after the clear.
        # The handler is done.


@pytest.mark.nicegui_ui
async def test_dialog_canary_during_card_rebuild():
    """Category 1: dialog canary destroyed by annotations rebuild.

    Same mechanism as Category 3 but triggered by CRDT broadcast
    calling _refresh_annotation_cards() which clears the
    annotations_container. Any dialog created in that container's
    context has its canary destroyed.
    """
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

        # Bug: raises RuntimeError here because canary destruction
        # deleted the dialog, staling the slot weakref.
        _ = context.client


# ---------------------------------------------------------------------------
# Category 2: Highlight deletion
# Production: cards.py:404 -> highlights.py:172
#
# Production traceback (2026-03-16T00:08:57Z) shows:
#   1. events.py:454 await result (do_delete)
#   2. cards.py:404 await _delete_highlight(state, hid, c)
#   3. highlights.py:172 card.delete()
#   4. element.py:504 parent_slot.children.remove(element)
#   5. ValueError: list.remove(x): x not in list
#   6. During exception handling: RuntimeError (stale slot)
#
# The ValueError proves container.clear() ran BEFORE card.delete(),
# removing the card from its parent slot's children list. Then
# card.delete() fails at list.remove() because the card is gone.
# The RuntimeError is secondary (exception handling path).
# ---------------------------------------------------------------------------


@pytest.mark.nicegui_ui
async def test_card_delete_after_concurrent_clear():
    """Category 2: card.delete() after concurrent container.clear().

    Production traceback shows ValueError: list.remove(x) at
    element.py:504, proving container.clear() already removed the
    card before card.delete() ran. This test reproduces that
    specific race: clear the container first, then card.delete().
    """
    container = ui.column()

    with container:
        card = ui.card()
        with card:
            ui.button("Delete highlight")

    # Step 1: concurrent CRDT broadcast clears the container.
    container.clear()
    gc.collect()

    # Step 2: the delete handler calls card.delete().
    # element.delete() -> parent_slot.parent.remove(self)
    # -> parent_slot.children.remove(element)
    # Card already removed from children -> ValueError.
    with pytest.raises(ValueError, match="not in list"):
        card.delete()
