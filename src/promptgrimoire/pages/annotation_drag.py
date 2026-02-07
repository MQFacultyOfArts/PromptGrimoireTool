"""Drag-and-drop infrastructure for Tab 2 (Organise) highlight cards.

Follows the canonical NiceGUI drag-and-drop pattern from the trello_cards
example: pure Python event handlers, .props('draggable'), and per-client
drag state. No js_handler or emit() — all events flow through NiceGUI's
normal event pipeline where .prevent modifiers work correctly.

Design decisions:
- Per-client drag state via DragState class — each client gets its own instance
- Factory functions wrap existing NiceGUI elements (no subclassing)
- Callback-based drop handling — on_drop callback decouples from CRDT details
- Visual feedback via CSS class changes (like trello_cards example)

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_04.md Task 1
- AC: three-tab-ui.AC2.3, AC2.4
- Pattern: github.com/zauberzeug/nicegui/tree/main/examples/trello_cards
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from nicegui import ui

logger = logging.getLogger(__name__)

# CSS classes for drop target visual feedback
_DROP_HIGHLIGHT_ADD = "bg-blue-grey-3"
_DROP_HIGHLIGHT_REMOVE = "bg-blue-grey-1"


class DragState:
    """Per-client drag state tracking the currently dragged highlight.

    Each client creates its own DragState instance, avoiding cross-client
    interference. The instance tracks the highlight ID being dragged and
    its source tag for cross-column drop resolution.
    """

    __slots__ = ("_dragged_id", "_source_tag")

    def __init__(self) -> None:
        self._dragged_id: str | None = None
        self._source_tag: str | None = None

    def set_dragged(self, highlight_id: str, source_tag: str | None = None) -> None:
        """Record the highlight being dragged and its source tag."""
        self._dragged_id = highlight_id
        self._source_tag = source_tag

    def get_dragged(self) -> str | None:
        """Return the currently dragged highlight ID, or None."""
        return self._dragged_id

    def get_source_tag(self) -> str | None:
        """Return the source tag of the dragged highlight, or None."""
        return self._source_tag

    def clear(self) -> None:
        """Clear drag state after a drop or cancel."""
        self._dragged_id = None
        self._source_tag = None


def create_drag_state() -> DragState:
    """Create a new per-client drag state instance.

    Returns:
        A fresh DragState with no dragged highlight.
    """
    return DragState()


def make_draggable_card(
    card: ui.card,
    highlight_id: str,
    source_tag: str,
    drag_state: DragState,
) -> ui.card:
    """Add drag attributes and events to an existing highlight card.

    Uses NiceGUI's .props('draggable') and Python-side dragstart handler,
    following the canonical trello_cards pattern. No js_handler needed —
    drag state is tracked entirely in Python via DragState.

    Args:
        card: The NiceGUI card element to make draggable.
        highlight_id: ID of the highlight this card represents.
        source_tag: The raw tag key this card belongs to.
        drag_state: Per-client DragState instance for tracking.

    Returns:
        The card (for chaining).
    """
    card.props("draggable")
    card.classes("cursor-pointer")

    def on_dragstart() -> None:
        drag_state.set_dragged(highlight_id, source_tag=source_tag)

    card.on("dragstart", on_dragstart)

    return card


def make_drop_column(
    column: ui.column,
    tag_name: str,
    on_drop: Callable[[str, str, str], Awaitable[None]],
    drag_state: DragState,
) -> ui.column:
    """Make a column a valid drop target for highlight cards.

    Uses NiceGUI's .on('dragover.prevent') to mark the column as a valid
    drop target (following the trello_cards pattern). Visual feedback is
    provided via CSS class changes on dragover/dragleave.

    Args:
        column: The NiceGUI column element to make a drop target.
        tag_name: The raw tag key this column represents.
        on_drop: Async callback(highlight_id, source_tag, target_tag).
        drag_state: Per-client DragState instance.

    Returns:
        The column (for chaining).
    """
    column.classes(_DROP_HIGHLIGHT_REMOVE)

    def highlight() -> None:
        column.classes(remove=_DROP_HIGHLIGHT_REMOVE, add=_DROP_HIGHLIGHT_ADD)

    def unhighlight() -> None:
        column.classes(remove=_DROP_HIGHLIGHT_ADD, add=_DROP_HIGHLIGHT_REMOVE)

    # dragover.prevent marks this as a valid drop target
    column.on("dragover.prevent", highlight)
    column.on("dragleave", unhighlight)

    async def on_drop_handler() -> None:
        unhighlight()
        highlight_id = drag_state.get_dragged()
        source_tag = drag_state.get_source_tag()
        if highlight_id is None or source_tag is None:
            logger.warning("Drop event with no dragged highlight")
            return
        drag_state.clear()
        await on_drop(highlight_id, source_tag, tag_name)

    column.on("drop", on_drop_handler)

    return column
