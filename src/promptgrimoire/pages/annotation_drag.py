"""Drag-and-drop infrastructure for Tab 2 (Organise) highlight cards.

Provides factory functions that wrap NiceGUI elements with HTML5 drag event
handlers. Per-client drag state is held in closure scope (no global state).
Drop events are dispatched via callbacks that the caller wires to CRDT operations.

Design decisions:
- No subclassing -- factory functions wrap existing NiceGUI elements
- Per-client drag state via DragState class -- each client gets its own instance
- Callback-based drop handling -- on_drop callback decouples from CRDT details

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_04.md Task 1
- AC: three-tab-ui.AC2.3, AC2.4
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from nicegui import ui

logger = logging.getLogger(__name__)


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
    """Add HTML5 drag attributes and events to an existing highlight card.

    Sets the card as draggable with a grab cursor, and wires dragstart
    to store the highlight ID in both the JavaScript DataTransfer object
    and the Python-side DragState.

    Args:
        card: The NiceGUI card element to make draggable.
        highlight_id: ID of the highlight this card represents.
        source_tag: The raw tag key this card belongs to (for cross-column tracking).
        drag_state: Per-client DragState instance for tracking.

    Returns:
        The card (for chaining).
    """
    card.style("cursor: grab;")
    card._props["draggable"] = "true"

    def on_dragstart() -> None:
        drag_state.set_dragged(highlight_id, source_tag=source_tag)

    card.on(
        "dragstart",
        handler=on_dragstart,
        # Use js_handler to set DataTransfer data for browser-level drag
        js_handler=f"""(e) => {{
            e.dataTransfer.setData('text/plain', '{highlight_id}');
            e.dataTransfer.effectAllowed = 'move';
            emit();
        }}""",
    )

    return card


def make_drop_column(
    column: ui.column,
    tag_name: str,
    on_drop: Callable[[str, str, str], Awaitable[None]],
    drag_state: DragState,
) -> ui.column:
    """Make a column a valid drop target for highlight cards.

    Adds dragover (with prevent default) and drop event handlers. On drop,
    reads the highlight ID from the DragState and calls the on_drop callback
    with (highlight_id, source_tag, target_tag).

    Args:
        column: The NiceGUI column element to make a drop target.
        tag_name: The raw tag key this column represents.
        on_drop: Async callback(highlight_id, source_tag, target_tag) called on drop.
        drag_state: Per-client DragState instance for reading dragged highlight.

    Returns:
        The column (for chaining).
    """
    # Prevent default to allow drop
    column.on(
        "dragover.prevent",
        js_handler="() => {}",
    )

    # Visual feedback on dragenter/dragleave
    column.on(
        "dragenter",
        js_handler="""(e) => {
            e.currentTarget.style.outline = '2px dashed #1976d2';
            e.currentTarget.style.outlineOffset = '-2px';
        }""",
    )
    column.on(
        "dragleave",
        js_handler="""(e) => {
            e.currentTarget.style.outline = '';
            e.currentTarget.style.outlineOffset = '';
        }""",
    )

    async def on_drop_handler() -> None:
        highlight_id = drag_state.get_dragged()
        source_tag = drag_state.get_source_tag()
        if highlight_id is None or source_tag is None:
            logger.warning("Drop event with no dragged highlight")
            return
        drag_state.clear()
        await on_drop(highlight_id, source_tag, tag_name)

    column.on(
        "drop",
        handler=on_drop_handler,
        js_handler="""(e) => {
            e.preventDefault();
            e.currentTarget.style.outline = '';
            e.currentTarget.style.outlineOffset = '';
            emit();
        }""",
    )

    return column
