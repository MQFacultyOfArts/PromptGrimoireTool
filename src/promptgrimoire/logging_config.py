"""Shared logging configuration for PromptGrimoire.

Extracted from ``__init__.py`` so that both the NiceGUI app and the
standalone export worker can initialise structured logging without
importing NiceGUI.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

    from promptgrimoire.config import Settings


# ---------------------------------------------------------------------------
# Patchable references (tests override these)
# ---------------------------------------------------------------------------
def _get_settings_for_logging() -> Settings:
    """Return settings; exists as a seam for test patching."""
    from promptgrimoire.config import get_settings

    return get_settings()


def _get_current_branch_for_logging() -> str | None:
    """Return current branch; exists as a seam for test patching."""
    from promptgrimoire.config import get_current_branch

    return get_current_branch()


def _branch_db_suffix_for_logging(
    branch: str | None,
) -> str:
    """Return branch DB suffix; seam for test patching."""
    from promptgrimoire.config import _branch_db_suffix

    return _branch_db_suffix(branch)


def _get_git_commit() -> str:
    """Get the short git commit hash, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return "unknown"


# Fields that only belong in JSON file output, not dev console.
_CONSOLE_STRIP_KEYS = frozenset(
    {
        "pid",
        "branch",
        "commit",
        "timestamp",
        "user_id",
        "workspace_id",
        "request_path",
    }
)


def _clean_for_console(
    _logger: object,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Strip global/null fields from console; keep in JSON file."""
    for key in _CONSOLE_STRIP_KEYS:
        val = event_dict.get(key)
        if val is None or key in ("pid", "branch", "commit", "timestamp"):
            event_dict.pop(key, None)
    return event_dict


def setup_logging() -> None:
    """Configure structured JSON logging via structlog.

    Sets up:
    - File handler: RotatingFileHandler with JSON output
    - Console handler: human-readable coloured output
    - structlog processor chain with context vars, global
      fields, and level-gated traceback policy

    Safe to call from both the NiceGUI app and standalone worker
    processes.  Does NOT import NiceGUI.
    """
    settings = _get_settings_for_logging()
    log_dir: Path = settings.app.log_dir

    # Derive branch-isolated log file path
    branch = _get_current_branch_for_logging()
    suffix = _branch_db_suffix_for_logging(branch)
    if suffix:
        log_file = log_dir / f"promptgrimoire-{suffix}.jsonl"
    else:
        log_file = log_dir / "promptgrimoire.jsonl"

    log_dir.mkdir(parents=True, exist_ok=True)

    # --- Shared pre-chain for foreign (stdlib) log records ---
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    # --- Custom processors ---
    # Compute global fields once at startup
    _pid = os.getpid()
    _branch = branch
    _commit = _get_git_commit()

    def add_global_fields(
        _logger: object,
        _method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        event_dict.setdefault("pid", _pid)
        event_dict.setdefault("branch", _branch)
        event_dict.setdefault("commit", _commit)
        return event_dict

    def ensure_null_context(
        _logger: object,
        _method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        """AC7.3: Set context fields to None if not bound."""
        for key in ("user_id", "workspace_id", "request_path"):
            event_dict.setdefault(key, None)
        return event_dict

    def level_gated_traceback(
        _logger: object,
        _method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        """AC7.1/AC7.2: Strip exc_info for DEBUG/INFO."""
        level = event_dict.get("level", "")
        if level in ("debug", "info"):
            event_dict.pop("exc_info", None)
        return event_dict

    # Full pre-chain used by both handlers and structlog.configure
    full_pre_chain: list[structlog.types.Processor] = [
        *shared_processors,
        add_global_fields,
        ensure_null_context,
        level_gated_traceback,
    ]

    # --- File handler (JSON) ---
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=full_pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Set file permissions to 0o644
    log_file.chmod(0o644)

    # --- Console handler ---
    # Under systemd (no TTY), use JSONRenderer so journal entries are
    # machine-parseable and free of ANSI escapes, rich box-drawing, and
    # local-variable dumps (which leak student PII via show_locals=True).
    # Under a TTY (dev), keep ConsoleRenderer for human readability but
    # disable show_locals to avoid PII in local variable dumps.
    if sys.stderr.isatty():
        console_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[
                *shared_processors,
                add_global_fields,
                level_gated_traceback,
                _clean_for_console,
            ],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _clean_for_console,
                structlog.dev.ConsoleRenderer(
                    sort_keys=False,
                    exception_formatter=structlog.dev.RichTracebackFormatter(
                        show_locals=False,
                    ),
                ),
            ],
        )
    else:
        console_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=full_pre_chain,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
        )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # --- Root stdlib logger ---
    # Clear any pre-existing handlers (e.g. from uvicorn's LOGGING_CONFIG
    # dictConfig call during reload, or NiceGUI's default setup) to prevent
    # duplicate output with raw dict formatting.
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # --- Discord webhook alerting processor ---
    from promptgrimoire.logging_discord import DiscordAlertProcessor

    discord_processor = DiscordAlertProcessor(
        webhook_url=settings.alerting.discord_webhook_url,
    )

    # --- structlog configuration ---
    structlog.configure(
        processors=[
            *full_pre_chain,
            discord_processor,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.info(
        "Structured logging configured. Log file: %s",
        log_file.absolute(),
    )
