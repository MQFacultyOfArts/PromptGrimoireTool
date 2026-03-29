"""PDF export orchestration for the annotation page.

Handles the PDF export flow: gathering highlights, document content,
response markdown, and submitting an export job to the queue.

The export job is processed asynchronously by the export worker (Phase 3).
A ui.timer polls for status updates and transitions the UI through
queued -> running -> completed/failed states.

Includes pre-export word count enforcement (AC5, AC6):
- Soft mode: warning dialog with "Export Anyway" / "Cancel"
- Hard mode: blocking dialog with "Dismiss" only
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import structlog
from nicegui import ui
from structlog.contextvars import bind_contextvars

from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.db.exceptions import BusinessLogicError
from promptgrimoire.db.export_jobs import (
    create_export_job,
    get_active_job_for_user,
    get_job,
)
from promptgrimoire.db.workspace_documents import list_documents
from promptgrimoire.db.workspaces import get_workspace_export_metadata
from promptgrimoire.export.filename import (
    PdfExportFilenameContext,
    build_pdf_export_stem,
)
from promptgrimoire.export.pdf_export import (
    markdown_to_latex_notes,
)
from promptgrimoire.word_count import word_count
from promptgrimoire.word_count_enforcement import (
    WordCountViolation,
    check_word_count_violation,
    format_violation_message,
)

if TYPE_CHECKING:
    from promptgrimoire.pages.annotation import PageState

logger = structlog.get_logger()


def _server_local_export_date() -> date:
    """Return the application server's local date for export filenames."""
    return datetime.now().date()


async def _build_export_filename(workspace_id: UUID) -> str:
    """Return the PDF export basename for the workspace."""
    meta = await get_workspace_export_metadata(workspace_id)
    ctx = PdfExportFilenameContext(
        course_code=meta.course_code if meta else None,
        activity_title=meta.activity_title if meta else None,
        workspace_title=meta.workspace_title if meta else None,
        owner_display_name=meta.owner_display_name if meta else None,
        export_date=_server_local_export_date(),
    )
    return build_pdf_export_stem(ctx)


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

    def _anon(d: dict[str, object]) -> dict[str, object]:
        return _anonymise_dict_author(
            d,
            viewing_user_id=viewing_user_id,
            anonymous_sharing=anonymous_sharing,
            viewer_is_privileged=viewer_is_privileged,
            privileged_user_ids=privileged_user_ids,
        )

    result: list[dict[str, object]] = []
    for hl in highlights:
        new_hl = _anon(hl)
        comments = hl.get("comments")
        if isinstance(comments, list):
            new_comments: list[object] = []
            for comment in comments:
                if isinstance(comment, dict):
                    typed = cast("dict[str, object]", comment)
                    new_comments.append(_anon(typed))
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


def _extract_response_markdown(state: PageState) -> str:
    """Extract response draft markdown from the CRDT mirror.

    The response_draft_markdown field is kept current by the
    respond_yjs_update event handler (which includes markdown in
    every event payload). No JS round-trip needed.
    """
    if state.crdt_doc is not None:
        return state.crdt_doc.get_response_draft_markdown()
    return ""


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


# ---------------------------------------------------------------------------
# Job submission, polling, and download (Phase 5 — export queue #402)
# ---------------------------------------------------------------------------


def _show_download_button(download_token: str, state: PageState) -> None:
    """Show download button for a completed export.

    Clears the download container and adds a single download button.
    Re-enables the export button so the user can start a new export.
    The button triggers a browser download from the token-based URL.
    """
    download_url = f"/export/{download_token}/download"

    ui.notification(
        "Your PDF is ready!",
        type="positive",
        timeout=5,
    )

    container = getattr(state, "export_download_container", None)
    if container is not None:
        container.clear()
        with container:
            ui.button(
                "Download your PDF",
                icon="download",
                on_click=lambda: ui.download(download_url),
            ).props('color=positive data-testid="export-download-btn"')

    # Re-enable the export button for new exports
    export_btn = getattr(state, "export_btn", None)
    if export_btn is not None:
        export_btn.enable()


def _start_export_polling(
    job_id: UUID,
    state: PageState,
    *,
    initial_status: str = "queued",
) -> None:
    """Start polling for export job status with UI transitions.

    Creates a spinner notification and a 2-second timer that polls
    the export job status. Status transitions:
    - queued -> "Export queued..."
    - running -> "Compiling PDF..."
    - completed -> dismiss notification, show download button
    - failed -> dismiss notification, show error notification

    Args:
        initial_status: Current job status for the initial notification
            message. Use "running" on page-load recovery to avoid
            briefly showing "Export queued..." for an already-running job.
    """
    _STATUS_MESSAGES = {"running": "Compiling PDF...", "queued": "Export queued..."}
    initial_message = _STATUS_MESSAGES.get(initial_status, "Export queued...")

    notification = ui.notification(
        initial_message,
        spinner=True,
        timeout=None,
        type="ongoing",
    )
    notification.props('data-testid="export-status-spinner"')

    async def _poll_status() -> None:
        job = await get_job(job_id)
        if job is None:
            notification.dismiss()
            timer.deactivate()
            # Re-enable export button — job was deleted
            export_btn = getattr(state, "export_btn", None)
            if export_btn is not None:
                export_btn.enable()
            return

        if job.status == "running":
            notification.message = "Compiling PDF..."
        elif job.status == "completed" and job.download_token:
            notification.dismiss()
            timer.deactivate()
            _show_download_button(job.download_token, state)
        elif job.status == "failed":
            notification.dismiss()
            timer.deactivate()
            ui.notification(
                f"Export failed: {(job.error_message or 'Unknown error')[:200]}",
                type="negative",
                timeout=10,
            )
            # Re-enable export button so user can retry
            export_btn = getattr(state, "export_btn", None)
            if export_btn is not None:
                export_btn.enable()

    timer = ui.timer(2, _poll_status)
    state.export_poll_timer = timer


async def check_existing_export(state: PageState) -> None:
    """On page load, recover state for any active or completed export.

    Called from the annotation page header setup after the export button
    is created. Checks for existing export jobs for this user+workspace
    and starts polling or shows a download button as appropriate.

    **Design trade-off:** A completed export's download button is shown
    even if the document was modified after the export. There is no
    ``modified_at`` comparison between job and workspace. Within a
    session, ``_wrap_refresh_with_stale_download_clear`` handles this
    by clearing the button on any document change. Across page reloads,
    the user may see a download button for a stale PDF. The 24-hour
    token TTL limits exposure. Tracked as a known limitation.
    """
    if state.user_id is None:
        return

    job = await get_active_job_for_user(
        user_id=UUID(state.user_id),
        workspace_id=state.workspace_id,
    )

    if job is None:
        return

    if job.status in ("queued", "running"):
        # Disable export button while job is active
        export_btn = getattr(state, "export_btn", None)
        if export_btn is not None:
            export_btn.disable()
        _start_export_polling(job.id, state, initial_status=job.status)
    elif job.status == "completed" and job.download_token:
        _show_download_button(job.download_token, state)


async def _handle_pdf_export(state: PageState, workspace_id: UUID) -> bool:
    """Handle PDF export: gather data, submit job, start polling.

    Returns True if a job was successfully submitted, False otherwise.
    The per-user concurrency check is handled by create_export_job()
    (DB-level partial unique index), not an in-memory lock.
    """
    bind_contextvars(workspace_id=str(workspace_id))
    if state.crdt_doc is None or state.document_id is None or state.user_id is None:
        ui.notify(
            "Not authenticated" if state.user_id is None else "No document to export",
            type="warning",
        )
        return False

    # --- Extract response markdown once (live JS path, with CRDT fallback) ---
    # This single extraction is shared by both enforcement and the export
    # pipeline, eliminating any divergence between stale CRDT and live editor
    # content (AC5/AC6 enforcement fires on the same text that goes into the PDF).
    response_markdown = _extract_response_markdown(state)

    # --- Word count enforcement (AC5, AC6) ---
    should_proceed, export_word_count = await _check_word_count_enforcement(
        state, response_markdown
    )
    if not should_proceed:
        return False

    # --- Gather payload: all source documents + their highlights ---
    tag_name_map = {ti.raw_key: ti.name for ti in (state.tag_info_list or [])}
    tag_colours = state.tag_colours()

    all_docs = await list_documents(workspace_id)
    source_docs = [d for d in all_docs if d.type == "source" and d.content]
    if not source_docs:
        ui.notify(
            "No document content to export. Please paste or upload content first.",
            type="warning",
        )
        return False

    documents: list[dict[str, Any]] = []
    total_dangling = 0
    for doc in source_docs:
        doc_highlights = state.crdt_doc.get_highlights_for_document(str(doc.id))
        if state.is_anonymous and state.user_id:
            doc_highlights = anonymise_highlights(
                doc_highlights,
                viewing_user_id=state.user_id,
                anonymous_sharing=True,
                viewer_is_privileged=state.viewer_is_privileged,
                privileged_user_ids=state.privileged_user_ids,
            )

        valid = [hl for hl in doc_highlights if hl.get("tag", "") in tag_name_map]
        total_dangling += len(doc_highlights) - len(valid)

        enriched = [
            {**hl, "tag_name": tag_name_map.get(str(hl.get("tag", "")))} for hl in valid
        ]

        doc_para_map = doc.paragraph_map
        legal_para_map: dict[int, int | None] | None = (
            {int(k): v for k, v in doc_para_map.items()} if doc_para_map else None
        )

        documents.append(
            {
                "title": doc.title or f"Source {len(documents) + 1}",
                "html_content": doc.content,
                "highlights": enriched,
                "word_to_legal_para": legal_para_map,
            }
        )

    if total_dangling > 0:
        ui.notify(
            f"{total_dangling} annotation(s) reference deleted tags "
            "and cannot be exported. Re-tag or remove them first.",
            type="negative",
        )
        return False

    notes_latex = await markdown_to_latex_notes(response_markdown)
    filename = await _build_export_filename(workspace_id)

    payload: dict[str, Any] = {
        "documents": documents,
        "tag_colours": tag_colours,
        "general_notes": "",
        "notes_latex": notes_latex,
        "filename": filename,
        "word_count": export_word_count,
        "word_minimum": state.word_minimum,
        "word_limit": state.word_limit,
    }

    # --- Submit job to queue ---
    try:
        job = await create_export_job(UUID(state.user_id), workspace_id, payload)
    except BusinessLogicError:  # only raised by per-user concurrency check
        logger.debug("export_job_rejected", user_id=state.user_id)
        ui.notify(
            "An earlier export is still processing."
            " Reload the page to check its status.",
            type="warning",
        )
        return False

    # --- Start polling for status updates ---
    _start_export_polling(job.id, state)
    return True
