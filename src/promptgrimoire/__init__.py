"""PromptGrimoire - A collaborative tool for prompt iteration and annotation.

A classroom grimoire for prompt iteration, annotation, and sharing
in educational contexts.
"""

import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from promptgrimoire.config import Settings

__version__ = "0.1.0"

log = structlog.get_logger()


def get_git_commit() -> str:
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
        log.warning("git_commit_unavailable", operation="get_git_commit")
        return "unknown"


def get_version_string() -> str:
    """Get version string with git commit for dev builds."""
    commit = get_git_commit()
    return f"{__version__}+{commit}"


# ---------------------------------------------------------------------------
# Patchable references for _setup_logging (tests override these)
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


def _setup_logging() -> None:
    """Configure structured JSON logging via structlog.

    Sets up:
    - File handler: RotatingFileHandler with JSON output
    - Console handler: human-readable coloured output
    - structlog processor chain with context vars, global
      fields, and level-gated traceback policy
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
    _commit = get_git_commit()

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

    # --- Console handler (human-readable) ---
    # Note: format_exc_info is intentionally omitted here — ConsoleRenderer
    # (via rich) handles exception rendering itself. Including format_exc_info
    # before ConsoleRenderer triggers a UserWarning on every ERROR/CRITICAL log.

    def _drop_null_context_for_console(
        _logger: object,
        _method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        """Strip None context fields from console output (keep in JSON)."""
        for key in ("user_id", "workspace_id", "request_path"):
            if event_dict.get(key) is None:
                event_dict.pop(key, None)
        return event_dict

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[*full_pre_chain, _drop_null_context_for_console],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(
                pad_event_to=60,
                sort_keys=False,
            ),
        ],
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # --- Root stdlib logger ---
    root_logger = logging.getLogger()
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


def _bootstrap_database(db_url: str) -> None:
    """Auto-create branch database, run migrations, seed if new."""
    from promptgrimoire.config import get_current_branch
    from promptgrimoire.db.bootstrap import (
        ensure_database_exists,
        run_alembic_upgrade,
    )

    created = ensure_database_exists(db_url)
    run_alembic_upgrade()  # idempotent

    if created:
        log.info("database_created", action="seeding development data")
        subprocess.run(
            ["uv", "run", "grimoire", "seed", "run"],
            check=False,
        )

    # Log branch + DB info for feature branches
    branch = get_current_branch()
    if branch and branch not in ("main", "master"):
        db_name = db_url.split("?", maxsplit=1)[0].rsplit("/", 1)[-1]
        log.info("branch_config", branch=branch, database=db_name)


def main() -> None:
    """Entry point for the PromptGrimoire application."""
    from nicegui import app, ui

    from promptgrimoire.config import get_settings

    _setup_logging()

    # Serve static JS/CSS assets (e.g. annotation-highlight.js)
    _static_dir = Path(__file__).parent / "static"
    app.add_static_files("/static", str(_static_dir))

    import promptgrimoire.pages

    _ = promptgrimoire.pages  # side-effect import: registers routes

    settings = get_settings()

    if settings.database.url:
        _bootstrap_database(settings.database.url)

    # Database lifecycle hooks (only if DATABASE__URL is configured)
    if settings.database.url:
        import asyncio

        from promptgrimoire.crdt.persistence import (
            get_persistence_manager,
        )
        from promptgrimoire.db import (
            close_db,
            get_engine,
            init_db,
            verify_schema,
        )
        from promptgrimoire.deadline_worker import (
            start_deadline_worker,
        )
        from promptgrimoire.search_worker import start_search_worker

        _search_worker_task: asyncio.Task[None] | None = None
        _deadline_worker_task: asyncio.Task[None] | None = None

        @app.on_startup
        async def startup() -> None:
            nonlocal _search_worker_task, _deadline_worker_task
            await init_db()
            await verify_schema(get_engine())
            _search_worker_task = asyncio.create_task(
                start_search_worker(),
            )
            _deadline_worker_task = asyncio.create_task(
                start_deadline_worker(),
            )
            log.info("database_connected")

        @app.on_shutdown
        async def shutdown() -> None:
            nonlocal _search_worker_task, _deadline_worker_task
            # Cancel background workers before shutdown
            if _search_worker_task is not None:
                _search_worker_task.cancel()
                _search_worker_task = None
            if _deadline_worker_task is not None:
                _deadline_worker_task.cancel()
                _deadline_worker_task = None
            # Persist all dirty CRDT documents before closing DB
            mgr = get_persistence_manager()
            await mgr.persist_all_dirty_workspaces()
            await close_db()

    port = settings.app.port
    storage_secret = settings.app.storage_secret.get_secret_value()

    log.info("app_starting", version=get_version_string(), host="0.0.0.0", port=port)  # noqa: S104 — intentional bind

    ui.run(
        host="0.0.0.0",  # noqa: S104 — intentional bind
        port=port,
        title="Macquarie University Annotation Tool and Prompt Grimoire",
        reload=settings.app.reload,
        show=False,
        storage_secret=storage_secret,
        reconnect_timeout=30.0,
        show_welcome_message=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
