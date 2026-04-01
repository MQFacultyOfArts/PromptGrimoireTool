from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from nicegui import ui

if TYPE_CHECKING:
    from collections.abc import Callable

# Path to the JS file — follows project convention of JS in static/
_JS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "static" / "annotation-sidebar.js"
)


class AnnotationSidebar(ui.element, component=_JS_PATH):
    """Minimal custom Vue component wrapper for annotation sidebar spike."""

    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        *,
        on_test_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__()
        self._props["items"] = items or []
        if on_test_event is not None:
            self.on("test_event", lambda e: on_test_event(e.args))

    def set_items(self, items: list[dict[str, Any]]) -> None:
        """Update the items prop and push to client."""
        self._props["items"] = items
        self.update()
