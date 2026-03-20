"""Roleplay chat page for SillyTavern scenario sessions.

Provides a chat interface for roleplay with Claude API,
featuring streaming responses and JSONL logging.

Route: /roleplay
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from uuid import UUID

import structlog
from nicegui import app, ui
from structlog.contextvars import bind_contextvars

from promptgrimoire.config import get_settings
from promptgrimoire.db.acl import grant_permission
from promptgrimoire.db.workspace_documents import add_document
from promptgrimoire.db.workspaces import create_workspace, update_workspace_title
from promptgrimoire.llm import substitute_placeholders
from promptgrimoire.llm.client import ClaudeClient
from promptgrimoire.llm.log import JSONLLogger, generate_log_filename
from promptgrimoire.models import Character, Session
from promptgrimoire.pages.layout import page_layout, require_roleplay_enabled
from promptgrimoire.pages.registry import page_route
from promptgrimoire.pages.roleplay_access import require_roleplay_page_access
from promptgrimoire.pages.roleplay_export import session_to_html
from promptgrimoire.parsers.sillytavern import parse_character_card
from promptgrimoire.ui_helpers import on_submit_with_value

if TYPE_CHECKING:
    from nicegui.elements.chat_message import ChatMessage
    from nicegui.elements.drawer import RightDrawer
    from nicegui.elements.input import Input
    from nicegui.elements.label import Label
    from nicegui.elements.scroll_area import ScrollArea
    from nicegui.elements.spinner import Spinner

logger = structlog.get_logger()


def _get_default_user_name() -> str:
    """Get default user name from Stytch auth or fallback to 'User'.

    Priority:
    1. Stytch member name (if set)
    2. Parsed email local part (john.smith@example.com -> John Smith)
    3. Fallback to 'User'
    """
    auth_user = app.storage.user.get("auth_user")
    if auth_user:
        # Try Stytch name field first
        if auth_user.get("name"):
            return auth_user["name"]
        # Fall back to parsing email
        if auth_user.get("email"):
            local_part = auth_user["email"].split("@")[0]
            # Convert john.smith or john_smith to "John Smith"
            return " ".join(
                word.title()
                for word in local_part.replace(".", " ").replace("_", " ").split()
            )
    return "User"


_USER_AVATAR = "/static/roleplay/user-default.png"
_AI_AVATAR = "/static/roleplay/becky-bennett.png"
_BECKY_CARD_PATH = (
    Path(__file__).parent.parent / "static" / "roleplay" / "becky-bennett.json"
)


def _create_chat_message(
    content: str, name: str, sent: bool, *, avatar: str | None = None
) -> None:
    """Create a chat message with markdown-rendered content."""
    msg = ui.chat_message(name=name, sent=sent, avatar=avatar)
    with msg:
        ui.markdown(content).classes("text-base")


def _render_messages(session: Session, chat_container, scroll_area: ScrollArea) -> None:
    """Render all messages in the session using chat_message components."""
    with chat_container:
        for turn in session.turns:
            avatar = _USER_AVATAR if turn.is_user else _AI_AVATAR
            _create_chat_message(turn.content, turn.name, turn.is_user, avatar=avatar)
    # Scroll to bottom after rendering
    scroll_area.scroll_to(percent=1.0)


async def _complete_conversation(
    state: dict,
    input_field: Input,
    send_button,
    chat_container,
    *,
    finish_btn=None,
) -> None:
    """Lock the UI, export the conversation, and show a completion banner.

    Called when the AI emits ``<endofconversation>`` or when the user
    clicks "Finish Interview".  ``finish_btn`` is optional — Task 3
    adds the button, Task 2 calls this without it.
    """
    input_field.disable()
    send_button.disable()
    if finish_btn is not None:
        finish_btn.disable()

    session = state["session"]
    auth_user = app.storage.user.get("auth_user")
    if auth_user is None:
        ui.notify("Session expired. Please refresh the page.", type="negative")
        return
    user_id = UUID(auth_user["user_id"])
    workspace_url = await _export_to_workspace(session, user_id)

    with (
        chat_container,
        ui.card()
        .classes("w-full q-pa-md")
        .props('data-testid="roleplay-completion-banner"'),
    ):
        ui.label("The activity is complete.").classes("text-h6")
        ui.link(
            "Review your conversation in the annotation workspace",
            workspace_url,
        ).props('data-testid="roleplay-workspace-link"')


async def _handle_finish(
    state: dict,
    input_field: Input,
    send_button,
    finish_btn,
    chat_container,
) -> None:
    """Show confirmation dialog; on confirm, lock and export the conversation."""
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("End this interview?").classes("text-h6")
        ui.label(
            "This will lock the conversation and export it "
            "to your annotation workspace."
        )
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(
                "End Interview",
                on_click=lambda: dialog.submit(True),
            ).props("color=negative")

    dialog.open()
    confirmed = await dialog

    if confirmed:
        state["session"].ended = True
        await _complete_conversation(
            state, input_field, send_button, chat_container, finish_btn=finish_btn
        )


def _show_thinking_indicator(
    chat_container, character_name: str
) -> tuple[ChatMessage, Spinner, Label, Label]:
    """Show a thinking indicator in the chat and return widget handles.

    Returns (thinking_msg, spinner, thinking_label, streaming_label).
    """
    with chat_container:
        thinking_msg = ui.chat_message(
            name=character_name, sent=False, avatar=_AI_AVATAR
        )
        with thinking_msg:
            with ui.row().classes("items-center gap-2"):
                spinner = ui.spinner("dots", size="sm")
                thinking_label = ui.label("Thinking...").classes("text-gray-500 italic")
            streaming_label = ui.label("")
    return thinking_msg, spinner, thinking_label, streaming_label


async def _stream_response(
    client: ClaudeClient,
    session: Session,
    spinner: Spinner,
    thinking_label: Label,
    streaming_label: Label,
    scroll_area: ScrollArea,
) -> tuple[str, bool]:
    """Stream the AI response, updating widgets as chunks arrive.

    Returns (full_response_text, conversation_ended).
    """
    full_response = ""
    first_chunk = True
    conversation_ended = False
    async for chunk in client.stream_message_only(session):
        if first_chunk:
            spinner.visible = False
            thinking_label.visible = False
            first_chunk = False
        full_response += chunk.text
        streaming_label.text = full_response
        scroll_area.scroll_to(percent=1.0)
        if chunk.ended:
            conversation_ended = True
    return full_response, conversation_ended


async def _handle_send(
    user_message: str,
    state: dict,
    client: ClaudeClient,
    input_field: Input,
    log_path: Path,
    chat_container,
    scroll_area: ScrollArea,
    send_button,
    *,
    finish_btn=None,
) -> None:
    """Handle sending a message and streaming the response.

    ``user_message`` is captured client-side by ``on_submit_with_value``
    to avoid the server-side value race.  See value-capture-hardening
    design doc.
    """
    session = state["session"]
    if session and session.ended:
        return  # AC3.7: no messages after conversation end

    if not user_message or not user_message.strip():
        return

    input_field.value = ""
    send_button.disable()

    # Add user message
    session.add_turn(user_message.strip(), is_user=True)
    with chat_container:
        _create_chat_message(
            user_message.strip(), session.user_name, sent=True, avatar=_USER_AVATAR
        )
    scroll_area.scroll_to(percent=1.0)

    # Show thinking indicator
    thinking_msg, spinner, thinking_label, streaming_label = _show_thinking_indicator(
        chat_container, session.character.name
    )
    scroll_area.scroll_to(percent=1.0)

    # Stream response
    try:
        full_response, conversation_ended = await _stream_response(
            client, session, spinner, thinking_label, streaming_label, scroll_area
        )
    except Exception as e:
        logger.exception("stream_response_failed", operation="stream_response")
        ui.notify(f"Error: {e}", type="negative")
        send_button.enable()
        return

    # Replace streaming message with final rendered version
    thinking_msg.delete()
    with chat_container:
        _create_chat_message(
            full_response, session.character.name, sent=False, avatar=_AI_AVATAR
        )
    scroll_area.scroll_to(percent=1.0)

    if conversation_ended:
        session.ended = True
        logger.info(
            "end_of_conversation_detected",
            character=session.character.name,
            turn_count=len(session.turns),
        )
        await _complete_conversation(
            state, input_field, send_button, chat_container, finish_btn=finish_btn
        )
    else:
        send_button.enable()

    # Log turns
    with log_path.open("a") as f:
        jsonl_log = JSONLLogger(f)
        for turn in session.turns[-2:]:
            jsonl_log.write_turn(turn)


def _setup_session(
    character: Character,
    lorebook_entries: list,
    user_name: str,
) -> tuple[Session, ClaudeClient, Path]:
    """Initialize session, client, and log file."""
    character.lorebook_entries = lorebook_entries
    session = Session(character=character, user_name=user_name)

    if character.first_mes:
        first_msg = substitute_placeholders(
            character.first_mes, char_name=character.name, user_name=user_name
        )
        session.add_turn(first_msg, is_user=False)

    settings = get_settings()
    log_dir = settings.app.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / generate_log_filename(session)

    with log_path.open("w") as f:
        jsonl_log = JSONLLogger(f)
        jsonl_log.write_header(session)
        for turn in session.turns:
            jsonl_log.write_turn(turn)

    audit_path = (
        log_path.with_name(log_path.stem + "_audit.json")
        if settings.roleplay.audit_log
        else None
    )
    client = ClaudeClient(
        api_key=settings.llm.api_key.get_secret_value(),
        model=settings.llm.model,
        thinking_budget=settings.llm.thinking_budget,
        lorebook_budget=settings.llm.lorebook_token_budget,
        audit_log_path=audit_path,
    )
    return session, client, log_path


def _build_char_panel(widgets: dict) -> None:
    """Build the character info panel (left sidebar)."""
    with (
        ui.column()
        .classes("roleplay-char-panel")
        .props('data-testid="roleplay-char-panel"')
    ):
        char_portrait = (
            ui.image(_AI_AVATAR)
            .classes("roleplay-char-portrait")
            .props('data-testid="roleplay-char-portrait"')
        )
        widgets["char_portrait"] = char_portrait
        panel_char_name = ui.label("").classes("text-h5 roleplay-char-name")
        widgets["panel_char_name"] = panel_char_name


def _build_chat_header(
    widgets: dict[str, object], management_drawer: RightDrawer
) -> None:
    """Build the chat card header row with avatar, name, and settings button."""
    with ui.row().classes("w-full items-center justify-between"):
        with (
            ui.row()
            .classes("items-center gap-3")
            .props('data-testid="roleplay-chat-header"')
        ):
            ui.avatar(_AI_AVATAR, size="40px").classes("roleplay-chat-header-avatar")
            char_name_label = (
                ui.label("").classes("text-h5").style("color: rgb(220, 220, 210);")
            )
        widgets["char_name_label"] = char_name_label

        settings_btn = ui.button(icon="settings").props(
            'flat round data-testid="roleplay-settings-btn"'
        )
        settings_btn.on("click", management_drawer.toggle)


_EXPORT_BTN_INITIAL_DISABLED = True

_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB (CRIT-6)


async def _export_to_workspace(session: Session, user_id: UUID) -> str:
    """Export session to annotation workspace, return the URL path.

    Creates a loose workspace, adds the session HTML as an ai_conversation
    document, grants owner permission, and returns the annotation URL.
    """
    html_content = session_to_html(session)

    workspace = await create_workspace()
    bind_contextvars(workspace_id=str(workspace.id))
    title = f"Roleplay: {session.character.name}"
    await update_workspace_title(workspace.id, title)
    await add_document(
        workspace_id=workspace.id,
        type="ai_conversation",
        content=html_content,
        source_type="html",
        title=title,
    )
    await grant_permission(workspace.id, user_id, "owner")

    return f"/annotation?{urlencode({'workspace_id': str(workspace.id)})}"


async def _handle_export(state: dict) -> None:
    """Export the current roleplay session to an annotation workspace.

    Creates a loose workspace, adds the session HTML as a document,
    grants owner permission to the current user, and navigates to the
    annotation page.
    """
    session = state.get("session")
    if session is None:
        ui.notify("No active session to export", type="warning")
        return

    try:
        auth_user = app.storage.user.get("auth_user")
        if not auth_user or not auth_user.get("user_id"):
            ui.notify("You must be logged in to export", type="negative")
            return

        user_id = UUID(auth_user["user_id"])
        workspace_url = await _export_to_workspace(session, user_id)
        ui.navigate.to(workspace_url)
    except Exception:
        logger.exception("Failed to export roleplay session")
        ui.notify("Export failed. Please try again.", type="negative")


def _auto_load_character(state: dict, widgets: dict) -> None:
    """Auto-load the bundled Becky Bennett character card.

    Populates state and widgets on success, opens upload panel on failure.
    Extracted from roleplay_page to reduce cognitive complexity.
    """
    try:
        character, lorebook_entries = parse_character_card(_BECKY_CARD_PATH)
        user_name = _get_default_user_name()

        session, client, log_path = _setup_session(
            character, lorebook_entries, user_name
        )
        state["session"] = session
        state["client"] = client
        state["log_path"] = log_path

        widgets["char_name_label"].text = character.name
        widgets["panel_char_name"].text = character.name
        # Portrait update deferred — parser does not yet extract embedded images
        # from chara_card_v3
        widgets["scenario_label"].text = substitute_placeholders(
            character.scenario or "No scenario",
            char_name=character.name,
            user_name=user_name,
        )

        _render_messages(session, widgets["chat_container"], widgets["scroll_area"])
        widgets["export_button"].enable()
    except Exception:
        logger.exception("Failed to auto-load bundled character card")
        ui.notify("Could not auto-load character card", type="negative")
        widgets["management_drawer"].value = True


async def _handle_upload(e, *, state: dict, widgets: dict) -> None:
    """Process an uploaded character card and initialise the chat session.

    Extracted from roleplay_page to reduce cognitive complexity.
    """
    tmp_path = None
    try:
        content = await e.file.read()

        # CRIT-6: Check upload size before processing
        if len(content) > _MAX_UPLOAD_SIZE:
            ui.notify("File too large (max 100MB)", type="negative")
            return

        # Write to temp file for parsing
        tmp_path = Path(f"/tmp/pg_upload_{e.file.name}")  # nosec B108
        tmp_path.write_bytes(content)

        character, lorebook_entries = parse_character_card(tmp_path)
        user_name = widgets["user_name_input"].value or "User"

        session, client, log_path = _setup_session(
            character, lorebook_entries, user_name
        )

        state["session"] = session
        state["client"] = client
        state["log_path"] = log_path

        widgets["management_drawer"].value = False  # close the drawer

        widgets["char_name_label"].text = character.name
        widgets["panel_char_name"].text = character.name
        # Portrait update deferred — parser does not yet extract embedded images
        # from chara_card_v3
        widgets["scenario_label"].text = substitute_placeholders(
            character.scenario or "No scenario",
            char_name=character.name,
            user_name=user_name,
        )

        # Clear previous messages and render new ones
        widgets["chat_container"].clear()
        _render_messages(session, widgets["chat_container"], widgets["scroll_area"])

        # Enable export now that a session is loaded
        if "export_button" in widgets:
            widgets["export_button"].enable()

        ui.notify(f"Loaded {character.name}")

    except ValueError as ve:
        logger.warning("character_load_validation_error", operation="load_character")
        ui.notify(str(ve), type="negative")
    except Exception as ex:
        logger.exception("character_load_failed", operation="load_character")
        ui.notify(f"Failed to load: {ex}", type="negative")
    finally:
        # Clean up temp file
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


@page_route(
    "/roleplay", title="Roleplay", icon="chat", order=30, requires_roleplay=True
)
async def roleplay_page() -> None:
    """Roleplay chat page."""
    await ui.context.client.connected()

    # Feature flag guard -- require roleplay enabled
    if not require_roleplay_enabled():
        return

    if not require_roleplay_page_access():
        return

    state: dict = {"session": None, "client": None, "log_path": None}
    widgets: dict = {}

    with page_layout("Roleplay", drawer_open=False):
        ui.add_head_html('<link rel="stylesheet" href="/static/roleplay.css">')
        # Inline overrides — Quasar uses very high specificity on
        # chat message colours; an external stylesheet can't always win.
        ui.add_head_html("""<style>
            .roleplay-chat .q-message-text-content {
                background: rgba(60, 60, 60, 0.3) !important;
                color: rgb(220, 220, 210) !important;
            }
            .roleplay-chat .q-message-sent .q-message-text-content {
                background: rgba(0, 0, 0, 0.3) !important;
                color: rgb(220, 220, 210) !important;
            }
            .roleplay-chat .q-message-text {
                color: rgb(220, 220, 210) !important;
            }
            .roleplay-chat .q-message-text--sent {
                background: rgba(0, 0, 0, 0.3) !important;
                color: rgb(220, 220, 210) !important;
            }
            .roleplay-chat .q-message-text--received {
                background: rgba(60, 60, 60, 0.3) !important;
                color: rgb(220, 220, 210) !important;
            }
            .roleplay-chat .q-message-name--sent,
            .roleplay-chat .q-message-name--received {
                color: rgb(180, 180, 170) !important;
            }
            .roleplay-chat .q-message-stamp {
                color: rgb(140, 140, 130) !important;
            }
            /* Input field text colour */
            .roleplay-card .q-field__native,
            .roleplay-card .q-field__prefix,
            .roleplay-card .q-field__suffix,
            .roleplay-card .q-field__input,
            .roleplay-card input,
            .roleplay-card textarea {
                color: rgb(220, 220, 210) !important;
            }
            .roleplay-card .q-field__label {
                color: rgba(220, 220, 210, 0.7) !important;
            }
            .roleplay-card .q-field--outlined .q-field__control::before {
                border-color: rgba(220, 220, 210, 0.3) !important;
            }
            /* Buttons */
            .roleplay-card .q-btn {
                color: rgb(220, 220, 210) !important;
                background: rgba(80, 80, 80, 0.5) !important;
                border: 1px solid rgba(220, 220, 210, 0.2) !important;
            }
            .roleplay-card .q-btn .q-icon {
                color: rgb(220, 220, 210) !important;
            }
            .roleplay-card .q-btn[disabled],
            .roleplay-card .q-btn--disabled {
                color: rgba(220, 220, 210, 0.4) !important;
                background: rgba(80, 80, 80, 0.3) !important;
                border: 1px solid rgba(220, 220, 210, 0.1) !important;
                opacity: 1 !important;
            }
            /* Right drawer dark theme */
            .roleplay-management-drawer {
                background: rgba(30, 30, 30, 0.95) !important;
                border-left: 1px solid rgba(220, 220, 210, 0.1) !important;
                color: rgb(220, 220, 210) !important;
            }
        </style>""")
        ui.query("body").classes("roleplay-bg")

        # Management panel — right drawer, initially closed
        with (
            ui.right_drawer(value=False)
            .classes("roleplay-management-drawer")
            .props('data-testid="roleplay-management-drawer"') as management_drawer
        ):
            widgets["management_drawer"] = management_drawer

            ui.label("Management").classes("text-h6 q-mb-md").style(
                "color: rgb(220, 220, 210);"
            )

            # Export to workspace
            export_button = (
                ui.button(
                    "Export to Workspace",
                    icon="upload",
                    on_click=lambda: _handle_export(state),
                )
                .classes("w-full mb-4")
                .props('data-testid="roleplay-export-btn"')
            )
            if _EXPORT_BTN_INITIAL_DISABLED:
                export_button.disable()
            widgets["export_button"] = export_button

            ui.separator().style("border-color: rgba(220,220,210,0.2);")

            # Load different character
            ui.label("Load Different Character").classes("text-subtitle1 mt-2").style(
                "color: rgb(220, 220, 210);"
            )
            user_name_input = ui.input(
                label="Your name (used as {{user}})",
                value=_get_default_user_name(),
            ).classes("w-64 mb-2")
            widgets["user_name_input"] = user_name_input

            ui.upload(
                label="Drop character card JSON here",
                on_upload=lambda e: _handle_upload(e, state=state, widgets=widgets),
                auto_upload=True,
            ).classes("w-full").props('accept=".json"')

            ui.separator().style("border-color: rgba(220,220,210,0.2);")
            ui.label("Log files are saved to: logs/sessions/").style(
                "color: rgba(220,220,210,0.6); font-size: 12px;"
            )

        # Centre a constrained-width column
        with (
            ui.column()
            .classes("w-full items-center")
            .style("display: flex; flex-direction: column; flex: 1; min-height: 0;"),
            ui.column().classes("roleplay-column").style("padding: 0 16px;"),
        ):
            with (
                ui.row()
                .classes("roleplay-main-row w-full")
                .style("flex: 1; min-height: 0;")
            ):
                _build_char_panel(widgets)

                # Chat section — transparent card over dark background
                with (
                    ui.card()
                    .classes("w-full roleplay-card")
                    .style(
                        "background: rgba(23, 23, 23, 0.75) !important;"
                        " box-shadow: 0 4px 16px rgba(0,0,0,0.4) !important;"
                        " border: 1px solid rgba(220,220,210,0.1) !important;"
                        " border-radius: 12px !important;"
                    )
                    .props('data-testid="roleplay-chat-card"') as chat_card
                ):
                    widgets["chat_card"] = chat_card

                    _build_chat_header(widgets, management_drawer)

                    # Scenario hidden — raw placeholder text is not user-facing
                    scenario_label = ui.label("")
                    scenario_label.visible = False
                    widgets["scenario_label"] = scenario_label

                    with (
                        ui.scroll_area()
                        .classes("w-full border rounded p-4 roleplay-chat")
                        .props('data-testid="roleplay-chat-area"') as scroll_area
                    ):
                        chat_container = ui.column().classes("w-full gap-3")
                    widgets["scroll_area"] = scroll_area
                    widgets["chat_container"] = chat_container

                    with ui.row().classes("w-full mt-4"):
                        message_input = (
                            ui.input(placeholder="Type your message...")
                            .classes("flex-grow")
                            .props('outlined data-testid="roleplay-message-input"')
                            .style("color: rgb(220, 220, 210) !important;")
                        )

                        async def on_send(text: str) -> None:
                            if state["session"]:
                                await _handle_send(
                                    text,
                                    state,
                                    state["client"],
                                    message_input,
                                    state["log_path"],
                                    chat_container,
                                    scroll_area,
                                    send_button,
                                    finish_btn=widgets.get("finish_btn"),
                                )

                        send_button = (
                            ui.button("Send")
                            .classes("ml-2")
                            .props('data-testid="roleplay-send-btn"')
                        )
                        on_submit_with_value(
                            send_button,
                            message_input,
                            on_send,
                        )
                        on_submit_with_value(
                            message_input,
                            message_input,
                            on_send,
                            event="keydown.enter",
                        )

                        finish_btn = (
                            ui.button("Finish Interview", icon="stop")
                            .props('outline data-testid="roleplay-finish-btn"')
                            .classes("ml-2")
                        )
                        widgets["finish_btn"] = finish_btn
                        finish_btn.on(
                            "click",
                            lambda: _handle_finish(
                                state,
                                message_input,
                                send_button,
                                finish_btn,
                                chat_container,
                            ),
                        )

            # Auto-load bundled Becky Bennett character card
            _auto_load_character(state, widgets)
