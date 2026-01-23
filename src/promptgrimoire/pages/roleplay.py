"""Roleplay chat page for SillyTavern scenario sessions.

Provides a chat interface for roleplay with Claude API,
featuring streaming responses and JSONL logging.

Route: /roleplay
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from nicegui import app, ui

from promptgrimoire.llm import substitute_placeholders
from promptgrimoire.llm.client import ClaudeClient
from promptgrimoire.llm.log import JSONLLogger, generate_log_filename
from promptgrimoire.models import Character, Session
from promptgrimoire.parsers.sillytavern import parse_character_card

if TYPE_CHECKING:
    from nicegui.elements.input import Input
    from nicegui.elements.scroll_area import ScrollArea

# Default log directory
LOG_DIR = Path(os.environ.get("ROLEPLAY_LOG_DIR", "logs/sessions"))

# Claude model configuration
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# Extended thinking budget (0 = disabled, 1024 = minimal, 10000+ = thorough)
THINKING_BUDGET = int(os.environ.get("CLAUDE_THINKING_BUDGET", "1024"))


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


def _create_chat_message(content: str, name: str, sent: bool) -> None:
    """Create a chat message with markdown-rendered content."""
    msg = ui.chat_message(name=name, sent=sent)
    with msg:
        ui.markdown(content).classes("text-base")


def _render_messages(session: Session, chat_container, scroll_area: ScrollArea) -> None:
    """Render all messages in the session using chat_message components."""
    with chat_container:
        for turn in session.turns:
            _create_chat_message(turn.content, turn.name, turn.is_user)
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
        _create_chat_message(user_message.strip(), session.user_name, sent=True)
    scroll_area.scroll_to(percent=1.0)

    # Show thinking indicator
    with chat_container:
        thinking_msg = ui.chat_message(name=session.character.name, sent=False)
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
        _create_chat_message(full_response, session.character.name, sent=False)
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

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / generate_log_filename(session)

    with log_path.open("w") as f:
        logger = JSONLLogger(f)
        logger.write_header(session)
        for turn in session.turns:
            logger.write_turn(turn)

    client = ClaudeClient(model=CLAUDE_MODEL, thinking_budget=THINKING_BUDGET)
    return session, client, log_path


@ui.page("/roleplay")
async def roleplay_page() -> None:  # noqa: PLR0915 - UI pages have many statements
    """Roleplay chat page."""
    await ui.context.client.connected()

    state: dict = {"session": None, "client": None, "log_path": None}

    ui.label("SillyTavern Roleplay").classes("text-h4 mb-4")

    # Upload section
    with ui.card().classes("w-full mb-4") as upload_card:
        ui.label("Load Character Card").classes("text-h6")

        # CRIT-6: Maximum upload size limit to prevent DoS
        max_upload_size = 100 * 1024 * 1024  # 100 MB

        async def handle_upload(e) -> None:
            tmp_path = None
            try:
                content = await e.file.read()

                # CRIT-6: Check upload size before processing
                if len(content) > max_upload_size:
                    ui.notify("File too large (max 100MB)", type="negative")
                    return

                # Write to temp file for parsing
                tmp_path = Path(f"/tmp/pg_upload_{e.file.name}")
                tmp_path.write_bytes(content)

                character, lorebook_entries = parse_character_card(tmp_path)
                user_name = user_name_input.value or "User"

                session, client, log_path = _setup_session(
                    character, lorebook_entries, user_name
                )

                state["session"] = session
                state["client"] = client
                state["log_path"] = log_path

                upload_card.visible = False
                chat_card.visible = True

                char_name_label.text = character.name
                scenario_label.text = substitute_placeholders(
                    character.scenario or "No scenario",
                    char_name=character.name,
                    user_name=user_name,
                )

                # Render initial messages
                _render_messages(session, chat_container, scroll_area)

                ui.notify(f"Loaded {character.name}")

            except ValueError as ve:
                ui.notify(str(ve), type="negative")
            except Exception as ex:
                ui.notify(f"Failed to load: {ex}", type="negative")
            finally:
                # Clean up temp file
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink()

        user_name_input = ui.input(
            label="Your name (used as {{user}})", value=_get_default_user_name()
        ).classes("w-64 mb-2")

        ui.upload(
            label="Drop character card JSON here",
            on_upload=handle_upload,
            auto_upload=True,
        ).classes("w-full").props('accept=".json"')

    # Chat section
    with ui.card().classes("w-full") as chat_card:
        chat_card.visible = False

        with ui.row().classes("w-full items-center mb-2"):
            char_name_label = ui.label("").classes("text-h5")
        scenario_label = ui.label("").classes("text-sm text-gray-600 mb-4")

        with ui.scroll_area().classes("w-full h-96 border rounded p-4") as scroll_area:
            chat_container = ui.column().classes("w-full gap-3")

        with ui.row().classes("w-full mt-4"):
            message_input = (
                ui.input(placeholder="Type your message...")
                .classes("flex-grow")
                .props("outlined")
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

            send_button = ui.button("Send", on_click=on_send).classes("ml-2")
            message_input.on("keydown.enter", on_send)

    with ui.expansion("Session Info", icon="info").classes("w-full mt-4"):
        ui.label("Log files are saved to: logs/sessions/")
