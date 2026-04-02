from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from nicegui import ui

if TYPE_CHECKING:
    from collections.abc import Callable

    from promptgrimoire.pages.annotation.tags import TagInfo

# Path to the JS file — follows project convention of JS in static/
_JS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "static" / "annotationsidebar.js"
)


class AnnotationSidebar(ui.element, component=_JS_PATH):
    """Custom Vue component wrapper for annotation sidebar."""

    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        *,
        tag_options: dict[str, str] | None = None,
        permissions: dict[str, bool] | None = None,
        expanded_ids: list[str] | None = None,
        on_test_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__()
        self._props["items"] = items or []
        self._props["tag_options"] = tag_options or {}
        self._props["permissions"] = permissions or {}
        self._props["expanded_ids"] = expanded_ids or []
        if on_test_event is not None:
            self.on("test_event", lambda e: on_test_event(e.args))

    def set_items(self, items: list[dict[str, Any]]) -> None:
        """Update the items prop and push to client."""
        self._props["items"] = items
        self.update()

    def refresh_items(
        self,
        highlights: list[dict[str, Any]],
        tag_info_map: dict[str, TagInfo],
        tag_colours: dict[str, str],
        user_id: str | None,
        viewer_is_privileged: bool,
        privileged_user_ids: frozenset[str],
        can_annotate: bool,
        anonymous_sharing: bool,
    ) -> None:
        """Serialise highlights and push items + metadata as props."""
        from promptgrimoire.pages.annotation.items_serialise import serialise_items  # noqa: PLC0415, I001 -- lazy: items_serialise imports card_shared which may re-enter annotation package

        items = serialise_items(
            highlights=highlights,
            tag_info_map=tag_info_map,
            tag_colours=tag_colours,
            user_id=user_id,
            viewer_is_privileged=viewer_is_privileged,
            privileged_user_ids=privileged_user_ids,
            can_annotate=can_annotate,
            anonymous_sharing=anonymous_sharing,
        )
        self._props["items"] = items
        tag_opts = {k: v.name for k, v in tag_info_map.items()}
        self._props["tag_options"] = tag_opts
        self._props["permissions"] = {"can_annotate": can_annotate}
        self.update()
