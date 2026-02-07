"""Drag-and-drop infrastructure for Tab 2 (Organise) highlight cards.

Uses NiceGUI's element.move() for visual card relocation on drop, following
the recommended pattern from github.com/zauberzeug/nicegui/discussions/932.
Never uses panel.clear() — elements are moved in place.

Design decisions:
- Per-client drag state via DragState — tracks highlight ID, source tag, AND
  the card element itself (needed for element.move())
- Factory functions wrap existing NiceGUI elements
- On drop: move card element first (instant visual), then fire callback for
  CRDT persistence — never clear + rebuild
- dragover.prevent throttled to prevent 60/sec event flood

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_04.md Task 1
- AC: three-tab-ui.AC2.3, AC2.4
- Pattern: github.com/zauberzeug/nicegui/discussions/932
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from nicegui import ui

logger = logging.getLogger(__name__)


class DragState:
    """Per-client drag state tracking the currently dragged highlight.

    Each client creates its own DragState instance, avoiding cross-client
    interference. Tracks highlight ID, source tag, AND the card element
    so the drop handler can call card.move() for instant visual relocation.
    """

    __slots__ = ("_dragged_card", "_dragged_id", "_source_tag")

    def __init__(self) -> None:
        self._dragged_id: str | None = None
        self._source_tag: str | None = None
        self._dragged_card: Any | None = None  # ui.card at runtime

    def set_dragged(
        self,
        highlight_id: str,
        source_tag: str | None = None,
        card: Any | None = None,
    ) -> None:
        """Record the highlight being dragged, its source tag, and card element."""
        self._dragged_id = highlight_id
        self._source_tag = source_tag
        self._dragged_card = card

    def get_dragged(self) -> str | None:
        """Return the currently dragged highlight ID, or None."""
        return self._dragged_id

    def get_source_tag(self) -> str | None:
        """Return the source tag of the dragged highlight, or None."""
        return self._source_tag

    def get_dragged_card(self) -> Any | None:
        """Return the card element being dragged, or None."""
        return self._dragged_card

    def clear(self) -> None:
        """Clear drag state after a drop or cancel."""
        self._dragged_id = None
        self._source_tag = None
        self._dragged_card = None


def create_drag_state() -> DragState:
    """Create a new per-client drag state instance."""
    return DragState()


def make_draggable_card(
    card: ui.card,
    highlight_id: str,
    source_tag: str,
    drag_state: DragState,
) -> ui.card:
    """Add drag attributes and events to an existing highlight card.

    Stores the card element in DragState on dragstart so the drop handler
    can call card.move() for instant visual relocation.

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
        drag_state.set_dragged(highlight_id, source_tag=source_tag, card=card)

    card.on("dragstart", on_dragstart)

    return card


def make_drop_column(
    column: ui.column,
    tag_name: str,
    on_drop: Callable[[str, str, str], Awaitable[None]],
    drag_state: DragState,
) -> ui.column:
    """Make a column a valid drop target for highlight cards.

    On drop, moves the card element to this column using element.move()
    (instant visual update), then fires the on_drop callback for CRDT
    persistence. Never clears or rebuilds the panel.

    Args:
        column: The NiceGUI column element to make a drop target.
        tag_name: The raw tag key this column represents.
        on_drop: Async callback(highlight_id, source_tag, target_tag).
        drag_state: Per-client DragState instance.

    Returns:
        The column (for chaining).
    """
    # dragover.prevent marks as valid drop target.
    # Throttle — we only need preventDefault(), not the handler.
    column.on("dragover.prevent", lambda: None, throttle=0.05)

    async def on_drop_handler() -> None:
        highlight_id = drag_state.get_dragged()
        source_tag = drag_state.get_source_tag()
        dragged_card = drag_state.get_dragged_card()
        if highlight_id is None or source_tag is None:
            logger.warning("Drop event with no dragged highlight")
            return
        logger.info(
            "Drop: highlight=%s from=%s to=%s", highlight_id, source_tag, tag_name
        )
        drag_state.clear()

        # Move card element to this column (instant visual update)
        if dragged_card is not None:
            dragged_card.move(target_container=column)

        # Persist via CRDT callback
        await on_drop(highlight_id, source_tag, tag_name)

    column.on("drop", on_drop_handler)

    return column
