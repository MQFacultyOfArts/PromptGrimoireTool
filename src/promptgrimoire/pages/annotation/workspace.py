"""Workspace view, header, copy protection, and tab initialisation.

Contains the main workspace rendering logic, placement dialog,
copy protection injection, organise drag setup, and respond tab init.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode
from uuid import UUID

from nicegui import app, events, ui

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.db.activities import list_activities_for_week
from promptgrimoire.db.courses import list_courses, list_user_enrollments
from promptgrimoire.db.weeks import list_weeks
from promptgrimoire.db.workspace_documents import list_documents
from promptgrimoire.db.workspaces import (
    PlacementContext,
    create_workspace,
    get_placement_context,
    get_workspace,
    make_workspace_loose,
    place_workspace_in_activity,
    place_workspace_in_course,
)
from promptgrimoire.pages.annotation import (
    PageState,
    _workspace_presence,
    _workspace_registry,
)
from promptgrimoire.pages.annotation.broadcast import (
    _broadcast_yjs_update,
    _setup_client_sync,
    _update_user_count,
)
from promptgrimoire.pages.annotation.content_form import _render_add_content_form
from promptgrimoire.pages.annotation.document import (
    _render_document_with_highlights,
)
from promptgrimoire.pages.annotation.highlights import (
    _push_highlights_to_client,
    _update_highlight_css,
    _warp_to_highlight,
)
from promptgrimoire.pages.annotation.organise import render_organise_tab
from promptgrimoire.pages.annotation.pdf_export import _handle_pdf_export
from promptgrimoire.pages.annotation.respond import render_respond_tab
from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info

if TYPE_CHECKING:
    from nicegui import Client

logger = logging.getLogger(__name__)


def _get_current_username() -> str:
    """Get the display name for the current user."""
    auth_user = app.storage.user.get("auth_user")
    if auth_user:
        if auth_user.get("display_name"):
            return auth_user["display_name"]
        if auth_user.get("email"):
            return auth_user["email"].split("@")[0]
    return "Anonymous"


async def _create_workspace_and_redirect() -> None:
    """Create a new workspace and redirect to it.

    Requires authenticated user (auth check only, no user ID stored on workspace).
    """
    auth_user = app.storage.user.get("auth_user")
    if not auth_user:
        ui.notify("Please log in to create a workspace", type="warning")
        ui.navigate.to("/login")
        return

    try:
        workspace = await create_workspace()
        logger.info("Created workspace %s", workspace.id)
        ui.navigate.to(f"/annotation?{urlencode({'workspace_id': str(workspace.id)})}")
    except Exception:
        logger.exception("Failed to create workspace")
        ui.notify("Failed to create workspace", type="negative")


def _get_placement_chip_style(ctx: PlacementContext) -> tuple[str, str, str]:
    """Return (label, color, icon) for a placement context chip."""
    if ctx.is_template and ctx.placement_type == "activity":
        return f"Template: {ctx.display_label}", "purple", "lock"
    if ctx.placement_type == "activity":
        return ctx.display_label, "blue", "assignment"
    if ctx.placement_type == "course":
        return ctx.display_label, "green", "folder"
    return "Unplaced", "grey", "help_outline"


def _get_current_user_id() -> UUID | None:
    """Get the local User UUID from session storage, if authenticated."""
    auth_user = app.storage.user.get("auth_user")
    if auth_user and auth_user.get("user_id"):
        return UUID(auth_user["user_id"])
    return None


async def _load_enrolled_course_options(
    user_id: UUID,
) -> dict[str, str]:
    """Load course select options for courses the user is enrolled in."""
    enrollments = await list_user_enrollments(user_id)
    course_ids = {e.course_id for e in enrollments}
    # TODO(Seam-D): Replace with single JOIN query if course count grows
    courses_list = await list_courses()
    return {
        str(c.id): f"{c.code} - {c.name}" for c in courses_list if c.id in course_ids
    }


def _build_activity_cascade(
    course_options: dict[str, str],
    selected: dict[str, UUID | None],
) -> None:
    """Build the Course -> Week -> Activity cascading selects.

    Renders UI elements in the current NiceGUI context.
    Stores selected IDs into ``selected`` dict under keys
    "course", "week", "activity".
    """

    course_select = (
        ui.select(options=course_options, label="Course", with_input=True)
        .classes("w-full")
        .props('data-testid="placement-course"')
    )
    week_select = (
        ui.select(options={}, label="Week")
        .classes("w-full")
        .props('data-testid="placement-week"')
    )
    week_select.disable()
    activity_select = (
        ui.select(options={}, label="Activity")
        .classes("w-full")
        .props('data-testid="placement-activity"')
    )
    activity_select.disable()

    async def on_course_change(e: events.ValueChangeEventArguments) -> None:
        week_select.options = {}
        week_select.value = None
        week_select.disable()
        activity_select.options = {}
        activity_select.value = None
        activity_select.disable()
        selected["course"] = selected["week"] = selected["activity"] = None
        if e.value:
            try:
                cid = UUID(e.value)
                selected["course"] = cid
                weeks = await list_weeks(cid)
                week_select.options = {
                    str(w.id): f"Week {w.week_number}: {w.title}" for w in weeks
                }
                week_select.update()
                if weeks:
                    week_select.enable()
            except Exception as exc:
                ui.notify(str(exc), type="negative")

    course_select.on_value_change(on_course_change)

    async def on_week_change(e: events.ValueChangeEventArguments) -> None:
        activity_select.options = {}
        activity_select.value = None
        activity_select.disable()
        selected["week"] = selected["activity"] = None
        if e.value:
            try:
                wid = UUID(e.value)
                selected["week"] = wid
                activities = await list_activities_for_week(wid)
                activity_select.options = {str(a.id): a.title for a in activities}
                activity_select.update()
                if activities:
                    activity_select.enable()
            except Exception as exc:
                ui.notify(str(exc), type="negative")

    week_select.on_value_change(on_week_change)

    def on_activity_change(e: events.ValueChangeEventArguments) -> None:
        selected["activity"] = UUID(e.value) if e.value else None

    activity_select.on_value_change(on_activity_change)


def _build_course_only_select(
    course_options: dict[str, str],
    selected: dict[str, UUID | None],
) -> None:
    """Build a single Course select for course-level placement.

    Stores the selected course ID into ``selected["course_only"]``.
    """

    course_only_select = (
        ui.select(options=course_options, label="Course", with_input=True)
        .classes("w-full")
        .props('data-testid="placement-course-only"')
    )

    def on_change(e: events.ValueChangeEventArguments) -> None:
        selected["course_only"] = UUID(e.value) if e.value else None

    course_only_select.on_value_change(on_change)


async def _apply_placement(
    mode_value: str,
    workspace_id: UUID,
    selected: dict[str, UUID | None],
) -> bool:
    """Apply the placement based on the selected mode.

    Returns True on success, False if validation failed.
    """
    if mode_value == "loose":
        await make_workspace_loose(workspace_id)
        ui.notify("Workspace unplaced", type="positive")
        return True
    if mode_value == "activity":
        aid = selected.get("activity")
        if aid is None:
            ui.notify(
                "Please select a course, week, and activity",
                type="warning",
            )
            return False
        await place_workspace_in_activity(workspace_id, aid)
        ui.notify("Workspace placed in activity", type="positive")
        return True
    if mode_value == "course":
        cid = selected.get("course_only")
        if cid is None:
            ui.notify("Please select a course", type="warning")
            return False
        await place_workspace_in_course(workspace_id, cid)
        ui.notify("Workspace associated with course", type="positive")
        return True
    return False


async def _show_placement_dialog(
    workspace_id: UUID,
    current_ctx: PlacementContext,
    on_changed: Any,
) -> None:
    """Open the placement dialog for changing workspace placement.

    Args:
        workspace_id: The workspace to place.
        current_ctx: Current placement context (for pre-selecting state).
        on_changed: Async callable to invoke after placement changes.
    """
    user_id = _get_current_user_id()
    if user_id is None:
        ui.notify("Please log in to change placement", type="warning")
        return

    initial_mode = current_ctx.placement_type
    if initial_mode not in {"activity", "course"}:
        initial_mode = "loose"

    course_options = await _load_enrolled_course_options(user_id)
    selected: dict[str, UUID | None] = {}

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Change Workspace Placement").classes("text-lg font-bold mb-2")
        mode = ui.radio(
            options={
                "loose": "Unplaced",
                "activity": "Place in Activity",
                "course": "Associate with Course",
            },
            value=initial_mode,
        ).props('data-testid="placement-mode"')

        activity_container = ui.column().classes("w-full gap-2")
        course_container = ui.column().classes("w-full gap-2")

        with activity_container:
            _build_activity_cascade(course_options, selected)
        with course_container:
            _build_course_only_select(course_options, selected)

        def update_visibility() -> None:
            activity_container.set_visibility(mode.value == "activity")
            course_container.set_visibility(mode.value == "course")

        mode.on_value_change(lambda _: update_visibility())
        update_visibility()

        with ui.row().classes("w-full justify-end gap-2 mt-4"):

            async def on_confirm() -> None:
                try:
                    ok = await _apply_placement(
                        cast("str", mode.value), workspace_id, selected
                    )
                except ValueError as exc:
                    ui.notify(str(exc), type="negative")
                    return
                if ok:
                    dialog.close()
                    await on_changed()

            ui.button("Confirm", on_click=on_confirm).props("color=primary")
            ui.button("Cancel", on_click=dialog.close).props("flat")

    dialog.open()


async def _render_workspace_header(
    state: PageState,
    workspace_id: UUID,
    protect: bool = False,
) -> None:
    """Render the header row with save status, user count, and export button.

    Extracted from _render_workspace_view to keep statement count manageable.

    Args:
        state: Page state to populate with header element references.
        workspace_id: Workspace UUID for export.
        protect: Whether copy protection is active for this workspace.
    """
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

        # Placement status chip (refreshable)
        @ui.refreshable
        async def placement_chip() -> None:
            ctx = await get_placement_context(workspace_id)
            label, color, icon = _get_placement_chip_style(ctx)
            is_authenticated = _get_current_user_id() is not None

            async def open_dialog() -> None:
                await _show_placement_dialog(workspace_id, ctx, placement_chip.refresh)

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

        await placement_chip()

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


def _parse_sort_end_args(
    args: dict[str, Any],
) -> tuple[str, str, str, int]:
    """Parse SortableJS sort-end event args into highlight ID and tag keys.

    Extracts and normalizes IDs from SortableJS event args:
    - ``item``: Card HTML ID (format: ``hl-{highlight_id}``)
    - ``from``: Source container ID (format: ``sort-{raw_key}`` or
      ``sort-untagged``)
    - ``to``: Target container ID (format: ``sort-{raw_key}`` or
      ``sort-untagged``)
    - ``newIndex``: Position in target container (0-indexed)

    Returns tuple: (highlight_id, source_tag_raw_key, target_tag_raw_key,
    new_index)

    The ``hl-`` and ``sort-`` prefixes are stripped. The special key
    ``sort-untagged`` is mapped to an empty string (CRDT convention).

    Args:
        args: Event args dict from SortableJS sort-end event.

    Returns:
        Tuple of (highlight_id, source_tag, target_tag, new_index).
        Empty strings or -1 indicate missing/invalid values.
    """
    item_id: str = args.get("item", "")
    from_id: str = args.get("from", "")
    to_id: str = args.get("to", "")
    new_index: int = args.get("newIndex", -1)

    # Parse IDs: "hl-{highlight_id}" and "sort-{raw_key}"
    highlight_id = item_id.removeprefix("hl-")
    source_tag = from_id.removeprefix("sort-")
    target_tag = to_id.removeprefix("sort-")

    # "sort-untagged" -> empty string (CRDT convention)
    if source_tag == "untagged":
        source_tag = ""
    if target_tag == "untagged":
        target_tag = ""

    return highlight_id, source_tag, target_tag, new_index


def _setup_organise_drag(state: PageState) -> None:
    """Set up SortableJS sort-end handler and Organise tab refresh.

    Wires the on_sort_end callback to CRDT operations and stores a
    refresh_organise callable on state for broadcast-triggered re-renders.

    Must be called after state is created but before _on_tab_change is
    defined, since the tab change handler calls state.refresh_organise.
    """

    async def _on_organise_sort_end(e: events.GenericEventArguments) -> None:
        """Handle a SortableJS sort-end event from Tab 2.

        Parses source/target tag from Sortable container HTML IDs
        (``sort-{raw_key}``) and highlight_id from card HTML ID
        (``hl-{highlight_id}``). Same-column reorders within the tag;
        cross-column moves reassign the highlight's tag. Both mutate
        CRDT and broadcast.
        """
        if state.crdt_doc is None:
            return

        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(e.args)

        if not highlight_id:
            logger.warning("Sort-end event with no item ID: %s", e.args)
            return

        if source_tag == target_tag:
            # Same-column reorder: SortableJS gives us the exact newIndex.
            current_order = state.crdt_doc.get_tag_order(target_tag)
            if highlight_id in current_order:
                current_order.remove(highlight_id)
            current_order.insert(new_index, highlight_id)
            state.crdt_doc.set_tag_order(
                target_tag, current_order, origin_client_id=state.client_id
            )
            ui.notify("Reordered", type="info", position="bottom")
        else:
            # Cross-column move: reassign tag and update orders
            state.crdt_doc.move_highlight_to_tag(
                highlight_id,
                from_tag=source_tag,
                to_tag=target_tag,
                position=new_index,
                origin_client_id=state.client_id,
            )
            ui.notify(
                f"Moved to {target_tag or 'Untagged'}",
                type="positive",
                position="bottom",
            )
            # Re-render to update card tag labels and colours
            _render_organise_now()

        # Persist to database
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            state.workspace_id,
            state.crdt_doc.doc_id,
            last_editor=state.user_name,
        )
        await pm.force_persist_workspace(state.workspace_id)

        # Broadcast to other clients for CRDT sync.
        if state.broadcast_update:
            await state.broadcast_update()

    async def _on_locate(start_char: int, end_char: int) -> None:
        """Warp to a highlight in Tab 1 from Tab 2 or Tab 3."""
        await _warp_to_highlight(state, start_char, end_char)

    def _render_organise_now() -> None:
        """Re-render the Organise tab with current CRDT state."""
        if not (state.organise_panel and state.crdt_doc):
            return
        if state.tag_info_list is None:
            state.tag_info_list = brief_tags_to_tag_info()
        render_organise_tab(
            state.organise_panel,
            state.tag_info_list,
            state.crdt_doc,
            on_sort_end=_on_organise_sort_end,
            on_locate=_on_locate,
        )

    state.refresh_organise = _render_organise_now


async def _initialise_respond_tab(state: PageState, workspace_id: UUID) -> None:
    """Initialise the Respond tab with Milkdown editor and reference panel.

    Called once on first visit to the Respond tab (deferred rendering).
    Sets up the editor, CRDT relay, and marks the client for Yjs broadcast.
    """
    if not (state.respond_panel and state.crdt_doc):
        return

    tags = state.tag_info_list or brief_tags_to_tag_info()

    def _on_broadcast(b64_update: str, origin_client_id: str) -> None:
        _broadcast_yjs_update(workspace_id, origin_client_id, b64_update)

    async def _on_respond_locate(start_char: int, end_char: int) -> None:
        await _warp_to_highlight(state, start_char, end_char)

    (
        state.refresh_respond_references,
        state.sync_respond_markdown,
    ) = await render_respond_tab(
        panel=state.respond_panel,
        tags=tags,
        crdt_doc=state.crdt_doc,
        workspace_key=str(workspace_id),
        workspace_id=workspace_id,
        client_id=state.client_id,
        on_yjs_update_broadcast=_on_broadcast,
        on_locate=_on_respond_locate,
    )
    state.has_milkdown_editor = True
    # Mark this client as having a Milkdown editor for Yjs relay
    ws_key = str(workspace_id)
    clients = _workspace_presence.get(ws_key, {})
    if state.client_id in clients:
        clients[state.client_id].has_milkdown_editor = True


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


def _inject_copy_protection() -> None:
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


async def _render_workspace_view(workspace_id: UUID, client: Client) -> None:  # noqa: PLR0915  # TODO(2026-02): refactor after Phase 7 -- extract tab setup into helpers
    """Render the workspace content view with documents or add content form."""
    workspace = await get_workspace(workspace_id)

    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return

    # Compute copy protection flag (Phase 3 -- consumed by Phase 4 JS injection)
    auth_user = app.storage.user.get("auth_user")
    ctx = await get_placement_context(workspace_id)
    protect = ctx.copy_protection and not is_privileged_user(auth_user)

    # Create page state
    state = PageState(
        workspace_id=workspace_id,
        user_name=_get_current_username(),
    )

    # Set up client synchronization
    _setup_client_sync(workspace_id, client, state)

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")
    await _render_workspace_header(state, workspace_id, protect=protect)

    # Pre-load the Milkdown JS bundle so it's available when Tab 3 (Respond)
    # is first visited. Must be added during page construction -- dynamically
    # injected <script> tags via ui.add_body_html after page load don't execute.
    ui.add_body_html('<script src="/milkdown/milkdown-bundle.js"></script>')

    # Three-tab container (Phase 1: three-tab UI)
    state.initialised_tabs = {"Annotate"}

    with ui.tabs().classes("w-full") as tabs:
        ui.tab("Annotate")
        ui.tab("Organise")
        ui.tab("Respond")

    # Set up Tab 2 drag-and-drop and tab change handler (Phase 4)
    _setup_organise_drag(state)

    async def _on_tab_change(e: events.ValueChangeEventArguments) -> None:
        """Handle tab switching with deferred rendering and refresh."""
        assert state.initialised_tabs is not None
        tab_name = str(e.value)
        prev_tab = state.active_tab
        state.active_tab = tab_name

        # Sync markdown to CRDT when leaving the Respond tab (Phase 7).
        # Wrapped in try/except: sync failure must not block tab switch,
        # otherwise the Annotate refresh never runs and cards disappear.
        if prev_tab == "Respond" and state.sync_respond_markdown:
            try:
                await state.sync_respond_markdown()
            except Exception:
                logger.debug(
                    "RESPOND_MD_SYNC failed on tab leave, continuing",
                    exc_info=True,
                )

        if tab_name == "Organise" and state.organise_panel and state.crdt_doc:
            # Always re-render Organise tab to show current highlights
            state.initialised_tabs.add(tab_name)
            if state.refresh_organise:
                state.refresh_organise()
            return

        if tab_name == "Annotate":
            # Rebuild text node map and re-apply highlights. The text walker
            # does not modify the DOM (unlike char span injection) so this
            # is safe to call on every tab switch.
            _push_highlights_to_client(state)
            if state.refresh_annotations:
                state.refresh_annotations()
            _update_highlight_css(state)
            return

        if tab_name == "Respond":
            if tab_name not in state.initialised_tabs:
                state.initialised_tabs.add(tab_name)
                await _initialise_respond_tab(state, workspace_id)
            elif state.refresh_respond_references:
                state.refresh_respond_references()
            return

        if tab_name not in state.initialised_tabs:
            state.initialised_tabs.add(tab_name)

    with ui.tab_panels(tabs, value="Annotate", on_change=_on_tab_change).classes(
        "w-full"
    ) as panels:
        state.tab_panels = panels

        with ui.tab_panel("Annotate"):
            # Load CRDT document for this workspace
            crdt_doc = await _workspace_registry.get_or_create_for_workspace(
                workspace_id
            )

            # Load existing documents
            documents = await list_documents(workspace_id)

            if documents:
                # Render first document with highlight support
                doc = documents[0]
                await _render_document_with_highlights(state, doc, crdt_doc)
            else:
                # Show add content form (extracted to reduce function complexity)
                _render_add_content_form(workspace_id)

        with ui.tab_panel("Organise") as organise_panel:
            state.organise_panel = organise_panel
            ui.label("Organise tab content will appear here.").classes("text-gray-400")

        with ui.tab_panel("Respond") as respond_panel:
            state.respond_panel = respond_panel
            ui.label("Respond tab content will appear here.").classes("text-gray-400")

    # Inject copy protection JS after tab container is built (Phase 4)
    if protect:
        _inject_copy_protection()
