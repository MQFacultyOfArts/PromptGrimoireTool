"""Roleplay chat page for SillyTavern scenario sessions.

Provides a chat interface for roleplay with Claude API,
featuring streaming responses and JSONL logging.

Route: /roleplay
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from nicegui import app, ui

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
from promptgrimoire.pages.roleplay_export import session_to_html
from promptgrimoire.parsers.sillytavern import parse_character_card

if TYPE_CHECKING:
    from nicegui.elements.input import Input
    from nicegui.elements.scroll_area import ScrollArea

logger = logging.getLogger(__name__)


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


async def _handle_send(
    session: Session,
    client: ClaudeClient,
    input_field: Input,
    log_path: Path,
    chat_container,
    scroll_area: ScrollArea,
    send_button,
) -> None:
    """Handle sending a message and streaming the response."""
    user_message = input_field.value
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
    with chat_container:
        thinking_msg = ui.chat_message(
            name=session.character.name, sent=False, avatar=_AI_AVATAR
        )
        with thinking_msg:
            with ui.row().classes("items-center gap-2"):
                spinner = ui.spinner("dots", size="sm")
                thinking_label = ui.label("Thinking...").classes("text-gray-500 italic")
            streaming_label = ui.label("")
    scroll_area.scroll_to(percent=1.0)

    # Stream response
    full_response = ""
    first_chunk = True
    try:
        async for chunk in client.stream_message_only(session):
            if first_chunk:
                spinner.visible = False
                thinking_label.visible = False
                first_chunk = False
            full_response += chunk
            streaming_label.text = full_response
            scroll_area.scroll_to(percent=1.0)
    except Exception as e:
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

    send_button.enable()

    # Log turns
    with log_path.open("a") as f:
        logger = JSONLLogger(f)
        for turn in session.turns[-2:]:
            logger.write_turn(turn)


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
        logger = JSONLLogger(f)
        logger.write_header(session)
        for turn in session.turns:
            logger.write_turn(turn)

    client = ClaudeClient(
        api_key=settings.llm.api_key.get_secret_value(),
        model=settings.llm.model,
        thinking_budget=settings.llm.thinking_budget,
        lorebook_budget=settings.llm.lorebook_token_budget,
    )
    return session, client, log_path


_EXPORT_BTN_INITIAL_DISABLED = True

_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB (CRIT-6)


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
        html_content = session_to_html(session)

        workspace = await create_workspace()
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

        ui.navigate.to(f"/annotation/{workspace.id}")
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
        widgets["upload_expansion"].value = True


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

        widgets["upload_expansion"].value = False  # collapse the expansion panel

        widgets["char_name_label"].text = character.name
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
        ui.notify(str(ve), type="negative")
    except Exception as ex:
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

    # Auth guard -- require login
    auth_user = app.storage.user.get("auth_user")
    if auth_user is None:
        ui.navigate.to("/login")
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
        </style>""")
        ui.query("body").classes("roleplay-bg")

        # Centre a constrained-width column within the q-page
        ui.query(".q-page").style(
            "display: flex !important; justify-content: center !important;"
        )
        with (
            ui.column()
            .classes("roleplay-column")
            .style("max-width: 1000px; width: 100%;")
        ):
            # Upload section (collapsed — Becky Bennett auto-loads below)
            with (
                ui.expansion("Load Different Character", icon="upload_file")
                .classes("w-full mb-4 roleplay-upload")
                .props('data-testid="roleplay-upload-card"') as upload_expansion
            ):
                widgets["upload_expansion"] = upload_expansion

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

                char_name_label = (
                    ui.label("").classes("text-h5").style("color: rgb(220, 220, 210);")
                )
                widgets["char_name_label"] = char_name_label

                # Scenario hidden — raw placeholder text is not user-facing
                scenario_label = ui.label("")
                scenario_label.visible = False
                widgets["scenario_label"] = scenario_label

                with (
                    ui.scroll_area()
                    .classes("w-full border rounded p-4 roleplay-chat")
                    .style("height: 60vh;")
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
                    )

                    async def on_send() -> None:
                        if state["session"]:
                            await _handle_send(
                                state["session"],
                                state["client"],
                                message_input,
                                state["log_path"],
                                chat_container,
                                scroll_area,
                                send_button,
                            )

                    send_button = (
                        ui.button("Send", on_click=on_send)
                        .classes("ml-2")
                        .props('data-testid="roleplay-send-btn"')
                    )
                    message_input.on("keydown.enter", on_send)

                # Export button — disabled until a session is loaded
                export_button = (
                    ui.button(
                        "Export to Workspace",
                        icon="upload",
                        on_click=lambda: _handle_export(state),
                    )
                    .classes("w-full mt-4")
                    .props('data-testid="roleplay-export-btn"')
                )
                if _EXPORT_BTN_INITIAL_DISABLED:
                    export_button.disable()
                widgets["export_button"] = export_button

            with ui.expansion("Session Info", icon="info").classes(
                "w-full mt-4 roleplay-upload"
            ):
                ui.label("Log files are saved to: logs/sessions/")

            # Auto-load bundled Becky Bennett character card
            _auto_load_character(state, widgets)
