"""PromptGrimoire - A collaborative tool for prompt iteration and annotation.

A classroom grimoire for prompt iteration, annotation, and sharing
in educational contexts.
"""

import logging
import os
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path

__version__ = "0.1.0"


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
        return "unknown"


def get_version_string() -> str:
    """Get version string with git commit for dev builds."""
    commit = get_git_commit()
    return f"{__version__}+{commit}"


def _setup_logging() -> None:
    """Configure logging to both console and rotating file."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"promptgrimoire.{os.getpid()}.log"

    # Root logger config
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # File handler - detailed logging with rotation (10MB, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # Console handler - less verbose
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info("Logging configured. Log file: %s", log_file.absolute())


def main() -> None:
    """Entry point for the PromptGrimoire application."""
    from nicegui import app, ui

    from promptgrimoire.config import get_settings

    _setup_logging()

    # Serve static JS/CSS assets (e.g. annotation-highlight.js)
    _static_dir = Path(__file__).parent / "static"
    app.add_static_files("/static", str(_static_dir))

    import promptgrimoire.pages  # noqa: F401 - registers routes

    settings = get_settings()

    # Auto-create branch database, run migrations, seed if new.
    # Note: run_alembic_upgrade() internally calls ensure_database_exists() again,
    # but that second call is idempotent (DB already exists, returns False).
    # We call ensure_database_exists() separately here to capture the "created"
    # bool for conditional seeding.
    if settings.database.url:
        from promptgrimoire.config import get_current_branch
        from promptgrimoire.db.bootstrap import (
            ensure_database_exists,
            run_alembic_upgrade,
        )

        created = ensure_database_exists(settings.database.url)
        run_alembic_upgrade()  # idempotent — ensures schema is current

        if created:
            print("Created database — seeding development data...")
            subprocess.run(["uv", "run", "seed-data"], check=False)

        # Print branch + DB info for feature branches
        branch = get_current_branch()
        if branch and branch not in ("main", "master"):
            db_name = settings.database.url.split("?")[0].rsplit("/", 1)[-1]
            print(f"Branch: {branch} | Database: {db_name}")

    # Database lifecycle hooks (only if DATABASE__URL is configured)
    if settings.database.url:
        import asyncio

        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db import close_db, get_engine, init_db, verify_schema
        from promptgrimoire.search_worker import start_search_worker

        _search_worker_task: asyncio.Task[None] | None = None

        @app.on_startup
        async def startup() -> None:
            nonlocal _search_worker_task
            await init_db()
            await verify_schema(get_engine())
            _search_worker_task = asyncio.create_task(start_search_worker())
            print("Database connected")

        @app.on_shutdown
        async def shutdown() -> None:
            nonlocal _search_worker_task
            # Cancel search worker before shutdown
            if _search_worker_task is not None:
                _search_worker_task.cancel()
                _search_worker_task = None
            # Persist all dirty CRDT documents before closing DB
            await get_persistence_manager().persist_all_dirty_workspaces()
            await close_db()

    port = settings.app.port
    storage_secret = settings.app.storage_secret.get_secret_value()

    print(f"PromptGrimoire v{get_version_string()}")
    print(f"Starting application on http://0.0.0.0:{port}")

    reload = os.environ.get("PROMPTGRIMOIRE_RELOAD", "1") != "0"
    ui.run(host="0.0.0.0", port=port, reload=reload, storage_secret=storage_secret)  # nosec B104


if __name__ in {"__main__", "__mp_main__"}:
    main()
