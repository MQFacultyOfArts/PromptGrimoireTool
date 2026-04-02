"""Discord webhook alerting processor for structlog.

Sends Discord embeds on ERROR/CRITICAL log events with deduplication
to avoid webhook spam during cascading failures. Fire-and-forget:
webhook POSTs never block the logging pipeline.

All exceptions from the webhook POST are swallowed -- this processor
must never disrupt application logging.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import sys
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import MutableMapping


# Discord embed limits
_TITLE_MAX = 256
_DESCRIPTION_MAX = 4096
_FIELD_VALUE_MAX = 1024

# Colours for embed severity
_COLOUR_ERROR = 15548997  # #ED4245 (red)
_COLOUR_CRITICAL = 10040115  # #992D22 (dark red)

# Context fields to include as embed fields when present and not None
_CONTEXT_FIELDS = (
    "user_id",
    "workspace_id",
    "export_id",
    "request_path",
    "logger",
    "pid",
)


def _truncate(text: str, limit: int) -> str:
    """Truncate text to limit, appending ellipsis if truncated."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _exc_type_name(exc_info: object) -> str:
    """Extract exception type name from exc_info."""
    if isinstance(exc_info, BaseException):
        return type(exc_info).__name__
    if isinstance(exc_info, tuple) and len(exc_info) >= 2 and exc_info[1] is not None:
        return type(exc_info[1]).__name__
    return ""


def _build_diagnostic_commands(
    event_name: str,
    event_dict: MutableMapping[str, Any],
) -> str:
    """Build copy-pasteable diagnostic commands for a Discord alert.

    LaTeX errors get workspace extraction + scp.
    All other errors get collect-telemetry (last 5 min) plus workspace
    extraction if workspace_id is present.
    """
    workspace_id = event_dict.get("workspace_id")
    is_latex = event_name in ("latex_compilation_failed", "latex_subprocess_output")

    lines: list[str] = []

    if is_latex:
        if workspace_id:
            lines.append(f"grimoire-run scripts/extract_workspace.py {workspace_id}")
            lines.append(
                f"scp grimoire.drbbs.org:/tmp/workspace_{workspace_id}.json /tmp/"
            )
    else:
        # General error: collect recent telemetry
        lines.append(
            "sudo deploy/collect-telemetry.sh --start \"$(date -d '5 minutes ago' "
            "'+%Y-%m-%d %H:%M')\" --end \"$(date '+%Y-%m-%d %H:%M')\"",
        )
        if workspace_id:
            lines.append(f"grimoire-run scripts/extract_workspace.py {workspace_id}")
            lines.append(
                f"scp grimoire.drbbs.org:/tmp/workspace_{workspace_id}.json /tmp/"
            )

    return "\n".join(lines)


class DiscordAlertProcessor:
    """structlog processor that POSTs Discord embeds on ERROR/CRITICAL.

    Deduplicates by (exception_type, logger_name) within a configurable
    time window to prevent webhook spam during cascading failures.

    Args:
        webhook_url: Discord webhook URL. Empty string disables alerting.
        dedup_window_seconds: Minimum seconds between alerts for the same
            (exception_type, logger_name) pair. Default: 60.
    """

    def __init__(
        self,
        webhook_url: str,
        dedup_window_seconds: float = 60.0,
    ) -> None:
        self._webhook_url = webhook_url
        self._dedup_window = dedup_window_seconds
        self._recent: dict[tuple[str, str], float] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()

    def __call__(
        self,
        _logger: object,
        _method_name: str,
        event_dict: MutableMapping[str, Any],
    ) -> MutableMapping[str, Any]:
        """Process a log event, firing a Discord alert for ERROR/CRITICAL."""
        with contextlib.suppress(Exception):
            self._process(event_dict)
        return event_dict

    def _process(
        self,
        event_dict: MutableMapping[str, Any],
    ) -> None:
        """Internal processing -- may raise, caller catches all."""
        if not self._webhook_url:
            return

        # Never alert during test runs
        if os.environ.get("GRIMOIRE_TEST_HARNESS"):
            return

        level = event_dict.get("level", "")
        if level not in ("error", "critical"):
            return

        # Deduplication key: (exc_type, logger_name)
        exc_info = event_dict.get("exc_info")
        exc_type = _exc_type_name(exc_info) if exc_info else ""
        logger_name = str(event_dict.get("logger", ""))
        dedup_key = (exc_type, logger_name)

        now = time.monotonic()
        last_sent = self._recent.get(dedup_key)
        if last_sent is not None and (now - last_sent) < self._dedup_window:
            return

        # Build payload
        payload = self._build_payload(level, event_dict)

        # Fire and forget
        self._fire_and_forget(payload)

        # Update dedup timestamp
        self._recent[dedup_key] = now

    def _build_payload(
        self,
        level: str,
        event_dict: MutableMapping[str, Any],
    ) -> dict[str, Any]:
        """Build Discord webhook payload with embed."""
        event_name = str(event_dict.get("event", "unknown"))
        title = _truncate(f"[{level.upper()}] {event_name}", _TITLE_MAX)

        colour = _COLOUR_CRITICAL if level == "critical" else _COLOUR_ERROR

        # Description from exception info
        description = ""
        exc_info = event_dict.get("exc_info")
        if exc_info is not None:
            if isinstance(exc_info, BaseException):
                description = f"{type(exc_info).__name__}: {exc_info}"
            elif (
                isinstance(exc_info, tuple)
                and len(exc_info) >= 2
                and exc_info[1] is not None
            ):
                description = f"{type(exc_info[1]).__name__}: {exc_info[1]}"
            else:
                description = str(exc_info)
            description = _truncate(description, _DESCRIPTION_MAX)

        # Context fields
        fields: list[dict[str, Any]] = [
            {
                "name": "server",
                "value": socket.gethostname(),
                "inline": True,
            },
        ]
        for key in _CONTEXT_FIELDS:
            value = event_dict.get(key)
            if value is not None:
                fields.append(
                    {
                        "name": key,
                        "value": _truncate(str(value), _FIELD_VALUE_MAX),
                        "inline": True,
                    }
                )

        # Diagnostic commands for the alert recipient
        diag_commands = _build_diagnostic_commands(event_name, event_dict)
        if diag_commands:
            fields.append(
                {
                    "name": "diagnostic commands",
                    "value": _truncate(diag_commands, _FIELD_VALUE_MAX),
                    "inline": False,
                }
            )

        embed: dict[str, Any] = {
            "title": title,
            "color": colour,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if description:
            embed["description"] = description
        if fields:
            embed["fields"] = fields

        return {"embeds": [embed]}

    def _fire_and_forget(self, payload: dict[str, Any]) -> None:
        """Dispatch webhook POST without blocking the log pipeline."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._send_webhook(payload))
            # Hold a reference so the task is not garbage-collected
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            # No running event loop -- use a daemon thread
            thread = threading.Thread(
                target=asyncio.run,
                args=(self._send_webhook(payload),),
                daemon=True,
            )
            thread.start()

    async def _send_webhook(self, payload: dict[str, Any]) -> None:
        """POST payload to Discord webhook. Swallows all exceptions."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self._webhook_url, json=payload)
                if response.status_code == 429:
                    sys.stderr.write(
                        f"Discord webhook rate-limited (429) for {self._webhook_url}\n"
                    )
                elif response.status_code >= 400:
                    url = self._webhook_url
                    code = response.status_code
                    sys.stderr.write(f"Discord webhook returned {code} for {url}\n")
        except Exception:  # noqa: S110 -- intentional: webhook failures must never propagate (AC5.4)
            pass
