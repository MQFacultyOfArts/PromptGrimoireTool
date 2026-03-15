"""Tests for Discord webhook alerting processor.

Verifies:
- AC5.1: ERROR-level log triggers webhook POST with correct embed format
- AC5.2: Empty webhook URL results in no POST attempt
- AC5.3: Deduplication within 60s window
- AC5.4: Webhook POST failure does not disrupt logging
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from promptgrimoire.logging_discord import DiscordAlertProcessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def processor() -> DiscordAlertProcessor:
    """Processor with a test webhook URL."""
    return DiscordAlertProcessor(
        webhook_url="https://discord.com/api/webhooks/123/abc",
    )


@pytest.fixture
def no_url_processor() -> DiscordAlertProcessor:
    """Processor with no webhook URL configured."""
    return DiscordAlertProcessor(webhook_url="")


@pytest.fixture
def event_dict_error() -> dict[str, object]:
    """Sample ERROR-level event dict."""
    return {
        "event": "database_connection_failed",
        "level": "error",
        "logger": "promptgrimoire.db",
        "user_id": "user-123",
        "workspace_id": "ws-456",
        "pid": 1234,
        "exc_info": ValueError("connection refused"),
        "timestamp": "2026-03-14T10:00:00Z",
    }


@pytest.fixture
def event_dict_critical() -> dict[str, object]:
    """Sample CRITICAL-level event dict."""
    return {
        "event": "unrecoverable_error",
        "level": "critical",
        "logger": "promptgrimoire.main",
        "pid": 1234,
        "timestamp": "2026-03-14T10:00:00Z",
    }


@pytest.fixture
def event_dict_info() -> dict[str, object]:
    """Sample INFO-level event dict."""
    return {
        "event": "request_handled",
        "level": "info",
        "logger": "promptgrimoire.pages",
        "pid": 1234,
    }


# ---------------------------------------------------------------------------
# AC5.2: No-op when webhook URL is empty
# ---------------------------------------------------------------------------
class TestNoOpWhenUnconfigured:
    """AC5.2: No Discord message sent when URL is empty."""

    def test_empty_url_returns_event_dict(
        self,
        no_url_processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        result = no_url_processor(None, "error", event_dict_error)
        assert result is event_dict_error

    def test_empty_url_no_post_attempt(
        self,
        no_url_processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        with patch("promptgrimoire.logging_discord.httpx") as mock_httpx:
            no_url_processor(None, "error", event_dict_error)
            mock_httpx.AsyncClient.assert_not_called()


# ---------------------------------------------------------------------------
# Non-error levels are ignored
# ---------------------------------------------------------------------------
class TestNonErrorLevelsIgnored:
    """Only ERROR and CRITICAL trigger webhook."""

    def test_info_level_passthrough(
        self,
        processor: DiscordAlertProcessor,
        event_dict_info: dict[str, object],
    ) -> None:
        with patch("promptgrimoire.logging_discord.httpx") as mock_httpx:
            result = processor(None, "info", event_dict_info)
            assert result is event_dict_info
            mock_httpx.AsyncClient.assert_not_called()

    def test_debug_level_passthrough(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        event = {"event": "debug_msg", "level": "debug", "logger": "test"}
        with patch("promptgrimoire.logging_discord.httpx") as mock_httpx:
            result = processor(None, "debug", event)
            assert result is event
            mock_httpx.AsyncClient.assert_not_called()


# ---------------------------------------------------------------------------
# AC5.1: ERROR-level log triggers webhook POST
# ---------------------------------------------------------------------------
class TestErrorTriggersWebhook:
    """AC5.1: ERROR events send Discord embed."""

    def test_error_fires_webhook(
        self,
        processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        """ERROR event triggers a fire-and-forget POST."""
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            result = processor(None, "error", event_dict_error)
            assert result is event_dict_error
            mock_fire.assert_called_once()
            payload = mock_fire.call_args[0][0]
            embed = payload["embeds"][0]
            assert "[ERROR]" in embed["title"]
            assert "database_connection_failed" in embed["title"]

    def test_critical_fires_webhook(
        self,
        processor: DiscordAlertProcessor,
        event_dict_critical: dict[str, object],
    ) -> None:
        """CRITICAL event triggers a fire-and-forget POST."""
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            result = processor(None, "critical", event_dict_critical)
            assert result is event_dict_critical
            mock_fire.assert_called_once()
            payload = mock_fire.call_args[0][0]
            embed = payload["embeds"][0]
            assert "[CRITICAL]" in embed["title"]

    def test_embed_colour_error_is_red(
        self,
        processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event_dict_error)
            embed = mock_fire.call_args[0][0]["embeds"][0]
            assert embed["color"] == 15548997  # red

    def test_embed_colour_critical_is_dark_red(
        self,
        processor: DiscordAlertProcessor,
        event_dict_critical: dict[str, object],
    ) -> None:
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "critical", event_dict_critical)
            embed = mock_fire.call_args[0][0]["embeds"][0]
            assert embed["color"] == 10040115  # dark red

    def test_embed_contains_context_fields(
        self,
        processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        """Context fields (user_id, workspace_id, etc.) appear as embed fields."""
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event_dict_error)
            embed = mock_fire.call_args[0][0]["embeds"][0]
            field_names = [f["name"] for f in embed.get("fields", [])]
            assert "user_id" in field_names
            assert "workspace_id" in field_names
            assert "logger" in field_names
            assert "pid" in field_names

    def test_embed_omits_none_context_fields(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        """Fields with None values are omitted from embed."""
        event = {
            "event": "test_error",
            "level": "error",
            "logger": "test",
            "user_id": None,
            "workspace_id": None,
            "pid": 1234,
        }
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event)
            embed = mock_fire.call_args[0][0]["embeds"][0]
            field_names = [f["name"] for f in embed.get("fields", [])]
            assert "user_id" not in field_names
            assert "workspace_id" not in field_names

    def test_embed_has_timestamp(
        self,
        processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event_dict_error)
            embed = mock_fire.call_args[0][0]["embeds"][0]
            assert "timestamp" in embed


# ---------------------------------------------------------------------------
# AC5.3: Deduplication within 60s window
# ---------------------------------------------------------------------------
class TestDeduplication:
    """AC5.3: Same (exc_type, logger) within window produces one message."""

    def test_duplicate_within_window_suppressed(
        self,
        processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event_dict_error)
            processor(None, "error", event_dict_error)
            assert mock_fire.call_count == 1

    def test_different_logger_not_suppressed(
        self,
        processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event_dict_error)
            event_dict_error["logger"] = "promptgrimoire.other"
            processor(None, "error", event_dict_error)
            assert mock_fire.call_count == 2

    def test_different_exc_type_not_suppressed(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        event1 = {
            "event": "err1",
            "level": "error",
            "logger": "test",
            "exc_info": ValueError("x"),
        }
        event2 = {
            "event": "err2",
            "level": "error",
            "logger": "test",
            "exc_info": TypeError("y"),
        }
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event1)
            processor(None, "error", event2)
            assert mock_fire.call_count == 2

    def test_after_window_expires_sends_again(
        self,
        event_dict_error: dict[str, object],
    ) -> None:
        proc = DiscordAlertProcessor(
            webhook_url="https://discord.com/api/webhooks/123/abc",
            dedup_window_seconds=0.1,
        )
        with patch.object(proc, "_fire_and_forget") as mock_fire:
            proc(None, "error", event_dict_error)
            time.sleep(0.15)
            proc(None, "error", event_dict_error)
            assert mock_fire.call_count == 2


# ---------------------------------------------------------------------------
# AC5.4: Webhook failure does not disrupt logging
# ---------------------------------------------------------------------------
class TestWebhookFailureSafe:
    """AC5.4: Webhook POST failure must not propagate."""

    @pytest.mark.asyncio
    async def test_send_webhook_swallows_timeout(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        """httpx timeout does not raise."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch(
            "promptgrimoire.logging_discord.httpx.AsyncClient", return_value=mock_client
        ):
            # Should not raise
            await processor._send_webhook({"embeds": []})

    @pytest.mark.asyncio
    async def test_send_webhook_swallows_connection_error(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with patch(
            "promptgrimoire.logging_discord.httpx.AsyncClient", return_value=mock_client
        ):
            await processor._send_webhook({"embeds": []})

    @pytest.mark.asyncio
    async def test_send_webhook_handles_429(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        """429 rate-limited logs to stderr, does not raise."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with (
            patch(
                "promptgrimoire.logging_discord.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("sys.stderr") as mock_stderr,
        ):
            await processor._send_webhook({"embeds": []})
            mock_stderr.write.assert_called()

    @pytest.mark.asyncio
    async def test_send_webhook_success(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        """Successful POST completes without error."""
        mock_response = MagicMock()
        mock_response.status_code = 204

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "promptgrimoire.logging_discord.httpx.AsyncClient", return_value=mock_client
        ):
            await processor._send_webhook({"embeds": [{"title": "test"}]})
            mock_client.post.assert_called_once()

    def test_processor_call_never_raises(
        self,
        processor: DiscordAlertProcessor,
        event_dict_error: dict[str, object],
    ) -> None:
        """Even if _fire_and_forget raises, processor swallows it."""
        with patch.object(
            processor,
            "_fire_and_forget",
            side_effect=RuntimeError("unexpected"),
        ):
            result = processor(None, "error", event_dict_error)
            assert result is event_dict_error


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------
class TestTruncation:
    """Discord embed limits are respected."""

    def test_title_truncated_to_256(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        event = {
            "event": "x" * 300,
            "level": "error",
            "logger": "test",
        }
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event)
            embed = mock_fire.call_args[0][0]["embeds"][0]
            assert len(embed["title"]) <= 256

    def test_description_truncated_to_4096(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        event = {
            "event": "big_error",
            "level": "error",
            "logger": "test",
            "exc_info": ValueError("y" * 5000),
        }
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event)
            embed = mock_fire.call_args[0][0]["embeds"][0]
            assert len(embed.get("description", "")) <= 4096

    def test_field_value_truncated_to_1024(
        self,
        processor: DiscordAlertProcessor,
    ) -> None:
        event = {
            "event": "err",
            "level": "error",
            "logger": "test",
            "user_id": "u" * 2000,
        }
        with patch.object(processor, "_fire_and_forget") as mock_fire:
            processor(None, "error", event)
            embed = mock_fire.call_args[0][0]["embeds"][0]
            for field in embed.get("fields", []):
                assert len(str(field["value"])) <= 1024
