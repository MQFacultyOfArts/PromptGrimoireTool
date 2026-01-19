"""Roleplay chat page for SillyTavern scenario sessions.

Provides a chat interface for roleplay with Claude API,
featuring streaming responses and JSONL logging.

Route: /roleplay
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.llm.client import ClaudeClient
from promptgrimoire.llm.log import JSONLLogger, generate_log_filename
from promptgrimoire.models import Session
from promptgrimoire.parsers.sillytavern import parse_character_card

if TYPE_CHECKING:
    from nicegui.elements.input import Input


# Default log directory
LOG_DIR = Path(os.environ.get("ROLEPLAY_LOG_DIR", "logs/sessions"))


@ui.refreshable
def message_list(session: Session) -> None:
    """Render the conversation messages."""
    for turn in session.turns:
        role_class = "bg-blue-100" if turn.is_user else "bg-gray-100"
        align_class = "ml-auto" if turn.is_user else "mr-auto"

        with ui.card().classes(f"{role_class} {align_class} max-w-3/4 mb-2"):
            ui.label(turn.name).classes("text-sm font-bold text-gray-600")
            ui.markdown(turn.content).classes("text-base")


async def send_message_handler(
    session: Session,
    client: ClaudeClient,
    input_field: Input,
    log_path: Path,
    response_container,
) -> None:
    """Handle sending a user message and streaming the response."""
    user_message = input_field.value
    if not user_message or not user_message.strip():
        return

    # Clear input
    input_field.value = ""

    # Refresh to show user message immediately
    session.add_turn(user_message.strip(), is_user=True)
    message_list.refresh(session)

    # Show streaming indicator
    response_container.clear()
    with response_container:
        streaming_label = ui.label("").classes("text-base")

    # Stream the response
    full_response = ""
    try:
        async for chunk in client.stream_message_only(session, user_message.strip()):
            full_response += chunk
            streaming_label.text = full_response
            streaming_label.update()
    except Exception as e:
        ui.notify(f"Error: {e}", type="negative")
        return

    # Response is already added to session by stream_message_only
    # Refresh to show final message in proper format
    response_container.clear()
    message_list.refresh(session)

    # Log the new turns
    with log_path.open("a") as f:
        logger = JSONLLogger(f)
        # Log the last two turns (user + assistant)
        for turn in session.turns[-2:]:
            logger.write_turn(turn)


@ui.page("/roleplay")
async def roleplay_page() -> None:
    """Roleplay chat page."""
    await ui.context.client.connected()

    # State
    session_holder: dict = {"session": None, "client": None, "log_path": None}

    ui.label("SillyTavern Roleplay").classes("text-h4 mb-4")

    # File upload section
    with ui.card().classes("w-full mb-4") as upload_card:
        ui.label("Load Character Card").classes("text-h6")

        async def handle_upload(e) -> None:
            """Handle character card upload."""
            try:
                # Save uploaded file temporarily
                content = e.content.read()
                tmp_path = Path("/tmp") / e.name
                tmp_path.write_bytes(content)

                # Parse character card
                character, lorebook_entries = parse_character_card(tmp_path)

                # Attach lorebook to character
                character.lorebook_entries = lorebook_entries

                # Create session
                user_name = user_name_input.value or "User"
                session = Session(character=character, user_name=user_name)

                # Add first message if present
                if character.first_mes:
                    session.add_turn(character.first_mes, is_user=False)

                # Create log file
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                log_path = LOG_DIR / generate_log_filename(session)

                # Write header
                with log_path.open("w") as f:
                    logger = JSONLLogger(f)
                    logger.write_header(session)
                    # Log first message if present
                    for turn in session.turns:
                        logger.write_turn(turn)

                # Create Claude client
                try:
                    client = ClaudeClient()
                except ValueError as ve:
                    ui.notify(str(ve), type="negative")
                    return

                # Store state
                session_holder["session"] = session
                session_holder["client"] = client
                session_holder["log_path"] = log_path

                # Hide upload section, show chat
                upload_card.visible = False
                chat_container.visible = True

                # Display character info
                char_name_label.text = character.name
                scenario_label.text = character.scenario or "No scenario provided"

                # Refresh message list
                message_list.refresh(session)

                ui.notify(
                    f"Loaded {character.name} with {len(lorebook_entries)} lorebook entries",
                    type="positive",
                )

            except Exception as ex:
                ui.notify(f"Failed to load character: {ex}", type="negative")

        user_name_input = ui.input(
            label="Your name (used as {{user}})", value="User"
        ).classes("w-64 mb-2")

        ui.upload(
            label="Drop character card JSON here",
            on_upload=handle_upload,
            auto_upload=True,
        ).classes("w-full").props('accept=".json"')

    # Chat section (hidden until character loaded)
    with ui.card().classes("w-full") as chat_container:
        chat_container.visible = False

        # Character header
        with ui.row().classes("w-full items-center mb-4"):
            char_name_label = ui.label("").classes("text-h5")
        scenario_label = ui.label("").classes("text-sm text-gray-600 mb-4")

        # Message container
        with ui.scroll_area().classes("w-full h-96 border rounded"):
            message_list(
                Session(
                    character=__import__(
                        "promptgrimoire.models", fromlist=["Character"]
                    ).Character(name="")
                )
            )

        # Response streaming container
        response_container = ui.row().classes("w-full")

        # Input area
        with ui.row().classes("w-full mt-4"):
            message_input = (
                ui.input(placeholder="Type your message...")
                .classes("flex-grow")
                .props("outlined")
            )

            async def on_send() -> None:
                if session_holder["session"]:
                    await send_message_handler(
                        session_holder["session"],
                        session_holder["client"],
                        message_input,
                        session_holder["log_path"],
                        response_container,
                    )

            ui.button("Send", on_click=on_send).classes("ml-2")

            # Also send on Enter key
            message_input.on("keydown.enter", on_send)

    # Log path display
    with ui.expansion("Session Info", icon="info").classes("w-full mt-4"):
        ui.label("Log files are saved to: logs/sessions/")
