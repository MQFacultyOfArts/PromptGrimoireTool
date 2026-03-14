"""Log viewer page for inspecting roleplay session logs.

Displays JSONL session logs with hidden metadata visible,
including lorebook activations and reasoning traces.

Route: /logs
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import structlog
from nicegui import ui

from promptgrimoire.config import get_settings
from promptgrimoire.pages.layout import require_roleplay_enabled
from promptgrimoire.pages.registry import page_route
from promptgrimoire.pages.roleplay_access import require_roleplay_page_access

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)


def parse_log_file(path: Path) -> tuple[dict | None, list[dict]]:
    """Parse a JSONL log file into header and turns.

    Args:
        path: Path to the JSONL file.

    Returns:
        Tuple of (header_dict, list_of_turn_dicts).
        Header may be None if file has no header line.
    """
    header = None
    turns = []

    with path.open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                # Header has character_name but no 'mes' field
                if "character_name" in data and "mes" not in data:
                    header = data
                else:
                    turns.append(data)
            except json.JSONDecodeError:
                logger.warning(
                    "jsonl_line_parse_failed",
                    operation="parse_jsonl",
                    line_number=len(turns) + 1,
                )
                continue

    return header, turns


def _render_metadata(extra: dict) -> None:
    """Render turn metadata in an expansion panel."""
    if "model" in extra:
        ui.label(f"Model: {extra['model']}").classes("text-sm")

    if "activated_lorebook" in extra:
        activated = extra["activated_lorebook"]
        if activated:
            ui.label("Activated Lorebook Entries:").classes("text-sm font-bold mt-2")
            for entry_name in activated:
                ui.label(f"  - {entry_name}").classes("text-sm text-green-700")
        else:
            ui.label("No lorebook entries activated").classes("text-sm text-gray-500")

    if "reasoning" in extra:
        ui.label("Reasoning Trace:").classes("text-sm font-bold mt-2")
        with ui.card().classes("w-full bg-yellow-50 p-2"):
            # HIGH-1: Render as preformatted text to prevent XSS from LLM output
            ui.label(extra["reasoning"]).classes(
                "text-sm whitespace-pre-wrap font-mono"
            )


def _render_turn(i: int, turn: dict) -> None:
    """Render a single conversation turn."""
    is_user = turn.get("is_user", False)
    name = turn.get("name", "Unknown")
    content = turn.get("mes", "")
    extra = turn.get("extra", {})

    bg_class = "bg-blue-100" if is_user else "bg-gray-100"

    with ui.card().classes(f"w-full mb-2 {bg_class}"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"#{i + 1} {name}").classes("font-bold")
            if turn.get("send_date"):
                ui.label(turn["send_date"]).classes("text-sm text-gray-500")

        ui.markdown(content).classes("text-base my-2")

        if extra:
            with ui.expansion("Metadata", icon="info").classes("w-full"):
                _render_metadata(extra)


def _list_log_files(log_dir: Path) -> list[Path]:
    """Return available JSONL log files, newest first."""
    if not log_dir.exists():
        return []
    return sorted(
        log_dir.glob("*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _build_log_selector(
    log_dir: Path,
    log_files: list[Path],
    state: dict,
    refresh_log_content,
) -> None:
    """Render the log file selector and hook it to the refreshable viewer."""
    with ui.card().classes("w-full mb-4"):
        ui.label("Select Session Log").classes("text-h6 mb-2")

        file_options = {str(path): path.name for path in log_files}

        def on_select(e) -> None:
            requested_path = Path(e.value).resolve()
            safe_base = log_dir.resolve()
            if not requested_path.is_relative_to(safe_base):
                logger.warning("Path traversal attempt blocked: %s", e.value)
                ui.notify("Invalid log file path", type="negative")
                return

            header, turns = parse_log_file(requested_path)
            state["selected_path"] = requested_path
            state["header"] = header
            state["turns"] = turns
            refresh_log_content.refresh()

        ui.select(options=file_options, on_change=on_select, label="Log file").classes(
            "w-full"
        )


def _render_log_content(state: dict) -> None:
    """Render the currently selected log file contents."""
    if not state["selected_path"]:
        ui.label("Select a log file to view").classes("text-gray-500")
        return

    header = state["header"]
    turns = state["turns"]

    if header:
        with ui.card().classes("w-full mb-4 bg-blue-50"):
            ui.label("Session Info").classes("text-h6 mb-2")
            with ui.row().classes("gap-4"):
                char_name = header.get("character_name", "Unknown")
                ui.label(f"Character: {char_name}").classes("font-bold")
                ui.label(f"User: {header.get('user_name', 'Unknown')}")
                ui.label(f"Date: {header.get('create_date', 'Unknown')}")

    ui.label(f"Messages ({len(turns)})").classes("text-h6 mb-2")

    for i, turn in enumerate(turns):
        _render_turn(i, turn)


def _render_log_viewer(log_dir: Path) -> None:
    """Render the standalone session log viewer."""
    ui.label("Session Log Viewer").classes("text-h4 mb-4")

    state: dict = {"selected_path": None, "header": None, "turns": []}
    log_files = _list_log_files(log_dir)
    if not log_files:
        ui.label("No log files found in logs/sessions/").classes("text-gray-500")
        return

    @ui.refreshable
    def log_content() -> None:
        _render_log_content(state)

    _build_log_selector(log_dir, log_files, state, log_content)

    with ui.card().classes("w-full"):
        log_content()


@page_route(
    "/logs", title="Session Logs", icon="description", order=40, requires_roleplay=True
)
async def logs_page() -> None:
    """Log viewer page."""
    await ui.context.client.connected()

    # Feature flag guard -- require roleplay enabled
    if not require_roleplay_enabled():
        return
    if not require_roleplay_page_access():
        return
    _render_log_viewer(get_settings().app.log_dir)
