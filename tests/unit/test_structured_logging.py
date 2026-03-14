"""Tests for structured logging setup.

Verifies ACs:
- AC6.1: Branch-isolated log file, RotatingFileHandler config
- AC6.2: Log file permissions 0o644
- AC6.3: Each line is valid JSON
- AC6.4: Append mode (no clobber on restart)
- AC6.5: File naming with branch slug
- AC7.1: DEBUG/INFO suppress traceback
- AC7.2: WARNING+ include traceback
- AC7.3: Null context fields when unbound
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import stat
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import structlog

if TYPE_CHECKING:
    from pathlib import Path


def _reset_logging() -> None:
    """Remove all handlers from root logger and reset structlog."""
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def _clean_logging():
    """Ensure logging state is clean before and after each test."""
    _reset_logging()
    yield
    _reset_logging()


def _call_setup_logging(
    tmp_path: Path,
    branch: str | None = None,
) -> Path:
    """Call _setup_logging with patched settings pointing to tmp_path.

    Returns the log directory path.
    """
    from promptgrimoire import _setup_logging
    from promptgrimoire.config import (
        AppConfig,
        DevConfig,
        Settings,
        _branch_db_suffix,
    )

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app=AppConfig(log_dir=tmp_path),
        dev=DevConfig(branch_db_suffix=False),
    )
    with (
        patch(
            "promptgrimoire._get_settings_for_logging",
            return_value=settings,
        ),
        patch(
            "promptgrimoire._get_current_branch_for_logging",
            return_value=branch,
        ),
        patch(
            "promptgrimoire._branch_db_suffix_for_logging",
            side_effect=_branch_db_suffix,
        ),
    ):
        _setup_logging()
    return tmp_path


class TestLogFilePath:
    """AC6.1 and AC6.5: Log file path and rotation."""

    def test_main_branch_produces_promptgrimoire_jsonl(
        self,
        tmp_path: Path,
    ) -> None:
        """AC6.5: Empty suffix -> promptgrimoire.jsonl."""
        _call_setup_logging(tmp_path, branch="main")
        assert (tmp_path / "promptgrimoire.jsonl").exists()

    def test_feature_branch_produces_slugged_filename(
        self,
        tmp_path: Path,
    ) -> None:
        """AC6.5: Branch suffix -> promptgrimoire-{slug}.jsonl."""
        _call_setup_logging(
            tmp_path,
            branch="structured-logging-339",
        )
        expected = tmp_path / "promptgrimoire-structured_logging_339.jsonl"
        assert expected.exists()

    def test_none_branch_produces_promptgrimoire_jsonl(
        self,
        tmp_path: Path,
    ) -> None:
        """AC6.5: None branch -> promptgrimoire.jsonl."""
        _call_setup_logging(tmp_path, branch=None)
        assert (tmp_path / "promptgrimoire.jsonl").exists()

    def test_rotating_file_handler_config(
        self,
        tmp_path: Path,
    ) -> None:
        """AC6.1: RotatingFileHandler with 10MB max, 5 backups."""
        _call_setup_logging(tmp_path)
        root = logging.getLogger()
        rotating_handlers = [
            h
            for h in root.handlers
            if isinstance(
                h,
                logging.handlers.RotatingFileHandler,
            )
        ]
        assert len(rotating_handlers) == 1
        handler = rotating_handlers[0]
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5


class TestLogFilePermissions:
    """AC6.2: Log file permissions."""

    def test_log_file_has_644_permissions(
        self,
        tmp_path: Path,
    ) -> None:
        """AC6.2: Log file permissions are 0o644."""
        _call_setup_logging(tmp_path)
        log_file = tmp_path / "promptgrimoire.jsonl"
        assert log_file.exists()
        mode = stat.S_IMODE(log_file.stat().st_mode)
        assert mode == 0o644


class TestJsonOutput:
    """AC6.3: Each line is valid JSON."""

    def test_stdlib_logger_produces_valid_json(
        self,
        tmp_path: Path,
    ) -> None:
        """AC6.3: stdlib logger output is valid JSON."""
        _call_setup_logging(tmp_path)
        logger = logging.getLogger("test.stdlib")
        logger.info("test event from stdlib")

        # Flush handlers
        for h in logging.getLogger().handlers:
            h.flush()

        log_file = tmp_path / "promptgrimoire.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        assert len(lines) >= 1
        parsed = json.loads(lines[-1])
        assert parsed["event"] == "test event from stdlib"

    def test_structlog_logger_produces_valid_json(
        self,
        tmp_path: Path,
    ) -> None:
        """AC6.3: structlog logger output is valid JSON."""
        _call_setup_logging(tmp_path)
        logger = structlog.get_logger("test.structlog")
        logger.info("test event from structlog")

        for h in logging.getLogger().handlers:
            h.flush()

        log_file = tmp_path / "promptgrimoire.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        assert len(lines) >= 1
        parsed = json.loads(lines[-1])
        assert parsed["event"] == "test event from structlog"


class TestAppendMode:
    """AC6.4: Append mode, no clobber on restart."""

    def test_second_setup_appends_not_clobbers(
        self,
        tmp_path: Path,
    ) -> None:
        """AC6.4: _setup_logging twice appends to same file."""
        _call_setup_logging(tmp_path)
        logger = logging.getLogger("test.append")
        logger.info("first message")
        for h in logging.getLogger().handlers:
            h.flush()

        log_file = tmp_path / "promptgrimoire.jsonl"
        first_count = len(
            [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        )

        # Reset and call again
        _reset_logging()
        _call_setup_logging(tmp_path)
        logger2 = logging.getLogger("test.append2")
        logger2.info("second message")
        for h in logging.getLogger().handlers:
            h.flush()

        second_count = len(
            [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        )
        assert second_count > first_count


class TestTracebackPolicy:
    """AC7.1 and AC7.2: Level-gated traceback."""

    def test_info_inside_except_has_no_traceback(
        self,
        tmp_path: Path,
    ) -> None:
        """AC7.1: INFO log inside except has no traceback."""
        _call_setup_logging(tmp_path)
        logger = logging.getLogger("test.traceback")
        try:
            raise ValueError("test error")
        except ValueError:
            logger.info("handled the error", exc_info=True)

        for h in logging.getLogger().handlers:
            h.flush()

        log_file = tmp_path / "promptgrimoire.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        last_line = json.loads(lines[-1])
        assert "exc_info" not in last_line
        assert "traceback" not in last_line
        assert "Traceback" not in last_line.get("event", "")

    def test_error_inside_except_has_traceback(
        self,
        tmp_path: Path,
    ) -> None:
        """AC7.2: ERROR log inside except includes traceback."""
        _call_setup_logging(tmp_path)
        logger = logging.getLogger("test.traceback")
        try:
            raise ValueError("test error for traceback")
        except ValueError:
            logger.error("something went wrong", exc_info=True)

        for h in logging.getLogger().handlers:
            h.flush()

        log_file = tmp_path / "promptgrimoire.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        last_line = json.loads(lines[-1])
        # Traceback should be present in some form
        has_traceback = (
            "exc_info" in last_line
            or "traceback" in last_line
            or "Traceback" in json.dumps(last_line)
        )
        assert has_traceback


class TestNullContextFields:
    """AC7.3: Context fields are null when unavailable."""

    def test_null_context_fields_stdlib(
        self,
        tmp_path: Path,
    ) -> None:
        """AC7.3: user_id etc. are null when unbound."""
        _call_setup_logging(tmp_path)
        logger = logging.getLogger("test.context")
        logger.info("no context bound")

        for h in logging.getLogger().handlers:
            h.flush()

        log_file = tmp_path / "promptgrimoire.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        parsed = json.loads(lines[-1])
        assert parsed["user_id"] is None
        assert parsed["workspace_id"] is None
        assert parsed["request_path"] is None

    def test_null_context_fields_structlog(
        self,
        tmp_path: Path,
    ) -> None:
        """AC7.3: null context fields with structlog logger."""
        _call_setup_logging(tmp_path)
        logger = structlog.get_logger("test.context.structlog")
        logger.info("no context bound structlog")

        for h in logging.getLogger().handlers:
            h.flush()

        log_file = tmp_path / "promptgrimoire.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        parsed = json.loads(lines[-1])
        assert parsed["user_id"] is None
        assert parsed["workspace_id"] is None
        assert parsed["request_path"] is None


class TestGlobalFields:
    """Verify pid, branch, commit are present in output."""

    def test_global_fields_present(
        self,
        tmp_path: Path,
    ) -> None:
        """Global fields pid, branch, commit in every log line."""
        _call_setup_logging(tmp_path, branch="test-branch")
        logger = logging.getLogger("test.global")
        logger.info("check fields")

        for h in logging.getLogger().handlers:
            h.flush()

        log_file = tmp_path / "promptgrimoire-test_branch.jsonl"
        lines = [ln for ln in log_file.read_text().splitlines() if ln.strip()]
        parsed = json.loads(lines[-1])
        assert "pid" in parsed
        assert parsed["pid"] == os.getpid()
        assert "branch" in parsed
        assert "commit" in parsed
        assert "level" in parsed
        assert "timestamp" in parsed
        assert "event" in parsed
