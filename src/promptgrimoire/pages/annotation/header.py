"""Workspace header: status badges, placement chip, sharing, export, copy protection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from nicegui import ui

from promptgrimoire.db.workspace_documents import update_document_paragraph_settings
from promptgrimoire.db.workspaces import PlacementContext, get_placement_context
from promptgrimoire.input_pipeline.paragraph_map import (
    build_paragraph_map_for_json,
    inject_paragraph_attributes,
)
from promptgrimoire.pages.annotation.broadcast import _update_user_count
from promptgrimoire.pages.annotation.document_management import (
    open_manage_documents_dialog,
)
from promptgrimoire.pages.annotation.word_count_badge import format_word_count_badge

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.db.models import WorkspaceDocument
    from promptgrimoire.db.workspaces import PlacementContext
    from promptgrimoire.pages.annotation import PageState

from promptgrimoire.pages.annotation.pdf_export import (
    _handle_pdf_export,
    check_existing_export,
)
from promptgrimoire.pages.annotation.placement import show_placement_dialog
from promptgrimoire.pages.annotation.sharing import render_sharing_controls

logger = structlog.get_logger()


def _get_placement_chip_style(ctx: PlacementContext) -> tuple[str, str, str]:
    """Return (label, color, icon) for a placement context chip."""
    if ctx.is_template and ctx.placement_type == "activity":
        return f"Template: {ctx.display_label}", "purple", "lock"
    if ctx.placement_type == "activity":
        return ctx.display_label, "blue", "assignment"
    if ctx.placement_type == "course":
        return ctx.display_label, "green", "folder"
    return "Unplaced", "grey", "help_outline"


# -- Copy protection JS injection (Phase 4) ----------------------------------

_COPY_PROTECTION_PRINT_CSS = """
@media print {
  .q-tab-panels { display: none !important; }
  .copy-protection-print-message { display: block !important; }
}
.copy-protection-print-message { display: none; }
""".strip()

_COPY_PROTECTION_PRINT_MESSAGE = (
    '<div class="copy-protection-print-message" '
    'style="display:none; padding: 2rem; text-align: center; font-size: 1.5rem;">'
    "Printing is disabled for this activity.</div>"
)


def inject_copy_protection() -> None:
    """Inject client-side JS and CSS to block copy/cut/paste/drag/print.

    Called once during page construction when ``protect=True``. Uses event
    delegation from protected selectors so Milkdown copy (student's own
    writing) is unaffected. Paste is blocked on the Milkdown editor in
    capture phase before ProseMirror sees the event. Ctrl+P/Cmd+P is
    intercepted via keydown handler. CSS ``@media print`` hides tab panels
    and shows a "Printing is disabled" message instead.
    """
    _selectors = '.doc-container, [data-testid="respond-reference-panel"]'
    # On SPA navigations, annotation-copy-protection.js may not be loaded yet
    # (ui.add_body_html only injects on full page loads).  Stash the selectors
    # so the dynamic loader in document.py can call setupCopyProtection later.
    ui.run_javascript(
        f"if (typeof setupCopyProtection === 'function') {{"
        f"  setupCopyProtection({_selectors!r});"
        f"}} else {{"
        f"  window._pendingCopyProtection = {_selectors!r};"
        f"}}"
    )
    ui.add_css(_COPY_PROTECTION_PRINT_CSS)
    ui.html(_COPY_PROTECTION_PRINT_MESSAGE, sanitize=False)


def _render_paragraph_toggle(state: PageState, document: WorkspaceDocument) -> None:
    """Render the auto-number paragraph toggle in the workspace header.

    The toggle rebuilds the paragraph map and re-renders the document
    HTML with updated ``data-para`` attributes.  Existing highlight
    ``para_ref`` values are NOT modified (AC7.3).

    Only shown to users with upload permission (editors/owners).

    Args:
        state: Page state with document container and content references.
        document: The WorkspaceDocument for initial toggle value and ID.
    """

    async def _handle_paragraph_toggle(new_value: bool) -> None:
        """Handle paragraph numbering toggle change.

        Uses ``state.document_id`` (not the captured ``document`` object)
        so the toggle persists to whichever source tab is currently active.
        """
        if not state.document_content or state.document_id is None:
            return

        # Rebuild the paragraph map with the new mode
        new_map = build_paragraph_map_for_json(
            state.document_content, auto_number=new_value
        )

        # Persist to database — use state.document_id (active tab)
        try:
            await update_document_paragraph_settings(
                state.document_id, new_value, new_map
            )
        except Exception:
            logger.exception(
                "Failed to update paragraph settings for doc %s",
                state.document_id,
            )
            ui.notify("Failed to update paragraph settings", type="negative")
            return

        # Update in-memory state
        state.paragraph_map = new_map
        state.auto_number_paragraphs = new_value

        # Re-render the document HTML with new paragraph attributes
        if state.doc_container is not None:
            rendered_html = inject_paragraph_attributes(state.document_content, new_map)
            state.doc_container.clear()
            with state.doc_container:
                ui.html(rendered_html, sanitize=False)

        mode_label = "auto-number" if new_value else "source-number"
        ui.notify(f"Paragraph numbering: {mode_label}", type="info")

    state.paragraph_toggle = ui.switch(
        "Auto-number \u00b6",
        value=document.auto_number_paragraphs,
        on_change=lambda e: _handle_paragraph_toggle(e.value),
    ).props('data-testid="paragraph-toggle"')


def _wrap_refresh_with_stale_download_clear(state: PageState) -> None:
    """Wrap state.refresh_annotations to also clear stale download buttons.

    Any document change (highlight, tag, response edit) triggers
    refresh_annotations. We wrap it to also clear the download
    container and re-enable the export button, since the existing
    PDF is now outdated.
    """
    original = state.refresh_annotations
    if original is None:
        logger.warning(
            "export_stale_clear_wrap_skipped", reason="refresh_annotations not set"
        )
        return

    def wrapped(*, trigger: str = "unknown") -> None:
        # Cancel any active polling timer — the PDF it's tracking
        # is now stale due to the document change.
        poll_timer = getattr(state, "export_poll_timer", None)
        if poll_timer is not None:
            poll_timer.deactivate()
            state.export_poll_timer = None
        # Clear stale download button
        container = getattr(state, "export_download_container", None)
        if container is not None:
            container.clear()
        export_btn = getattr(state, "export_btn", None)
        if export_btn is not None:
            export_btn.enable()
            # Reset error state — the document changed, so a previous
            # failure may no longer apply.
            export_btn.text = "Export PDF"
            export_btn.props("color=primary")
            state.export_error_msg = None
        # Call the original refresh
        original(trigger=trigger)

    state.refresh_annotations = wrapped


def _render_export_button(state: PageState, workspace_id: UUID) -> None:
    """Render the Export PDF button and download container.

    The download_container holds the download button (if any). It is
    cleared and repopulated by _show_download_button / _start_export_polling.
    Storing it on state.export_download_container makes it accessible to
    the polling callback and page-load recovery.
    """
    export_btn = ui.button(
        "Export PDF",
        icon="picture_as_pdf",
    ).props('color=primary data-testid="export-pdf-btn"')

    # Container for the download button — lives next to the export button
    download_container = ui.row().classes("items-center gap-2")
    download_container.props('data-testid="export-download-container"')
    state.export_download_container = download_container
    state.export_btn = export_btn

    async def _do_export() -> None:
        """Reset button to normal state and submit export job."""
        export_btn.text = "Export PDF"
        export_btn.props("color=primary")
        state.export_error_msg = None
        export_btn.disable()
        export_btn.props("loading")
        download_container.clear()
        try:
            job_submitted = await _handle_pdf_export(state, workspace_id)
        except Exception:
            export_btn.props(remove="loading")
            export_btn.enable()
            raise
        export_btn.props(remove="loading")
        if not job_submitted:
            export_btn.enable()

    async def on_export_click() -> None:
        if state.export_error_msg:
            # Show error dialog — no retry because LaTeX failures are
            # deterministic (same content → same error).  The button
            # resets automatically when the document changes.
            with ui.dialog() as dialog, ui.card():
                ui.label("Export failed").classes("text-h6")
                ui.label(state.export_error_msg)
                with ui.row():
                    ui.button("Close", on_click=dialog.close).props("flat")
            dialog.open()
        else:
            await _do_export()

    export_btn.on_click(on_export_click)


def _render_placement_chip(
    workspace_id: UUID,
    user_id: UUID | None,
    prefetched_ctx: PlacementContext | None = None,
) -> ui.refreshable:
    """Build and return a refreshable placement chip.

    Args:
        prefetched_ctx: Pre-fetched placement context from the page-load
            path.  Consumed on the initial render; subsequent ``.refresh()``
            calls (e.g. after the user edits placement) re-fetch from DB.
    """
    _cached: list[PlacementContext | None] = [prefetched_ctx]

    @ui.refreshable
    async def placement_chip() -> None:
        cached = _cached[0]
        _cached[0] = None  # consume: next .refresh() will re-fetch

        if cached is not None:
            ctx = cached
            logger.debug("[HEADER] placement_chip: using pre-fetched context")
        else:
            logger.debug("[HEADER] placement_chip: querying placement")
            ctx = await get_placement_context(workspace_id)
        logger.debug("[HEADER] placement_chip: got ctx, rendering chip")
        label, color, icon = _get_placement_chip_style(ctx)
        is_authenticated = user_id is not None

        async def open_dialog() -> None:
            await show_placement_dialog(
                workspace_id,
                ctx,
                placement_chip.refresh,
                user_id=user_id,
            )

        clickable = is_authenticated and not ctx.is_template
        props_str = 'data-testid="placement-chip" outline'
        if not clickable:
            props_str += " disable"
        chip = ui.chip(
            text=label,
            icon=icon,
            color=color,
            on_click=open_dialog if clickable else None,
        ).props(props_str)
        if ctx.is_template:
            chip.tooltip("Template placement is managed by the Activity")
        elif not is_authenticated:
            chip.tooltip("Log in to change placement")
        logger.debug("[HEADER] placement_chip: done")

    return placement_chip


async def render_workspace_header(
    state: PageState,
    workspace_id: UUID,
    protect: bool = False,
    *,
    allow_sharing: bool = False,
    shared_with_class: bool = False,
    can_manage_sharing: bool = False,
    user_id: UUID | None = None,
    document: WorkspaceDocument | None = None,
    placement_context: PlacementContext | None = None,
) -> None:
    """Render the header row with save status, user count, and export button.

    Args:
        state: Page state to populate with header element references.
        workspace_id: Workspace UUID for export.
        protect: Whether copy protection is active for this workspace.
        allow_sharing: Whether the placement context allows sharing.
        shared_with_class: Current workspace shared_with_class state.
        can_manage_sharing: Whether the user can toggle sharing (owner or privileged).
        user_id: The local User UUID for the current session, or None.
        document: First WorkspaceDocument, used for paragraph numbering toggle.
    """
    logger.debug("[HEADER] START workspace=%s", workspace_id)
    with ui.row().classes("gap-4 items-center"):
        # Save status indicator (for E2E test observability)
        state.save_status = (
            ui.label("")
            .classes("text-sm text-gray-500")
            .props('data-testid="save-status"')
        )

        # User count badge
        state.user_count_badge = (
            ui.label("1 user")
            .classes("text-sm text-blue-600 bg-blue-100 px-2 py-0.5 rounded")
            .props('data-testid="user-count"')
        )
        _update_user_count(state)

        # Word count badge (only when limits are configured)
        if state.word_minimum is not None or state.word_limit is not None:
            badge_state = format_word_count_badge(
                0, state.word_minimum, state.word_limit
            )
            state.word_count_badge = (
                ui.label(badge_state.text)
                .classes(badge_state.css_classes)
                .props('data-testid="word-count-badge"')
            )

        _render_export_button(state, workspace_id)

        # Recover any in-progress or completed export jobs (Phase 5, #402)
        await check_existing_export(state)

        # NOTE: stale download cleanup is wired up in workspace.py
        # AFTER state.refresh_annotations is set by document.py.
        # See _wrap_refresh_with_stale_download_clear().

        # Manage Documents button (owners only)
        if state.is_owner:
            ui.button(
                "Manage Documents",
                icon="description",
                on_click=lambda: open_manage_documents_dialog(state),
            ).props('outline color=primary data-testid="manage-documents-btn"')

        logger.debug("[HEADER] buttons done, calling placement_chip")
        placement_chip = _render_placement_chip(
            workspace_id, user_id, prefetched_ctx=placement_context
        )
        await placement_chip()
        logger.debug("[HEADER] placement_chip awaited")

        # Copy protection lock icon chip (Phase 4)
        if protect:
            ui.chip(
                "Protected",
                icon="lock",
                color="amber-7",
                text_color="white",
            ).props(
                'dense aria-label="Copy protection is enabled for this activity"'
                ' data-testid="copy-protection-chip"'
            ).tooltip("Copy protection is enabled for this activity")

        # Paragraph numbering toggle (Phase 7)
        if document is not None and state.can_upload:
            _render_paragraph_toggle(state, document)

        # Sharing controls (Phase 5)
        render_sharing_controls(
            workspace_id=workspace_id,
            allow_sharing=allow_sharing,
            shared_with_class=shared_with_class,
            can_manage_sharing=can_manage_sharing,
            viewer_is_privileged=state.viewer_is_privileged,
            grantor_id=user_id,
        )
