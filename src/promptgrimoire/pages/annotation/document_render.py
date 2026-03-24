"""Document rendering helpers shared between workspace.py and tab_bar.py.

Extracted to break the circular import between workspace.py (which imports
tab_bar at module level) and tab_bar.py (which needs these rendering
functions).  All functions here are pure UI renderers with no dependency
on tab_bar.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from nicegui import ui

from promptgrimoire.pages.annotation.content_form import _render_add_content_form
from promptgrimoire.pages.annotation.css import _build_tag_toolbar
from promptgrimoire.pages.annotation.document import (
    _render_document_with_highlights,
)
from promptgrimoire.pages.annotation.highlights import _add_highlight
from promptgrimoire.pages.annotation.respond import word_count
from promptgrimoire.pages.annotation.word_count_badge import format_word_count_badge

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from promptgrimoire.pages.annotation import PageState

logger = structlog.get_logger()


def render_content_form_outside_refreshable(
    state: PageState,
    workspace_id: UUID,
    *,
    has_documents: list[bool],
    on_document_added: Callable[[], object],
) -> ui.element | None:
    """Render the content form outside the refreshable boundary.

    Placement depends on whether documents already exist:
    - With documents: collapsible "Add Document" expansion panel
    - Without documents: bare content form for first upload

    Returns the wrapper element (used by the caller for layout purposes).
    """
    if not state.can_upload:
        return None

    if has_documents and has_documents[0]:
        with ui.expansion(
            "Add Document",
            icon="note_add",
        ).classes("w-full mt-4") as wrapper:
            _render_add_content_form(workspace_id, on_document_added)
        return wrapper
    else:
        with ui.column().classes("w-full") as wrapper:
            _render_add_content_form(workspace_id, on_document_added)
        return wrapper


async def render_document_container(
    state: PageState,
    doc: Any,
    crdt_doc: Any,
    *,
    on_add_tag: Any | None,
    on_manage_tags: Any,
    footer: Any | None,
) -> None:
    """Render a document with highlights and initialise the word count badge."""
    logger.debug("[RENDER] rendering document with highlights")
    await _render_document_with_highlights(
        state,
        doc,
        crdt_doc,
        on_add_click=on_add_tag,
        on_manage_click=on_manage_tags,
        footer=footer,
    )
    logger.debug("[RENDER] document rendered")

    # Initialise word count badge from existing CRDT content
    if state.word_count_badge is not None:
        initial_md = str(crdt_doc.response_draft_markdown)
        initial_count = word_count(initial_md)
        badge_state = format_word_count_badge(
            initial_count, state.word_minimum, state.word_limit
        )
        state.word_count_badge.set_text(badge_state.text)
        state.word_count_badge.classes(replace=badge_state.css_classes)


def render_empty_template_toolbar(
    state: PageState,
    *,
    on_add_tag: Any | None,
    on_manage_tags: Any,
    can_create_tags: bool,
    footer: Any | None,
) -> None:
    """Render tag toolbar for empty template workspaces.

    Allows tag management before any content is uploaded.  Tag buttons
    are inert (``_add_highlight`` guards on ``document_id is None``).
    """
    logger.debug("[RENDER] no documents, showing toolbar + add content form")

    async def handle_tag_click(tag_key: str) -> None:
        await _add_highlight(state, tag_key)

    state.toolbar_container = _build_tag_toolbar(
        state.tag_info_list or [],
        handle_tag_click,
        on_add_click=(on_add_tag if can_create_tags else None),
        on_manage_click=on_manage_tags,
        footer=footer,
    )
