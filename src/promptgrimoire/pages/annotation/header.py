"""Workspace header: status badges, placement chip, sharing, export, copy protection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.db.workspaces import get_placement_context
from promptgrimoire.pages.annotation.broadcast import _update_user_count

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.db.workspaces import PlacementContext
    from promptgrimoire.pages.annotation import PageState
from promptgrimoire.pages.annotation.pdf_export import _handle_pdf_export
from promptgrimoire.pages.annotation.placement import show_placement_dialog
from promptgrimoire.pages.annotation.sharing import render_sharing_controls

logger = logging.getLogger(__name__)


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
    _selectors = '#doc-container, [data-testid="respond-reference-panel"]'
    ui.run_javascript(f"setupCopyProtection({_selectors!r})")
    ui.add_css(_COPY_PROTECTION_PRINT_CSS)
    ui.html(_COPY_PROTECTION_PRINT_MESSAGE, sanitize=False)


async def render_workspace_header(
    state: PageState,
    workspace_id: UUID,
    protect: bool = False,
    *,
    allow_sharing: bool = False,
    shared_with_class: bool = False,
    can_manage_sharing: bool = False,
    user_id: UUID | None = None,
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
        # Update with actual count now that badge exists
        _update_user_count(state)

        # Export PDF button with loading state
        export_btn = ui.button(
            "Export PDF",
            icon="picture_as_pdf",
        ).props("color=primary")

        async def on_export_click() -> None:
            export_btn.disable()
            export_btn.props("loading")
            try:
                await _handle_pdf_export(state, workspace_id)
            finally:
                export_btn.props(remove="loading")
                export_btn.enable()

        export_btn.on_click(on_export_click)
        logger.debug("[HEADER] buttons done, calling placement_chip")

        # Placement status chip (refreshable)
        @ui.refreshable
        async def placement_chip() -> None:
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

            # Template workspaces have locked placement
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
            ).tooltip("Copy protection is enabled for this activity")

        # Sharing controls (Phase 5)
        render_sharing_controls(
            workspace_id=workspace_id,
            allow_sharing=allow_sharing,
            shared_with_class=shared_with_class,
            can_manage_sharing=can_manage_sharing,
            viewer_is_privileged=state.viewer_is_privileged,
            grantor_id=user_id,
        )
