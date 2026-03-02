"""PDF export orchestration for the annotation page.

Handles the PDF export flow: gathering highlights, document content,
response markdown, and invoking the export pipeline.

Includes pre-export word count enforcement (AC5, AC6):
- Soft mode: warning dialog with "Export Anyway" / "Cancel"
- Hard mode: blocking dialog with "Dismiss" only
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
from promptgrimoire.word_count import word_count
from promptgrimoire.word_count_enforcement import (
    WordCountViolation,
    check_word_count_violation,
    format_violation_message,
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


async def _show_word_count_warning(violation: WordCountViolation) -> bool:
    """Show soft-mode word count warning dialog.

    Presents the violation message with "Export Anyway" and "Cancel" buttons.
    Returns True if the user chose to proceed with export.

    AC5.1: Dialog shows violation message.
    AC5.2: User can confirm and proceed.
    """
    result = asyncio.Event()
    proceed = False

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Word Count Warning").classes("text-lg font-bold text-amber-800")
        ui.label(format_violation_message(violation)).classes("text-sm")

        with ui.row().classes("w-full justify-end gap-2 mt-4"):

            def on_cancel() -> None:
                nonlocal proceed
                proceed = False
                dialog.close()
                result.set()

            def on_export() -> None:
                nonlocal proceed
                proceed = True
                dialog.close()
                result.set()

            ui.button("Cancel", on_click=on_cancel).props(
                'flat data-testid="wc-cancel-btn"'
            )
            ui.button("Export Anyway", on_click=on_export).props(
                'color=warning data-testid="wc-export-anyway-btn"'
            )

    dialog.open()
    await result.wait()
    return proceed


async def _show_word_count_block(violation: WordCountViolation) -> None:
    """Show hard-mode word count blocking dialog.

    Presents the violation message with only a "Dismiss" button.
    Export is not permitted.

    AC6.1: Export blocked with dialog explaining violation.
    AC6.2: Dialog has no export button -- only dismiss.
    """
    result = asyncio.Event()

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Export Blocked").classes("text-lg font-bold text-red-800")
        ui.label(format_violation_message(violation)).classes("text-sm")
        ui.label("You must meet the word count requirements before exporting.").classes(
            "text-xs text-gray-600 mt-1"
        )

        with ui.row().classes("w-full justify-end mt-4"):

            def on_dismiss() -> None:
                dialog.close()
                result.set()

            ui.button("Dismiss", on_click=on_dismiss).props(
                'data-testid="wc-dismiss-btn"'
            )

    dialog.open()
    await result.wait()


async def _extract_response_markdown(state: PageState) -> str:
    """Extract response draft markdown from the editor or CRDT fallback.

    Primary path: JS extraction from the running Milkdown editor (most accurate).
    Fallback: CRDT Text field synced by whichever client last edited Tab 3.
    """
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
                "PDF export: JS markdown extraction failed (%s), using CRDT fallback",
                type(exc).__name__,
            )
            response_markdown = ""

    if not response_markdown and state.crdt_doc is not None:
        response_markdown = state.crdt_doc.get_response_draft_markdown()

    return response_markdown


async def _check_word_count_enforcement(
    state: PageState,
    response_text: str,
) -> tuple[bool, int | None]:
    """Run pre-export word count enforcement check.

    Accepts pre-extracted response text (from the live Milkdown editor via JS)
    so that enforcement and export always operate on the same content. Callers
    must extract the text via ``_extract_response_markdown()`` before calling
    this function.

    Args:
        state: Current page state with word limit configuration.
        response_text: The response draft text to count words in.  Must be
            the same text that will be passed to the export pipeline.

    Returns:
        A tuple of (should_proceed, export_word_count). ``should_proceed``
        is False if export was cancelled or blocked. ``export_word_count``
        is the computed count (or None if no limits are configured).
    """
    has_limits = state.word_minimum is not None or state.word_limit is not None
    if not has_limits:
        return True, None

    count = word_count(response_text) if response_text else 0
    violation = check_word_count_violation(count, state.word_minimum, state.word_limit)

    if not violation.has_violation:
        return True, count

    if state.word_limit_enforcement:
        # Hard mode (AC6): block export entirely
        await _show_word_count_block(violation)
        return False, count

    # Soft mode (AC5): warn, let user choose
    should_proceed = await _show_word_count_warning(violation)
    return should_proceed, count


async def _handle_pdf_export(state: PageState, workspace_id: UUID) -> None:
    """Handle PDF export with loading notification."""
    if state.crdt_doc is None or state.document_id is None:
        ui.notify("No document to export", type="warning")
        return

    # --- Extract response markdown once (live JS path, with CRDT fallback) ---
    # This single extraction is shared by both enforcement and the export
    # pipeline, eliminating any divergence between stale CRDT and live editor
    # content (AC5/AC6 enforcement fires on the same text that goes into the PDF).
    response_markdown = await _extract_response_markdown(state)

    # --- Word count enforcement (AC5, AC6) ---
    should_proceed, export_word_count = await _check_word_count_enforcement(
        state, response_markdown
    )
    if not should_proceed:
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

        # Enrich highlights with display names so the export pipeline renders
        # human-readable tag names instead of UUIDs (DB-backed tags store UUIDs
        # in the CRDT "tag" field).
        tag_name_map = {ti.raw_key: ti.name for ti in (state.tag_info_list or [])}
        highlights = [
            {**hl, "tag_name": tag_name_map.get(str(hl.get("tag", "")))}
            for hl in highlights
        ]

        doc = await get_document(state.document_id)
        if doc is None or not doc.content:
            notification.dismiss()
            ui.notify(
                "No document content to export. Please paste or upload content first.",
                type="warning",
            )
            return
        html_content = doc.content

        # Convert markdown to LaTeX via Pandoc (no new dependencies).
        # markdown_to_latex_notes() handles empty/whitespace-only input gracefully.
        # response_markdown was extracted above, before enforcement.
        notes_latex = await markdown_to_latex_notes(response_markdown)

        # Convert string keys (from JSON) to int keys (expected by export pipeline)
        doc_para_map = doc.paragraph_map
        legal_para_map: dict[int, int | None] | None = (
            {int(k): v for k, v in doc_para_map.items()} if doc_para_map else None
        )

        # Generate PDF with optional word count snitch badge
        pdf_path = await export_annotation_pdf(
            html_content=html_content,
            highlights=highlights,
            tag_colours=state.tag_colours(),
            general_notes="",
            notes_latex=notes_latex,
            word_to_legal_para=legal_para_map,
            filename=f"workspace_{workspace_id}",
            word_count=export_word_count,
            word_minimum=state.word_minimum,
            word_limit=state.word_limit,
        )

        notification.dismiss()

        # Trigger download
        ui.download(pdf_path)
        ui.notify("PDF exported successfully!", type="positive")
    except Exception as e:
        notification.dismiss()
        logger.exception("Failed to export PDF")
        ui.notify(f"PDF export failed: {e}", type="negative", timeout=10000)
