"""Tests for batch export skip/fail classification.

Verifies that workspaces without exportable content (no documents,
no highlights) are classified as SKIP rather than FAIL, and that
the purge logic handles each state correctly.

Regression test for the 584-false-failures bug found during overnight
production validation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from promptgrimoire.cli.export import (
    _SKIP,
    _export_single_workspace,
    _purge_successes,
)

# Fake workspace/document for mocking
_TEST_UUID = UUID("12345678-1234-1234-1234-123456789abc")


class TestSkipClassification:
    """Workspaces without exportable content return _SKIP, not an error."""

    @pytest.mark.asyncio
    async def test_nonexistent_workspace_returns_skip(self) -> None:
        """Workspace not found in DB -> SKIP."""
        with patch(
            "promptgrimoire.cli.export.get_workspace",
            new_callable=AsyncMock,
            return_value=None,
        ):
            _stem, error = await _export_single_workspace(
                _TEST_UUID,
                Path("/tmp"),
                with_log=False,
                with_tex=False,
            )
        assert error == _SKIP

    @pytest.mark.asyncio
    async def test_workspace_no_content_returns_skip(self) -> None:
        """Workspace exists but documents have no content -> SKIP."""
        mock_ws = AsyncMock()
        mock_ws.crdt_state = None

        mock_doc = AsyncMock()
        mock_doc.content = ""

        with (
            patch(
                "promptgrimoire.cli.export.get_workspace",
                new_callable=AsyncMock,
                return_value=mock_ws,
            ),
            patch(
                "promptgrimoire.cli.export.get_workspace_export_metadata",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "promptgrimoire.cli.export.list_documents",
                new_callable=AsyncMock,
                return_value=[mock_doc],
            ),
        ):
            _stem, error = await _export_single_workspace(
                _TEST_UUID,
                Path("/tmp"),
                with_log=False,
                with_tex=False,
            )
        assert error == _SKIP

    @pytest.mark.asyncio
    async def test_workspace_no_highlights_returns_skip(self) -> None:
        """Workspace has content but no CRDT highlights -> SKIP."""
        mock_ws = AsyncMock()
        mock_ws.crdt_state = None  # No CRDT -> no highlights

        mock_doc = AsyncMock()
        mock_doc.content = "<p>Some content</p>"
        mock_doc.id = uuid4()

        with (
            patch(
                "promptgrimoire.cli.export.get_workspace",
                new_callable=AsyncMock,
                return_value=mock_ws,
            ),
            patch(
                "promptgrimoire.cli.export.get_workspace_export_metadata",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "promptgrimoire.cli.export.list_documents",
                new_callable=AsyncMock,
                return_value=[mock_doc],
            ),
            patch(
                "promptgrimoire.cli.export.list_tags_for_workspace",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            _stem, error = await _export_single_workspace(
                _TEST_UUID,
                Path("/tmp"),
                with_log=False,
                with_tex=False,
            )
        assert error == _SKIP


class TestPurgeSuccesses:
    """_purge_successes removes OK artifacts but ignores SKIPs and FAILs."""

    def test_purges_success_artifacts(self, tmp_path: Path) -> None:
        """Success (error=None) artifacts are deleted."""
        stem = "test_ok"
        for ext in (".pdf", ".tex", ".log"):
            (tmp_path / f"{stem}{ext}").write_text("content")

        results: list[tuple[str, str, str | None]] = [("12345678", stem, None)]
        _purge_successes(tmp_path, results)

        for ext in (".pdf", ".tex", ".log"):
            assert not (tmp_path / f"{stem}{ext}").exists()

    def test_preserves_failure_artifacts(self, tmp_path: Path) -> None:
        """Failure (error=string) artifacts are kept."""
        stem = "test_fail"
        for ext in (".pdf", ".tex", ".log"):
            (tmp_path / f"{stem}{ext}").write_text("content")

        results: list[tuple[str, str, str | None]] = [
            ("12345678", stem, "LaTeX compilation failed"),
        ]
        _purge_successes(tmp_path, results)

        for ext in (".tex", ".log"):
            assert (tmp_path / f"{stem}{ext}").exists()

    def test_skip_produces_no_artifacts_to_purge(self, tmp_path: Path) -> None:
        """SKIP (error=_SKIP) produces no artifacts — purge is a no-op."""
        results: list[tuple[str, str, str | None]] = [
            ("12345678", "test_skip", _SKIP),
        ]
        _purge_successes(tmp_path, results)
        assert list(tmp_path.iterdir()) == []
