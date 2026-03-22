"""Unit tests for PDF export queue refactoring (Phase 5, #402).

Tests verify the refactored export flow: job submission, polling,
download button, page-load recovery, and lock removal.

Traceability:
- Design: docs/implementation-plans/2026-03-21-export-queue-402/phase_05.md
- AC: export-queue-402.AC2.1, AC2.2, AC2.3, AC4.3, AC6.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest


# ---------------------------------------------------------------------------
# Lightweight stub for PageState — avoids importing NiceGUI at test time
# ---------------------------------------------------------------------------
@dataclass
class _StubPageState:
    """Minimal stub matching the PageState fields used by pdf_export.py."""

    workspace_id: UUID = field(default_factory=uuid4)
    user_id: str | None = None
    crdt_doc: MagicMock | None = None
    document_id: UUID | None = None
    is_anonymous: bool = False
    viewer_is_privileged: bool = False
    privileged_user_ids: frozenset[str] = field(default_factory=frozenset)
    tag_info_list: list | None = None
    word_minimum: int | None = None
    word_limit: int | None = None
    word_limit_enforcement: bool = False
    has_milkdown_editor: bool = False

    def tag_colours(self) -> dict[str, str]:
        """Stub for PageState.tag_colours()."""
        return {}


def _stub(**kwargs: Any) -> Any:
    """Create a _StubPageState cast to Any for type-checker compat."""
    return _StubPageState(**kwargs)


# ---------------------------------------------------------------------------
# Stub for ExportJob
# ---------------------------------------------------------------------------
@dataclass
class _StubExportJob:
    """Minimal stub matching ExportJob fields used in polling."""

    id: UUID = field(default_factory=uuid4)
    status: str = "queued"
    download_token: str | None = None
    error_message: str | None = None
    user_id: UUID = field(default_factory=uuid4)
    workspace_id: UUID = field(default_factory=uuid4)


# ---------------------------------------------------------------------------
# Import the functions under test
# ---------------------------------------------------------------------------
from promptgrimoire.pages.annotation.pdf_export import (  # noqa: E402
    _handle_pdf_export,
    _show_download_button,
    _start_export_polling,
    check_existing_export,
)


# ---------------------------------------------------------------------------
# AC2.1: Job submission with correct payload
# ---------------------------------------------------------------------------
class TestJobSubmission:
    """export-queue-402.AC2.1: After clicking export, job is created."""

    @pytest.mark.anyio
    async def test_handle_pdf_export_creates_job_with_payload(self) -> None:
        """Refactored handler gathers payload and calls create_export_job."""
        user_id = uuid4()
        workspace_id = uuid4()
        document_id = uuid4()

        state = _stub(
            workspace_id=workspace_id,
            user_id=str(user_id),
            document_id=document_id,
        )
        crdt = MagicMock()
        crdt.get_highlights_for_document.return_value = []
        crdt.get_response_draft_markdown.return_value = ""
        state.crdt_doc = crdt

        mock_job = _StubExportJob(
            id=uuid4(), user_id=user_id, workspace_id=workspace_id
        )

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.create_export_job",
                new_callable=AsyncMock,
                return_value=mock_job,
            ) as mock_create,
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_document",
                new_callable=AsyncMock,
            ) as mock_get_doc,
            patch(
                "promptgrimoire.pages.annotation.pdf_export.markdown_to_latex_notes",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export._build_export_filename",
                new_callable=AsyncMock,
                return_value="test-export",
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export._start_export_polling",
            ) as mock_poll,
            patch("promptgrimoire.pages.annotation.pdf_export.ui"),
            patch(
                "promptgrimoire.pages.annotation.pdf_export.bind_contextvars",
            ),
        ):
            # Set up document mock
            mock_doc = MagicMock()
            mock_doc.content = "<p>Test content</p>"
            mock_doc.paragraph_map = None
            mock_get_doc.return_value = mock_doc

            await _handle_pdf_export(state, workspace_id)

            # Verify create_export_job was called
            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert call_args[0][0] == user_id  # user_id as UUID
            assert call_args[0][1] == workspace_id
            payload = call_args[0][2]
            assert "html_content" in payload
            assert "highlights" in payload
            assert "tag_colours" in payload
            assert "filename" in payload

            # Verify polling was started
            mock_poll.assert_called_once_with(mock_job.id, state)

    @pytest.mark.anyio
    async def test_handle_pdf_export_no_document_shows_warning(self) -> None:
        """Handler shows warning when no document exists."""
        state = _stub(
            user_id=str(uuid4()),
            crdt_doc=None,
            document_id=None,
        )

        with (
            patch("promptgrimoire.pages.annotation.pdf_export.ui") as mock_ui,
            patch("promptgrimoire.pages.annotation.pdf_export.bind_contextvars"),
        ):
            await _handle_pdf_export(state, uuid4())
            mock_ui.notify.assert_called_once()
            assert "No document" in str(mock_ui.notify.call_args)


# ---------------------------------------------------------------------------
# AC4.3: BusinessLogicError shows notification
# ---------------------------------------------------------------------------
class TestConcurrentExportRejection:
    """export-queue-402.AC4.3: Concurrent export shows notification."""

    @pytest.mark.anyio
    async def test_business_logic_error_shows_notification(self) -> None:
        """BusinessLogicError from create_export_job shows 'already in progress'."""
        from promptgrimoire.db.exceptions import BusinessLogicError

        user_id = uuid4()
        workspace_id = uuid4()
        document_id = uuid4()

        state = _stub(
            workspace_id=workspace_id,
            user_id=str(user_id),
            document_id=document_id,
        )
        crdt = MagicMock()
        crdt.get_highlights_for_document.return_value = []
        crdt.get_response_draft_markdown.return_value = ""
        state.crdt_doc = crdt

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.create_export_job",
                new_callable=AsyncMock,
                side_effect=BusinessLogicError("A PDF export is already in progress"),
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_document",
                new_callable=AsyncMock,
            ) as mock_get_doc,
            patch(
                "promptgrimoire.pages.annotation.pdf_export.markdown_to_latex_notes",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export._build_export_filename",
                new_callable=AsyncMock,
                return_value="test-export",
            ),
            patch("promptgrimoire.pages.annotation.pdf_export.ui") as mock_ui,
            patch("promptgrimoire.pages.annotation.pdf_export.bind_contextvars"),
        ):
            mock_doc = MagicMock()
            mock_doc.content = "<p>Test</p>"
            mock_doc.paragraph_map = None
            mock_get_doc.return_value = mock_doc

            await _handle_pdf_export(state, workspace_id)

            # Verify "already in progress" notification
            notify_calls = mock_ui.notify.call_args_list
            assert any("already in progress" in str(c) for c in notify_calls)


# ---------------------------------------------------------------------------
# AC2.1 / AC2.2: Polling callback transitions and timer deactivation
# ---------------------------------------------------------------------------
class TestPollingCallback:
    """export-queue-402.AC2.1/AC2.2: Status polling transitions."""

    @pytest.mark.anyio
    async def test_poll_running_updates_message(self) -> None:
        """When job transitions to running, notification text updates."""
        job_id = uuid4()
        job = _StubExportJob(id=job_id, status="running")

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch("promptgrimoire.pages.annotation.pdf_export.ui") as mock_ui,
        ):
            notification = MagicMock()
            notification.props.return_value = notification  # .props() chains
            mock_ui.notification.return_value = notification

            timer = MagicMock()
            mock_ui.timer.return_value = timer

            _start_export_polling(job_id, _stub())

            # Get the poll callback passed to ui.timer
            poll_fn = mock_ui.timer.call_args[0][1]
            await poll_fn()

            assert notification.message == "Compiling PDF..."
            timer.deactivate.assert_not_called()

    @pytest.mark.anyio
    async def test_poll_completed_dismisses_and_shows_download(self) -> None:
        """When job completes, notification is dismissed and download button shown."""
        job_id = uuid4()
        token = "test-token-123"
        job = _StubExportJob(id=job_id, status="completed", download_token=token)

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch("promptgrimoire.pages.annotation.pdf_export.ui") as mock_ui,
            patch(
                "promptgrimoire.pages.annotation.pdf_export._show_download_button",
            ) as mock_download,
        ):
            notification = MagicMock()
            notification.props.return_value = notification  # .props() chains
            mock_ui.notification.return_value = notification

            timer = MagicMock()
            mock_ui.timer.return_value = timer

            state = _stub()
            _start_export_polling(job_id, state)

            poll_fn = mock_ui.timer.call_args[0][1]
            await poll_fn()

            notification.dismiss.assert_called_once()
            timer.deactivate.assert_called_once()
            mock_download.assert_called_once_with(token, state)

    @pytest.mark.anyio
    async def test_poll_failed_dismisses_and_shows_error(self) -> None:
        """When job fails, notification is dismissed and error shown."""
        job_id = uuid4()
        job = _StubExportJob(
            id=job_id, status="failed", error_message="LaTeX compilation error"
        )

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch("promptgrimoire.pages.annotation.pdf_export.ui") as mock_ui,
        ):
            notification = MagicMock()
            notification.props.return_value = notification  # .props() chains
            mock_ui.notification.return_value = notification

            timer = MagicMock()
            mock_ui.timer.return_value = timer

            _start_export_polling(job_id, _stub())

            poll_fn = mock_ui.timer.call_args[0][1]
            await poll_fn()

            notification.dismiss.assert_called_once()
            timer.deactivate.assert_called_once()

    @pytest.mark.anyio
    async def test_poll_job_none_deactivates_timer(self) -> None:
        """When job is not found (deleted), timer deactivates."""
        job_id = uuid4()

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_job",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("promptgrimoire.pages.annotation.pdf_export.ui") as mock_ui,
        ):
            notification = MagicMock()
            notification.props.return_value = notification  # .props() chains
            mock_ui.notification.return_value = notification

            timer = MagicMock()
            mock_ui.timer.return_value = timer

            _start_export_polling(job_id, _stub())

            poll_fn = mock_ui.timer.call_args[0][1]
            await poll_fn()

            notification.dismiss.assert_called_once()
            timer.deactivate.assert_called_once()


# ---------------------------------------------------------------------------
# AC2.1 / AC3.1: Download button
# ---------------------------------------------------------------------------
class TestDownloadButton:
    """export-queue-402.AC2.1/AC3.1: Download button for completed exports."""

    def test_show_download_button_creates_button_with_correct_url(self) -> None:
        """Download button triggers ui.download with correct token URL."""
        token = "abc-token-xyz"

        with patch("promptgrimoire.pages.annotation.pdf_export.ui") as mock_ui:
            # Set up a stub with a container that supports context manager
            container = MagicMock()
            container.__enter__ = MagicMock(return_value=container)
            container.__exit__ = MagicMock(return_value=False)
            export_btn = MagicMock()
            stub = _stub()
            stub.export_download_container = container
            stub.export_btn = export_btn

            _show_download_button(token, stub)

            # Verify container was cleared and entered
            container.clear.assert_called_once()

            # Verify notification shown
            mock_ui.notification.assert_called_once()
            assert "ready" in str(mock_ui.notification.call_args).lower()

            # Verify button created with data-testid
            mock_ui.button.assert_called_once()
            btn_call = mock_ui.button.call_args
            assert "Download" in str(btn_call)

            # Verify export button re-enabled
            export_btn.enable.assert_called_once()


# ---------------------------------------------------------------------------
# AC2.3: Page load recovery
# ---------------------------------------------------------------------------
class TestPageLoadRecovery:
    """export-queue-402.AC2.3: Page reload recovers export state."""

    @pytest.mark.anyio
    async def test_recovery_running_job_starts_polling(self) -> None:
        """Running export on page load starts polling timer."""
        user_id = uuid4()
        workspace_id = uuid4()
        job = _StubExportJob(
            id=uuid4(), status="running", user_id=user_id, workspace_id=workspace_id
        )

        state = _stub(
            workspace_id=workspace_id,
            user_id=str(user_id),
        )

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_active_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export._start_export_polling",
            ) as mock_poll,
            patch(
                "promptgrimoire.pages.annotation.pdf_export._show_download_button",
            ),
        ):
            await check_existing_export(state)
            mock_poll.assert_called_once_with(job.id, state, initial_status=job.status)

    @pytest.mark.anyio
    async def test_recovery_queued_job_starts_polling(self) -> None:
        """Queued export on page load starts polling timer."""
        user_id = uuid4()
        workspace_id = uuid4()
        job = _StubExportJob(
            id=uuid4(), status="queued", user_id=user_id, workspace_id=workspace_id
        )

        state = _stub(
            workspace_id=workspace_id,
            user_id=str(user_id),
        )

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_active_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export._start_export_polling",
            ) as mock_poll,
            patch(
                "promptgrimoire.pages.annotation.pdf_export._show_download_button",
            ),
        ):
            await check_existing_export(state)
            mock_poll.assert_called_once_with(job.id, state, initial_status=job.status)

    @pytest.mark.anyio
    async def test_recovery_completed_job_shows_download(self) -> None:
        """Completed export on page load shows download button."""
        user_id = uuid4()
        workspace_id = uuid4()
        token = "completed-token"
        job = _StubExportJob(
            id=uuid4(),
            status="completed",
            download_token=token,
            user_id=user_id,
            workspace_id=workspace_id,
        )

        state = _stub(
            workspace_id=workspace_id,
            user_id=str(user_id),
        )

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_active_job_for_user",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export._start_export_polling",
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export._show_download_button",
            ) as mock_download,
        ):
            await check_existing_export(state)
            mock_download.assert_called_once_with(token, state)

    @pytest.mark.anyio
    async def test_recovery_no_job_is_noop(self) -> None:
        """No active export on page load does nothing."""
        state = _stub(user_id=str(uuid4()))

        with (
            patch(
                "promptgrimoire.pages.annotation.pdf_export.get_active_job_for_user",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "promptgrimoire.pages.annotation.pdf_export._start_export_polling",
            ) as mock_poll,
            patch(
                "promptgrimoire.pages.annotation.pdf_export._show_download_button",
            ) as mock_download,
        ):
            await check_existing_export(state)
            mock_poll.assert_not_called()
            mock_download.assert_not_called()

    @pytest.mark.anyio
    async def test_recovery_unauthenticated_is_noop(self) -> None:
        """Unauthenticated user on page load does nothing."""
        state = _stub(user_id=None)

        with patch(
            "promptgrimoire.pages.annotation.pdf_export.get_active_job_for_user",
            new_callable=AsyncMock,
        ) as mock_get_active:
            await check_existing_export(state)
            mock_get_active.assert_not_called()


# ---------------------------------------------------------------------------
# AC6.1: No in-memory lock references
# ---------------------------------------------------------------------------
class TestLockRemoval:
    """export-queue-402.AC6.1: No in-memory lock references remain."""

    def test_no_user_export_locks_reference(self) -> None:
        """Module has no _user_export_locks or _get_user_export_lock."""
        import inspect

        import promptgrimoire.pages.annotation.pdf_export as mod

        source = inspect.getsource(mod)
        assert "_user_export_locks" not in source
        assert "_get_user_export_lock" not in source

    def test_no_asyncio_lock_import(self) -> None:
        """Module does not import asyncio.Lock (no longer needed)."""
        import inspect

        import promptgrimoire.pages.annotation.pdf_export as mod

        source = inspect.getsource(mod)
        assert "asyncio.Lock" not in source
