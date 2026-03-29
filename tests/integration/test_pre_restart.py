"""Integration tests for pre-restart flush endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_request(token: str | None = None) -> MagicMock:
    """Create a mock Starlette Request with optional Bearer token."""
    headers: dict[str, str] = {}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return MagicMock(headers=headers)


def _mock_settings(token: str = "test-token") -> MagicMock:  # noqa: S107
    """Create mock settings with pre_restart_token."""
    from pydantic import SecretStr

    settings = MagicMock()
    settings.admin.pre_restart_token = SecretStr(token)
    return settings


class TestPreRestartAuth:
    """AC2.3: Non-admin POST /api/pre-restart returns 403."""

    @pytest.mark.asyncio
    async def test_no_token_returns_403(self) -> None:
        from promptgrimoire.pages.restart import pre_restart_handler

        with patch(
            "promptgrimoire.pages.restart.get_settings",
            return_value=_mock_settings(),
        ):
            resp = await pre_restart_handler(_make_request())

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_token_returns_403(self) -> None:
        from promptgrimoire.pages.restart import pre_restart_handler

        with patch(
            "promptgrimoire.pages.restart.get_settings",
            return_value=_mock_settings(),
        ):
            resp = await pre_restart_handler(_make_request(token="wrong"))

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unconfigured_token_returns_503(self) -> None:
        from promptgrimoire.pages.restart import pre_restart_handler

        with patch(
            "promptgrimoire.pages.restart.get_settings",
            return_value=_mock_settings(token=""),
        ):
            resp = await pre_restart_handler(_make_request(token="anything"))

        assert resp.status_code == 503


class TestPreRestartFlush:
    """AC2.1, AC2.2, AC2.4: CRDT flush + navigate."""

    @pytest.mark.asyncio
    async def test_flushes_milkdown_persists_and_navigates(self) -> None:
        """Fire-and-forget flush -> persist -> navigate -> invalidate ordering.

        After #454 Phase 2 Task 3, _flush_milkdown_to_crdt sends
        _flushRespondMarkdownNow fire-and-forget (no per-client await),
        then sleeps 1.0s for the drain deadline. The test verifies the
        overall ordering: flush JS sent, persist, navigate, invalidate.
        """
        from promptgrimoire.pages.restart import pre_restart_handler

        call_order: list[str] = []

        # Mock client
        mock_client = MagicMock()
        mock_client.has_socket_connection = True
        mock_client._deleted = False
        mock_client.id = "test-client-1"

        def tracking_run_js(code: str, timeout: float = 5.0) -> None:  # noqa: ARG001
            # Fire-and-forget _flushRespondMarkdownNow
            if "_flushRespondMarkdownNow" in code:
                call_order.append("flush_fire")
                return None
            # Navigation is also fire-and-forget
            if "restarting" in code:
                call_order.append("navigate")
                return None
            return None

        mock_client.run_javascript = MagicMock(side_effect=tracking_run_js)

        # Mock presence
        mock_presence = MagicMock()
        mock_presence.has_milkdown_editor = True
        mock_presence.nicegui_client = mock_client

        mock_persist_mgr = MagicMock()

        async def tracking_persist() -> None:
            call_order.append("persist")

        mock_persist_mgr.persist_all_dirty_workspaces = AsyncMock(
            side_effect=tracking_persist
        )

        presence_dict: dict[str, dict[str, object]] = {
            "ws-123": {"test-client-1": mock_presence}
        }

        # Mock Client.instances for navigation loop
        mock_client_class = MagicMock()
        mock_client_class.instances = {"c1": mock_client}

        async def tracking_invalidate() -> None:
            call_order.append("invalidate")

        with (
            patch(
                "promptgrimoire.pages.restart.get_settings",
                return_value=_mock_settings(),
            ),
            patch("nicegui.Client", mock_client_class),
            patch(
                "promptgrimoire.pages.restart._get_annotation_state",
                return_value=(presence_dict, MagicMock()),
            ),
            patch(
                "promptgrimoire.crdt.persistence.get_persistence_manager",
                return_value=mock_persist_mgr,
            ),
            patch(
                "promptgrimoire.diagnostics._invalidate_all_sessions",
                AsyncMock(side_effect=tracking_invalidate),
            ),
        ):
            resp = await pre_restart_handler(_make_request(token="test-token"))

        assert resp.status_code == 200

        # Fire-and-forget flush before persist
        assert call_order.index("flush_fire") < call_order.index("persist")
        # Navigate before invalidate — clients still rendering will crash
        # on `assert auth_user is not None` if sessions vanish mid-load.
        assert call_order.index("navigate") < call_order.index("invalidate")
        # All four steps happened
        assert set(call_order) == {
            "flush_fire",
            "persist",
            "navigate",
            "invalidate",
        }

    @pytest.mark.asyncio
    async def test_tolerates_disconnected_client(self) -> None:
        """Stale clients don't crash the handler."""
        from promptgrimoire.pages.restart import pre_restart_handler

        mock_client = MagicMock()
        mock_client.has_socket_connection = True
        mock_client._deleted = True
        mock_client.id = "stale-client"

        mock_presence = MagicMock()
        mock_presence.has_milkdown_editor = True
        mock_presence.nicegui_client = mock_client

        mock_persist_mgr = MagicMock()
        mock_persist_mgr.persist_all_dirty_workspaces = AsyncMock()

        presence_dict: dict[str, dict[str, object]] = {
            "ws-456": {"stale-client": mock_presence}
        }

        mock_client_class = MagicMock()
        mock_client_class.instances = {"c1": mock_client}

        with (
            patch(
                "promptgrimoire.pages.restart.get_settings",
                return_value=_mock_settings(),
            ),
            patch("nicegui.Client", mock_client_class),
            patch(
                "promptgrimoire.pages.restart._get_annotation_state",
                return_value=(presence_dict, MagicMock()),
            ),
            patch(
                "promptgrimoire.crdt.persistence.get_persistence_manager",
                return_value=mock_persist_mgr,
            ),
        ):
            resp = await pre_restart_handler(_make_request(token="test-token"))

        assert resp.status_code == 200


class TestPreRestartSessionInvalidation:
    """Session invalidation must run during pre-restart."""

    @pytest.mark.asyncio
    async def test_pre_restart_calls_invalidate_all_sessions(self) -> None:
        """Manual restart via restart.sh must invalidate sessions."""
        from promptgrimoire.pages.restart import pre_restart_handler

        mock_persist_mgr = MagicMock()
        mock_persist_mgr.persist_all_dirty_workspaces = AsyncMock()

        mock_client_class = MagicMock()
        mock_client_class.instances = {}

        invalidate_called = False

        async def tracking_invalidate() -> None:
            nonlocal invalidate_called
            invalidate_called = True

        with (
            patch(
                "promptgrimoire.pages.restart.get_settings",
                return_value=_mock_settings(),
            ),
            patch("nicegui.Client", mock_client_class),
            patch(
                "promptgrimoire.pages.restart._get_annotation_state",
                return_value=({}, None),
            ),
            patch(
                "promptgrimoire.crdt.persistence.get_persistence_manager",
                return_value=mock_persist_mgr,
            ),
            patch(
                "promptgrimoire.diagnostics._invalidate_all_sessions",
                AsyncMock(side_effect=tracking_invalidate),
            ),
        ):
            resp = await pre_restart_handler(_make_request(token="test-token"))

        assert resp.status_code == 200
        assert invalidate_called, (
            "pre_restart_handler must call _invalidate_all_sessions"
        )

    @pytest.mark.asyncio
    async def test_invalidation_runs_after_navigate(self) -> None:
        """Sessions must be invalidated after clients are navigated away.

        Invalidating while clients are still rendering pages causes
        ``assert auth_user is not None`` crashes in page handlers.
        """
        from promptgrimoire.pages.restart import pre_restart_handler

        call_order: list[str] = []

        mock_persist_mgr = MagicMock()
        mock_persist_mgr.persist_all_dirty_workspaces = AsyncMock()

        async def tracking_invalidate() -> None:
            call_order.append("invalidate")

        mock_client = MagicMock()
        mock_client.has_socket_connection = True
        mock_client.id = "nav-test"

        def tracking_run_js(code: str, timeout: float = 5.0) -> None:  # noqa: ARG001
            if "restarting" in code:
                call_order.append("navigate")

        mock_client.run_javascript = MagicMock(side_effect=tracking_run_js)

        mock_client_class = MagicMock()
        mock_client_class.instances = {"c1": mock_client}

        with (
            patch(
                "promptgrimoire.pages.restart.get_settings",
                return_value=_mock_settings(),
            ),
            patch("nicegui.Client", mock_client_class),
            patch(
                "promptgrimoire.pages.restart._get_annotation_state",
                return_value=({}, None),
            ),
            patch(
                "promptgrimoire.crdt.persistence.get_persistence_manager",
                return_value=mock_persist_mgr,
            ),
            patch(
                "promptgrimoire.diagnostics._invalidate_all_sessions",
                AsyncMock(side_effect=tracking_invalidate),
            ),
        ):
            resp = await pre_restart_handler(_make_request(token="test-token"))

        assert resp.status_code == 200
        assert call_order.index("navigate") < call_order.index("invalidate")


class TestConnectionCount:
    """Test GET /api/connection-count."""

    @pytest.mark.asyncio
    async def test_returns_connected_count(self) -> None:
        from promptgrimoire.pages.restart import connection_count_handler

        connected = MagicMock(has_socket_connection=True)
        disconnected = MagicMock(has_socket_connection=False)

        mock_client_class = MagicMock()
        mock_client_class.instances = {
            "c1": connected,
            "c2": disconnected,
            "c3": connected,
        }

        with (
            patch(
                "promptgrimoire.pages.restart.get_settings",
                return_value=_mock_settings(),
            ),
            patch("nicegui.Client", mock_client_class),
        ):
            resp = await connection_count_handler(_make_request(token="test-token"))

        import json

        body = json.loads(bytes(resp.body))
        assert body["count"] == 2

    @pytest.mark.asyncio
    async def test_bad_token_returns_403(self) -> None:
        from promptgrimoire.pages.restart import connection_count_handler

        with patch(
            "promptgrimoire.pages.restart.get_settings",
            return_value=_mock_settings(),
        ):
            resp = await connection_count_handler(_make_request(token="wrong"))

        assert resp.status_code == 403
