"""Unit tests for upload handler error logging.

Verifies that file conversion failures (bad user input) are logged at
WARNING, not ERROR — preventing false Discord alerts.

Traceability:
- Issue: #390 (invalid PDF upload logs ERROR instead of WARNING)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
class TestUploadHandlerErrorLogging:
    """Verify upload handler logs conversion failures at WARNING."""

    async def test_conversion_error_from_process_input_logs_warning_not_error(
        self,
    ) -> None:
        """When process_input raises ConversionError (bad file), log at WARNING."""
        from promptgrimoire.input_pipeline.converters import ConversionError
        from promptgrimoire.pages.annotation.upload_handler import (
            _handle_file_upload,
        )

        workspace_id = uuid4()
        on_added = MagicMock()

        # Build a fake UploadEventArguments with a .file attribute
        fake_file = MagicMock()
        fake_file.name = "corrupt.pdf"
        fake_file.read = AsyncMock(return_value=b"not-a-pdf")
        upload_event = MagicMock()
        upload_event.file = fake_file

        with (
            patch(
                "promptgrimoire.pages.annotation.upload_handler.process_input",
                side_effect=ConversionError(
                    "Failed to convert PDF: Failed to open stream"
                ),
            ),
            patch(
                "promptgrimoire.pages.annotation.upload_handler.show_content_type_dialog",
                new_callable=AsyncMock,
                return_value=("pdf", True),
            ),
            patch(
                "promptgrimoire.pages.annotation.upload_handler.ui",
            ) as mock_ui,
            patch(
                "promptgrimoire.pages.annotation.upload_handler.logger",
            ) as mock_logger,
        ):
            await _handle_file_upload(workspace_id, upload_event, on_added)

            # Should log at WARNING, not ERROR/exception
            mock_logger.warning.assert_called_once()
            mock_logger.exception.assert_not_called()

            # Should still notify the user
            mock_ui.notify.assert_called_once()
            call_kwargs = mock_ui.notify.call_args
            assert "negative" in str(call_kwargs)

    async def test_unexpected_exception_still_logs_error(self) -> None:
        """Genuinely unexpected exceptions should still log at ERROR."""
        from promptgrimoire.pages.annotation.upload_handler import (
            _handle_file_upload,
        )

        workspace_id = uuid4()
        on_added = MagicMock()

        fake_file = MagicMock()
        fake_file.name = "test.pdf"
        fake_file.read = AsyncMock(return_value=b"some-bytes")
        upload_event = MagicMock()
        upload_event.file = fake_file

        with (
            patch(
                "promptgrimoire.pages.annotation.upload_handler.process_input",
                side_effect=OSError("disk full"),
            ),
            patch(
                "promptgrimoire.pages.annotation.upload_handler.show_content_type_dialog",
                new_callable=AsyncMock,
                return_value=("pdf", True),
            ),
            patch(
                "promptgrimoire.pages.annotation.upload_handler.ui",
            ),
            patch(
                "promptgrimoire.pages.annotation.upload_handler.logger",
            ) as mock_logger,
        ):
            await _handle_file_upload(workspace_id, upload_event, on_added)

            # Unexpected errors should still log at ERROR
            mock_logger.exception.assert_called_once()
            mock_logger.warning.assert_not_called()
