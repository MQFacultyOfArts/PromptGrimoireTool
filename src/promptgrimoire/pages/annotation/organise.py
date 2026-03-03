"""Tab 2 (Organise) rendering for the annotation page.

Renders tag columns with highlight cards, grouped by tag. Each column has a
coloured header and contains cards for highlights assigned to that tag.
Highlights with no tag appear in a final "Untagged" column.

Cards are draggable within and between columns via SortableJS. Sort-end events
update the CRDT tag_order (reorder) or move highlights between tags (reassign)
and broadcast changes to all connected clients.

This module imports TagInfo -- the tag-agnostic abstraction ensures Tab 2
rendering is decoupled from any specific tag definition.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_03.md Task 2
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_04.md Task 2
- AC: three-tab-ui.AC2.1, AC2.2, AC2.3, AC2.4, AC2.6
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from nicegui import ui

from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.db.exceptions import ProtectedDocumentError
from promptgrimoire.db.workspace_documents import count_document_clones, delete_document
from promptgrimoire.elements.sortable import Sortable

if TYPE_CHECKING:
    from collections.abc import Callable

    from nicegui.events import GenericEventArguments

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.db.models import WorkspaceDocument
    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.tags import TagInfo

logger = logging.getLogger(__name__)

# Colour for the "Untagged" column header
_UNTAGGED_COLOUR = "#999999"

# Raw key for the untagged pseudo-tag (empty string in CRDT)
_UNTAGGED_RAW_KEY = ""

# Maximum characters to show in text snippet before truncation
_SNIPPET_MAX_CHARS = 100


def can_delete_document(doc: WorkspaceDocument, *, is_owner: bool) -> bool:
    """Whether a document is eligible for deletion in the UI.

    A document can be deleted when:
    1. The viewer is the workspace owner, AND
    2. The document is user-uploaded (source_document_id IS NULL).

    Template-cloned documents (source_document_id IS NOT NULL) never show
    a delete button (AC4.3).

    Args:
        doc: The workspace document to check.
        is_owner: Whether the current user is the workspace owner.

    Returns:
        True if the delete button should be shown.
    """
    return is_owner and doc.source_document_id is None


def _build_highlight_card(
    highlight: dict[str, Any],
    tag_colour: str,
    display_tag_name: str,
    state: PageState,
    on_locate: Callable[..., Any] | None = None,
) -> ui.card:
    """Render a single highlight card inside a tag column.

    The card's HTML id is set to ``hl-{highlight_id}`` so that SortableJS
    event handlers can identify which highlight was dragged.

    Args:
        highlight: Highlight data dict from CRDT.
        tag_colour: Hex colour for the left border.
        display_tag_name: Human-readable tag name.
        state: Page state for anonymisation context.
        on_locate: Optional async callback(start_char, end_char) to warp to
            the highlight in Tab 1.

    Returns:
        The created ui.card element.
    """
    highlight_id = highlight.get("id", "")
    raw_author = highlight.get("author", "Unknown")
    start_char: int = highlight.get("start_char", 0)
    end_char: int = highlight.get("end_char", 0)
    full_text = highlight.get("text", "")
    snippet = full_text[:_SNIPPET_MAX_CHARS]
    if len(full_text) > _SNIPPET_MAX_CHARS:
        snippet += "..."
    comments: list[dict[str, Any]] = list(highlight.get("comments", []))

    card = (
        ui.card()
        .classes("w-full mb-2 cursor-grab")
        .style(f"border-left: 4px solid {tag_colour};")
        .props(
            f'data-testid="organise-card"'
            f' data-highlight-id="{highlight_id}"'
            f' id="hl-{highlight_id}"'
        )
    )
    with card:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(display_tag_name).classes("text-xs font-bold").style(
                f"color: {tag_colour};"
            )
            if on_locate is not None:

                async def _do_locate(sc: int = start_char, ec: int = end_char) -> None:
                    await on_locate(sc, ec)

                ui.button(icon="my_location", on_click=_do_locate).props(
                    "flat dense size=xs"
                ).tooltip("Locate in document").classes("sortable-ignore")

        # Anonymise highlight author
        hl_user_id = highlight.get("user_id")
        display_author = anonymise_author(
            author=raw_author,
            user_id=hl_user_id,
            viewing_user_id=state.user_id,
            anonymous_sharing=state.is_anonymous,
            viewer_is_privileged=state.viewer_is_privileged,
            author_is_privileged=(
                hl_user_id is not None and hl_user_id in state.privileged_user_ids
            ),
        )
        ui.label(f"by {display_author}").classes("text-xs text-gray-500")
        if snippet:
            ui.label(f'"{snippet}"').classes("text-sm italic mt-1")
        if comments:
            ui.separator().classes("my-1")
            for comment in comments:
                raw_c_author = comment.get("author", "Unknown")
                comment_text = comment.get("text", "")
                c_uid = comment.get("user_id")
                display_c_author = anonymise_author(
                    author=raw_c_author,
                    user_id=c_uid,
                    viewing_user_id=state.user_id,
                    anonymous_sharing=state.is_anonymous,
                    viewer_is_privileged=state.viewer_is_privileged,
                    author_is_privileged=(
                        c_uid is not None and c_uid in state.privileged_user_ids
                    ),
                )
                with ui.row().classes("w-full gap-1 items-start"):
                    ui.label(f"{display_c_author}:").classes(
                        "text-xs font-semibold text-gray-600 flex-shrink-0"
                    )
                    ui.label(comment_text).classes("text-xs text-gray-700")

    return card


def _render_ordered_cards(
    highlights: list[dict[str, Any]],
    ordered_ids: list[str],
    tag_colour: str,
    tag_name: str,
    state: PageState,
    on_locate: Callable[..., Any] | None,
) -> None:
    """Render highlight cards respecting tag_order, then unordered remainder.

    Ordered highlights are rendered first (in tag_order sequence), followed
    by any highlights not yet in the order list. Shows an empty-state hint
    when the column has no highlights at all.

    Args:
        highlights: All highlights assigned to this tag.
        ordered_ids: Ordered highlight IDs from CRDT tag_order.
        tag_colour: Hex colour for card left borders.
        tag_name: Display name for card tag label.
        state: Page state for anonymisation context.
        on_locate: Optional locate callback for Tab 1 warp.
    """
    hl_by_id = {h.get("id", ""): h for h in highlights}
    rendered_ids: set[str] = set()

    for hid in ordered_ids:
        if hid in hl_by_id:
            _build_highlight_card(hl_by_id[hid], tag_colour, tag_name, state, on_locate)
            rendered_ids.add(hid)

    for hl in highlights:
        hid = hl.get("id", "")
        if hid not in rendered_ids:
            _build_highlight_card(hl, tag_colour, tag_name, state, on_locate)

    if not highlights:
        ui.label("No highlights").classes(
            "text-xs text-gray-400 italic p-2 sortable-ignore"
        )


def _build_tag_column(
    tag_name: str,
    tag_colour: str,
    raw_key: str,
    highlights: list[dict[str, Any]],
    ordered_ids: list[str],
    on_sort_end: Callable[[GenericEventArguments], Any] | None,
    state: PageState,
    on_locate: Callable[..., Any] | None = None,
) -> ui.column:
    """Render a single tag column with header and highlight cards.

    Cards are ordered by tag_order first, with any unordered highlights
    appended at the bottom. If on_sort_end is provided, cards are wrapped
    in a SortableJS container enabling drag reorder and cross-column moves.

    Args:
        tag_name: Display name for column header.
        tag_colour: Hex colour for header background and card borders.
        raw_key: Raw tag key for CRDT operations.
        highlights: All highlights assigned to this tag.
        ordered_ids: Ordered highlight IDs from CRDT tag_order.
        on_sort_end: Callback for sort-end events (None to disable drag).
        state: Page state for anonymisation context.
        on_locate: Optional async callback(start_char, end_char) to warp to
            a highlight in Tab 1.

    Returns:
        The created ui.column element.
    """
    column = (
        ui.column()
        .classes("min-w-64 max-w-80 flex-shrink-0 self-stretch")
        .props(f'data-testid="tag-column" data-tag-name="{tag_name}"')
    )

    with column:
        # Coloured header
        ui.label(tag_name).classes(
            "text-white font-bold text-sm px-3 py-1 rounded-t w-full text-center"
        ).style(f"background-color: {tag_colour};")

        # Create Sortable container for cards
        sortable = Sortable(
            options={
                "group": "organise-highlights",
                "animation": 150,
                "filter": ".sortable-ignore",
            },
            on_end=on_sort_end,
        )
        # Set HTML id so event handler can identify the tag
        sortable_id = f"sort-{raw_key}" if raw_key else "sort-untagged"
        sortable.props(f'id="{sortable_id}"')
        sortable.classes("w-full flex-grow min-h-24 pb-4")

        with sortable:
            _render_ordered_cards(
                highlights, ordered_ids, tag_colour, tag_name, state, on_locate
            )

    return column


def _build_document_section(
    documents: list[WorkspaceDocument],
    state: PageState,
) -> None:
    """Render the document management section below tag columns.

    Shows each document with title, source type badge, protection status,
    and a delete button for user-uploaded documents when the viewer is
    the workspace owner.

    Template-cloned documents (source_document_id IS NOT NULL) show a
    "Template" badge and no delete button (AC4.3).

    Args:
        documents: Pre-loaded workspace documents.
        state: Page state (provides is_owner, workspace_id).
    """
    with (
        ui.column()
        .classes("w-full mt-4")
        .props('data-testid="document-management-section"')
    ):
        ui.label("Documents").classes("text-lg font-semibold mb-2")
        ui.separator()
        if not documents:
            ui.label("No documents in this workspace.").classes(
                "text-sm text-gray-400 italic py-2"
            )
            return
        for doc in documents:
            with ui.row().classes("w-full items-center gap-2 py-1"):
                ui.label(doc.title or "Untitled").classes("text-sm")
                ui.badge(doc.source_type).classes("text-xs")
                if doc.source_document_id is not None:
                    ui.badge("Template", color="blue").classes("text-xs").props(
                        'data-testid="template-badge"'
                    )
                elif state.is_owner:
                    ui.button(
                        icon="delete",
                        on_click=lambda d=doc: _handle_delete_document(d, state),
                    ).props(
                        "flat round dense size=sm color=negative"
                        f' data-testid="delete-doc-btn-{doc.id}"'
                    )


async def _handle_delete_document(doc: WorkspaceDocument, state: PageState) -> None:
    """Show confirmation dialog and delete a user-uploaded document.

    Checks for student clones first. If the document is a template source
    with clones, shows a warning before proceeding (AC5.5). Otherwise
    shows a standard confirmation dialog (AC4.1).

    Args:
        doc: The document to delete.
        state: Page state (provides workspace_id for redirect).
    """
    clone_count = await count_document_clones(doc.id)

    if clone_count > 0:
        _show_clone_warning_dialog(doc, state, clone_count)
        return

    _show_delete_confirm_dialog(doc, state)


def _show_clone_warning_dialog(
    doc: WorkspaceDocument, state: PageState, clone_count: int
) -> None:
    """Show warning dialog when deleting a template document with clones.

    Args:
        doc: The template source document.
        state: Page state for redirect after deletion.
        clone_count: Number of student clones.
    """
    with ui.dialog() as warn_dialog, ui.card().classes("w-96"):
        ui.label(
            f"{clone_count} student{'s' if clone_count != 1 else ''} "
            f"{'have' if clone_count != 1 else 'has'} "
            "copies of this document. "
            "Deleting it will make their copies deletable."
        ).classes("text-body1").props('data-testid="clone-warning-text"')
        with ui.row().classes("justify-end w-full gap-2 mt-4"):
            ui.button("Cancel", on_click=warn_dialog.close).props(
                'flat data-testid="cancel-delete-doc-btn"'
            )

            async def _proceed_after_warning() -> None:
                warn_dialog.close()
                await _do_delete_document(doc, state)

            ui.button("Delete Anyway", on_click=_proceed_after_warning).props(
                'color=negative data-testid="confirm-delete-doc-btn"'
            )
    warn_dialog.open()


def _show_delete_confirm_dialog(doc: WorkspaceDocument, state: PageState) -> None:
    """Show standard confirmation dialog for deleting a user-uploaded document.

    Args:
        doc: The document to delete.
        state: Page state for redirect after deletion.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"Delete '{doc.title or 'Untitled'}'?").classes("text-lg font-bold")
        ui.label("Annotations will be removed. Tags preserved.").classes(
            "text-gray-500"
        )
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                'flat data-testid="cancel-delete-doc-btn"'
            )

            async def _confirm() -> None:
                await _do_delete_document(doc, state)
                dialog.close()

            ui.button("Delete", on_click=_confirm).props(
                'color=negative data-testid="confirm-delete-doc-btn"'
            )
    dialog.open()


async def _do_delete_document(doc: WorkspaceDocument, state: PageState) -> None:
    """Execute document deletion and redirect to annotation page.

    Catches ProtectedDocumentError as defence in depth -- the UI should
    never show delete buttons for protected documents, but handle it
    gracefully if it happens.

    Args:
        doc: The document to delete.
        state: Page state (provides workspace_id for redirect).
    """
    try:
        await delete_document(doc.id)
    except ProtectedDocumentError:
        ui.notify("This document is protected and cannot be deleted", type="negative")
        return

    ui.notify("Document deleted. You can upload a replacement.", type="positive")
    qs = urlencode({"workspace_id": str(state.workspace_id)})
    ui.navigate.to(f"/annotation?{qs}")


def render_organise_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    *,
    on_sort_end: (Callable[[GenericEventArguments], Any] | None) = None,
    on_locate: Callable[..., Any] | None = None,
    state: PageState,
    documents: list[WorkspaceDocument] | None = None,
) -> None:
    """Populate the Organise tab panel with tag columns and highlight cards.

    Clears the placeholder content from the panel, then creates a
    horizontally scrollable row of tag columns. Each column shows
    highlights grouped by tag. An "Untagged" column is appended if
    any highlights have no tag.

    When on_sort_end is provided, cards are wrapped in SortableJS
    containers enabling drag reorder and cross-column moves.

    A document management section is appended below the tag columns,
    listing all workspace documents with delete controls for owners.

    Args:
        panel: The ui.tab_panel element to populate.
        tags: List of TagInfo instances.
        crdt_doc: The CRDT annotation document.
        on_sort_end: Callback for SortableJS sort-end events.
        on_locate: Optional async callback(start_char, end_char) to warp to
            a highlight in Tab 1.
        state: Page state for anonymisation context.
        documents: Pre-loaded workspace documents. If None, document
            management section is not rendered.
    """
    # Save scroll position before clearing (h-scroll across columns, v-scroll
    # within the panel). Uses data-testid selector since the element is rebuilt.
    ui.run_javascript(
        "window._organiseScroll = (function() {"
        "  var el = document.querySelector("
        "'[data-testid=\"organise-columns\"]');"
        "  return el"
        "    ? {x: el.scrollLeft, y: el.scrollTop}"
        "    : {x: 0, y: 0};"
        "})();"
    )

    panel.clear()

    all_highlights = crdt_doc.get_all_highlights()

    # Build raw tag value -> TagInfo lookup
    tag_raw_values: dict[str, TagInfo] = {tag.raw_key: tag for tag in tags}

    # Group highlights by tag
    tagged_highlights: dict[str, list[dict[str, Any]]] = {
        tag_info.name: [] for tag_info in tags
    }
    untagged_highlights: list[dict[str, Any]] = []

    for hl in all_highlights:
        raw_tag = hl.get("tag", "")
        if raw_tag and raw_tag in tag_raw_values:
            display_name = tag_raw_values[raw_tag].name
            tagged_highlights[display_name].append(hl)
        else:
            untagged_highlights.append(hl)

    with (
        panel,
        (
            ui.row()
            .classes("w-full overflow-x-auto gap-4 p-4 flex-nowrap items-stretch")
            .props('data-testid="organise-columns"')
        ),
    ):
        for tag_info in tags:
            highlights_for_tag = tagged_highlights[tag_info.name]
            ordered_ids = crdt_doc.get_tag_order(tag_info.raw_key)
            _build_tag_column(
                tag_info.name,
                tag_info.colour,
                tag_info.raw_key,
                highlights_for_tag,
                ordered_ids,
                on_sort_end,
                state,
                on_locate,
            )

        # Untagged column (AC2.6)
        if untagged_highlights:
            ordered_ids = crdt_doc.get_tag_order(_UNTAGGED_RAW_KEY)
            _build_tag_column(
                "Untagged",
                _UNTAGGED_COLOUR,
                _UNTAGGED_RAW_KEY,
                untagged_highlights,
                ordered_ids,
                on_sort_end,
                state,
                on_locate,
            )

    # Document management section (below tag columns)
    if documents is not None:
        with panel:
            _build_document_section(documents, state)

    # Restore scroll position after rebuild
    ui.run_javascript(
        "setTimeout(function() {"
        "  var el = document.querySelector("
        "'[data-testid=\"organise-columns\"]');"
        "  if (el && window._organiseScroll) {"
        "    el.scrollLeft = window._organiseScroll.x;"
        "    el.scrollTop = window._organiseScroll.y;"
        "  }"
        "}, 50);"
    )
