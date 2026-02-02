"""PromptGrimoire - A collaborative tool for prompt iteration and annotation.

A classroom grimoire for prompt iteration, annotation, and sharing
in educational contexts.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

__version__ = "0.1.0"


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
    from dotenv import load_dotenv
    from nicegui import app, ui

    load_dotenv()
    _setup_logging()

    import promptgrimoire.pages  # noqa: F401 - registers routes

    # Database lifecycle hooks (only if DATABASE_URL is configured)
    if os.environ.get("DATABASE_URL"):
        from promptgrimoire.crdt.persistence import get_persistence_manager
        from promptgrimoire.db import close_db, get_engine, init_db, verify_schema

        @app.on_startup
        async def startup() -> None:
            await init_db()
            await verify_schema(get_engine())
            print("Database connected")

        @app.on_shutdown
        async def shutdown() -> None:
            # Persist all dirty CRDT documents before closing DB
            await get_persistence_manager().persist_all_dirty_workspaces()
            await close_db()

    port = int(os.environ.get("PROMPTGRIMOIRE_PORT", "8080"))
    storage_secret = os.environ.get("STORAGE_SECRET", "dev-secret-change-me")

    print(f"PromptGrimoire v{__version__}")
    print(f"Starting application on http://0.0.0.0:{port}")

    ui.run(host="0.0.0.0", port=port, reload=True, storage_secret=storage_secret)


if __name__ in {"__main__", "__mp_main__"}:
    main()
