from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from nicegui import ui

if TYPE_CHECKING:
    from collections.abc import Callable

    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.tags import TagInfo

logger = structlog.get_logger()

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
        doc_container_id: str = "",
        on_toggle_expand: Callable[[dict[str, Any]], Any] | None = None,
        on_change_tag: Callable[[dict[str, Any]], Any] | None = None,
        on_submit_comment: Callable[[dict[str, Any]], Any] | None = None,
        on_delete_comment: Callable[[dict[str, Any]], Any] | None = None,
        on_delete_highlight: Callable[[dict[str, Any]], Any] | None = None,
        on_edit_para_ref: Callable[[dict[str, Any]], Any] | None = None,
        on_locate_highlight: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        super().__init__()
        self._props["items"] = items or []
        self._props["tag_options"] = tag_options or {}
        self._props["permissions"] = permissions or {}
        self._props["expanded_ids"] = expanded_ids or []
        self._props["doc_container_id"] = doc_container_id
        _event_map: dict[str, Callable[[dict[str, Any]], Any] | None] = {
            "toggle_expand": on_toggle_expand,
            "change_tag": on_change_tag,
            "submit_comment": on_submit_comment,
            "delete_comment": on_delete_comment,
            "delete_highlight": on_delete_highlight,
            "edit_para_ref": on_edit_para_ref,
            "locate_highlight": on_locate_highlight,
        }
        for event_name, handler in _event_map.items():
            if handler is not None:
                self.on(event_name, lambda e, h=handler: h(e.args))

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

    def refresh_from_state(self, state: PageState) -> None:
        """Refresh sidebar from PageState: serialise, push props, bump epoch.

        Extracts highlights from the CRDT doc, serialises them via
        ``items_serialise.serialise_items``, pushes all props, increments
        The Vue component's watch on ``items`` increments the client-side
        fire-and-forget ``ui.run_javascript()``.
        """
        if state.crdt_doc is None:
            return

        _t0 = time.monotonic()

        # Extract highlights for the current document
        if state.document_id is not None:
            highlights = state.crdt_doc.get_highlights_for_document(
                str(state.document_id),
            )
        else:
            highlights = state.crdt_doc.get_all_highlights()

        # Build tag info map from tag_info_list
        tag_info_map: dict[str, TagInfo] = {}
        for ti in state.tag_info_list or []:
            tag_info_map[ti.raw_key] = ti

        # Set expanded_ids before refresh_items so a single update()
        # pushes all props together.
        self._props["expanded_ids"] = list(state.expanded_cards)

        self.refresh_items(
            highlights=highlights,
            tag_info_map=tag_info_map,
            tag_colours=state.tag_colours(),
            user_id=state.user_id,
            viewer_is_privileged=state.viewer_is_privileged,
            privileged_user_ids=state.privileged_user_ids,
            can_annotate=state.can_annotate,
            anonymous_sharing=state.is_anonymous,
        )

        # Epoch increment is handled by the Vue watch on items
        # (annotationsidebar.js, flush: 'post') — no Python-side push needed.

        _elapsed = round((time.monotonic() - _t0) * 1000, 1)
        logger.info(
            "vue_sidebar_refresh",
            trigger="refresh_from_state",
            elapsed_ms=_elapsed,
            highlight_count=len(highlights),
            cards_epoch="vue-managed",
            document_id=str(state.document_id),
        )
