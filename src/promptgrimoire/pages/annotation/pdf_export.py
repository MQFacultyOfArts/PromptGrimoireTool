"""PDF export orchestration for the annotation page.

Handles the PDF export flow: gathering highlights, document content,
response markdown, and invoking the export pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.db.workspace_documents import get_document
from promptgrimoire.export.pdf_export import (
    export_annotation_pdf,
    markdown_to_latex_notes,
)

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.pages.annotation import PageState

logger = logging.getLogger(__name__)


def _anonymise_dict_author(
    d: dict[str, object],
    *,
    viewing_user_id: str,
    anonymous_sharing: bool,
    viewer_is_privileged: bool,
    privileged_user_ids: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Return a shallow copy of *d* with its ``author`` field anonymised."""
    out = dict(d)
    uid = str(d["user_id"]) if d.get("user_id") else None
    out["author"] = anonymise_author(
        author=str(d.get("author", "Unknown")),
        user_id=uid,
        viewing_user_id=viewing_user_id,
        anonymous_sharing=anonymous_sharing,
        viewer_is_privileged=viewer_is_privileged,
        author_is_privileged=(uid is not None and uid in privileged_user_ids),
    )
    return out


def anonymise_highlights(
    highlights: list[dict[str, object]],
    *,
    viewing_user_id: str,
    anonymous_sharing: bool,
    viewer_is_privileged: bool,
    privileged_user_ids: frozenset[str] = frozenset(),
) -> list[dict[str, object]]:
    """Return a deep copy of highlights with author names anonymised.

    Applies ``anonymise_author`` to both highlight-level and comment-level
    author fields. Does not mutate the input list.
    """
    anon_kw = {
        "viewing_user_id": viewing_user_id,
        "anonymous_sharing": anonymous_sharing,
        "viewer_is_privileged": viewer_is_privileged,
        "privileged_user_ids": privileged_user_ids,
    }
    result: list[dict[str, object]] = []
    for hl in highlights:
        new_hl = _anonymise_dict_author(hl, **anon_kw)  # type: ignore[arg-type]
        comments = hl.get("comments")
        if isinstance(comments, list):
            new_comments: list[object] = []
            for comment in comments:
                if isinstance(comment, dict):
                    typed: dict[str, object] = comment  # type: ignore[assignment]
                    new_comments.append(_anonymise_dict_author(typed, **anon_kw))  # type: ignore[arg-type]
                else:
                    new_comments.append(comment)
            new_hl["comments"] = new_comments
        result.append(new_hl)
    return result


async def _handle_pdf_export(state: PageState, workspace_id: UUID) -> None:
    """Handle PDF export with loading notification."""
    if state.crdt_doc is None or state.document_id is None:
        ui.notify("No document to export", type="warning")
        return

    # Show notification with spinner IMMEDIATELY
    notification = ui.notification(
        message="Generating PDF...",
        spinner=True,
        timeout=None,
        type="ongoing",
    )
    # Force UI update before starting async work
    await asyncio.sleep(0)

    try:
        # Get highlights for this document, anonymising if needed
        highlights = state.crdt_doc.get_highlights_for_document(str(state.document_id))
        if state.is_anonymous and state.user_id:
            highlights = anonymise_highlights(
                highlights,
                viewing_user_id=state.user_id,
                anonymous_sharing=True,
                viewer_is_privileged=state.viewer_is_privileged,
                privileged_user_ids=state.privileged_user_ids,
            )

        doc = await get_document(state.document_id)
        if doc is None or not doc.content:
            notification.dismiss()
            ui.notify(
                "No document content to export. Please paste or upload content first.",
                type="warning",
            )
            return
        html_content = doc.content

        # Get response draft markdown for the General Notes section (Phase 7).
        # Primary path: JS extraction from running Milkdown editor (most accurate).
        # Fallback: CRDT Text field synced by whichever client last edited Tab 3.
        response_markdown = ""
        if state.has_milkdown_editor:
            try:
                response_markdown = await ui.run_javascript(
                    "window._getMilkdownMarkdown()", timeout=3.0
                )
                if not response_markdown:
                    response_markdown = ""
            except (TimeoutError, OSError) as exc:
                logger.debug(
                    "PDF export: JS markdown extraction failed (%s), "
                    "using CRDT fallback",
                    type(exc).__name__,
                )
                response_markdown = ""

        if not response_markdown and state.crdt_doc is not None:
            response_markdown = state.crdt_doc.get_response_draft_markdown()

        # Convert markdown to LaTeX via Pandoc (no new dependencies)
        notes_latex = ""
        if response_markdown and response_markdown.strip():
            notes_latex = await markdown_to_latex_notes(response_markdown)

        # Generate PDF
        pdf_path = await export_annotation_pdf(
            html_content=html_content,
            highlights=highlights,
            tag_colours=state.tag_colours(),
            general_notes="",
            notes_latex=notes_latex,
            word_to_legal_para=None,
            filename=f"workspace_{workspace_id}",
        )

        notification.dismiss()

        # Trigger download
        ui.download(pdf_path)
        ui.notify("PDF exported successfully!", type="positive")
    except Exception as e:
        notification.dismiss()
        logger.exception("Failed to export PDF")
        ui.notify(f"PDF export failed: {e}", type="negative", timeout=10000)
