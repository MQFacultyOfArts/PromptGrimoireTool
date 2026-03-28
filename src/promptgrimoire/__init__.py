"""PromptGrimoire - A collaborative tool for prompt iteration and annotation.

A classroom grimoire for prompt iteration, annotation, and sharing
in educational contexts.
"""

import hmac
import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID as _UUID

import structlog
from starlette.requests import (
    Request,  # noqa: TC002 -- used in kick_user_handler signature at runtime
)
from starlette.responses import JSONResponse

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


async def kick_user_handler(request: Request) -> JSONResponse:
    """Kick a banned user's connected clients.

    POST /api/admin/kick — requires Bearer token matching
    ADMIN__ADMIN_API_SECRET.
    """
    from promptgrimoire.config import get_settings

    secret = get_settings().admin.admin_api_secret.get_secret_value()
    if not secret:
        return JSONResponse(
            {"error": "ADMIN_API_SECRET not configured"},
            status_code=503,
        )

    # Validate bearer token (case-insensitive scheme per RFC 7235)
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    token = auth_header[len("bearer ") :]
    if not hmac.compare_digest(token, secret):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    # Parse user_id from body
    try:
        body = await request.json()
        user_id = _UUID(body["user_id"])
    except KeyError, ValueError, TypeError:
        log.warning(
            "kick_invalid_user_id",
            reason="missing or malformed user_id",
        )
        return JSONResponse({"error": "Invalid or missing user_id"}, status_code=400)

    # Check ban state (DB is source of truth)
    from promptgrimoire.auth.client_registry import disconnect_user
    from promptgrimoire.db.users import is_user_banned

    if await is_user_banned(user_id):
        kicked = await disconnect_user(user_id)
        return JSONResponse({"kicked": kicked, "was_banned": True})

    return JSONResponse({"kicked": 0, "was_banned": False})


def _register_db_lifecycle(app: object) -> None:
    """Register database startup/shutdown hooks and background workers.

    Extracted from main() to keep statement count within linter limits.
    """
    import asyncio

    from nicegui import app as _app_module

    # Narrow the type so that .on_startup / .on_shutdown are visible
    assert isinstance(app, type(_app_module))  # noqa: S101 — runtime guard

    from promptgrimoire.config import get_settings
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
    from promptgrimoire.diagnostics import (
        invalidate_sessions_on_disk,
        start_diagnostic_logger,
    )
    from promptgrimoire.export.worker import start_export_worker
    from promptgrimoire.search_worker import start_search_worker

    _search_worker_task: asyncio.Task[None] | None = None
    _deadline_worker_task: asyncio.Task[None] | None = None
    _export_worker_task: asyncio.Task[None] | None = None
    _diagnostic_logger_task: asyncio.Task[None] | None = None

    @app.on_startup
    async def startup() -> None:
        nonlocal \
            _search_worker_task, \
            _deadline_worker_task, \
            _export_worker_task, \
            _diagnostic_logger_task
        # Clear stale sessions from disk before accepting connections.
        # Guarantees clean auth state regardless of how the previous
        # process died (SIGTERM, OOM, crash, bare systemctl restart).
        invalidate_sessions_on_disk()
        await init_db()
        await verify_schema(get_engine())
        _search_worker_task = asyncio.create_task(
            start_search_worker(),
        )
        _deadline_worker_task = asyncio.create_task(
            start_deadline_worker(),
        )
        _export_worker_task = asyncio.create_task(
            start_export_worker(),
        )
        _app_config = get_settings().app
        _diagnostic_logger_task = asyncio.create_task(
            start_diagnostic_logger(
                interval_seconds=_app_config.diagnostic_interval_seconds,
                memory_restart_threshold_mb=_app_config.memory_restart_threshold_mb,
            ),
        )
        log.info("database_connected")

    @app.on_shutdown
    async def shutdown() -> None:
        nonlocal \
            _search_worker_task, \
            _deadline_worker_task, \
            _export_worker_task, \
            _diagnostic_logger_task
        # Cancel background workers and await completion before DB teardown
        tasks_to_cancel: list[asyncio.Task[None]] = []
        if _search_worker_task is not None:
            _search_worker_task.cancel()
            tasks_to_cancel.append(_search_worker_task)
            _search_worker_task = None
        if _deadline_worker_task is not None:
            _deadline_worker_task.cancel()
            tasks_to_cancel.append(_deadline_worker_task)
            _deadline_worker_task = None
        if _export_worker_task is not None:
            _export_worker_task.cancel()
            tasks_to_cancel.append(_export_worker_task)
            _export_worker_task = None
        if _diagnostic_logger_task is not None:
            _diagnostic_logger_task.cancel()
            tasks_to_cancel.append(_diagnostic_logger_task)
            _diagnostic_logger_task = None
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        # Persist all dirty CRDT documents before closing DB
        mgr = get_persistence_manager()
        await mgr.persist_all_dirty_workspaces()
        await close_db()


def _install_session_identity_tracing() -> None:
    """Monkey-patch RequestTrackingMiddleware to log identity at middleware level.

    Wraps ``call_next`` inside the existing dispatch so that every HTTP
    request logs the session_id and asyncio task name *before* the page
    handler background task is created.  Comparing this log with the
    ``h7_page_identity`` log from ``page_route`` detects context
    contamination (#438 / H7).
    """
    import asyncio as _asyncio
    from typing import Any

    from nicegui.storage import RequestTrackingMiddleware

    _original_dispatch = RequestTrackingMiddleware.dispatch

    async def _instrumented_dispatch(
        self: Any,
        request: Request,
        call_next: Any,
    ) -> Any:
        async def _logging_call_next(req: Request) -> Any:
            task = _asyncio.current_task()
            task_name = task.get_name() if task else "no-task"
            session_id = req.session.get("id", "missing")
            path = str(req.url.path)
            # Skip noisy paths — only log page routes
            if not path.startswith(("/static/", "/_nicegui", "/healthz")):
                log.info(
                    "session_identity_at_middleware",
                    ctx_session_id=session_id,
                    task_name=task_name,
                    path=path,
                )
            return await call_next(req)

        return await _original_dispatch(self, request, _logging_call_next)

    RequestTrackingMiddleware.dispatch = _instrumented_dispatch  # ty: ignore[invalid-assignment]
    log.info("session_identity_tracing_installed")


def main() -> None:
    """Entry point for the PromptGrimoire application."""
    from nicegui import app, ui

    from promptgrimoire.config import get_settings

    _setup_logging()

    # Serve static JS/CSS assets (e.g. annotation-highlight.js)
    _static_dir = Path(__file__).parent / "static"
    app.add_static_files("/static", str(_static_dir))

    import promptgrimoire.export.download
    import promptgrimoire.pages

    _ = promptgrimoire.pages  # side-effect import: registers routes
    _ = (
        promptgrimoire.export.download
    )  # side-effect import: registers /export/{token}/download route

    # Health check endpoint for UptimeRobot (HEAD + GET)
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def healthz(_request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app.routes.insert(0, Route("/healthz", healthz, methods=["GET", "HEAD"]))

    # Admin kick endpoint for banning users in real time
    app.routes.insert(0, Route("/api/admin/kick", kick_user_handler, methods=["POST"]))

    # Pre-restart flush and connection-count endpoints for zero-downtime deploy
    from promptgrimoire.pages.restart import (
        connection_count_handler,
        pre_restart_handler,
    )

    app.routes.insert(
        0, Route("/api/pre-restart", pre_restart_handler, methods=["POST"])
    )
    app.routes.insert(
        0, Route("/api/connection-count", connection_count_handler, methods=["GET"])
    )

    settings = get_settings()

    if settings.database.url:
        _bootstrap_database(settings.database.url)

    # Database lifecycle hooks (only if DATABASE__URL is configured)
    if settings.database.url:
        _register_db_lifecycle(app)

    port = settings.app.port
    storage_secret = settings.app.storage_secret.get_secret_value()

    # --- Session identity tracing (#438) ---
    # Monkey-patch RequestTrackingMiddleware to log the session_id at the
    # middleware layer. This gives us a baseline to compare against the
    # page_route log (which runs in a separate asyncio Task).
    _install_session_identity_tracing()

    log.info("app_starting", version=get_version_string(), host="0.0.0.0", port=port)  # noqa: S104 — intentional bind

    ui.run(
        host="0.0.0.0",  # noqa: S104 — intentional bind
        port=port,
        title="Macquarie University Annotation Tool and Prompt Grimoire",
        reload=settings.app.reload,
        show=False,
        storage_secret=storage_secret,
        reconnect_timeout=15.0,
        show_welcome_message=False,
        log_config=None,  # Prevent uvicorn from overwriting our structlog config
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
