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
        """AC2.1+AC2.2+AC2.4: extract -> persist -> navigate ordering."""
        from promptgrimoire.pages.restart import pre_restart_handler

        call_order: list[str] = []

        # Mock client
        mock_client = MagicMock()
        mock_client.has_socket_connection = True
        mock_client._deleted = False
        mock_client.id = "test-client-1"

        async def tracking_run_js(code: str, timeout: float = 5.0) -> object:  # noqa: ARG001
            if "getMilkdownMarkdown" in code:
                call_order.append("extract_milkdown")
                return "# Draft markdown"
            if "restarting" in code:
                call_order.append("navigate")
                return None
            return None

        mock_client.run_javascript = AsyncMock(side_effect=tracking_run_js)

        # Mock presence
        mock_presence = MagicMock()
        mock_presence.has_milkdown_editor = True
        mock_presence.nicegui_client = mock_client

        # Mock CRDT doc
        mock_text_field = MagicMock()
        mock_text_field.__str__ = lambda _self: ""
        mock_text_field.__len__ = lambda _self: 0
        mock_text_field.__iadd__ = lambda _self, _other: _self
        mock_crdt_doc = MagicMock()
        mock_crdt_doc.response_draft_markdown = mock_text_field
        mock_crdt_doc.doc.transaction.return_value.__enter__ = MagicMock()
        mock_crdt_doc.doc.transaction.return_value.__exit__ = MagicMock(
            return_value=False
        )

        mock_registry = AsyncMock()
        mock_registry.get_or_create_for_workspace = AsyncMock(
            return_value=mock_crdt_doc
        )

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

        with (
            patch(
                "promptgrimoire.pages.restart.get_settings",
                return_value=_mock_settings(),
            ),
            patch("nicegui.Client", mock_client_class),
            patch(
                "promptgrimoire.pages.restart._get_annotation_state",
                return_value=(presence_dict, mock_registry),
            ),
            patch(
                "promptgrimoire.crdt.persistence.get_persistence_manager",
                return_value=mock_persist_mgr,
            ),
        ):
            resp = await pre_restart_handler(_make_request(token="test-token"))

        assert resp.status_code == 200

        # AC2.4: extraction before persist
        assert call_order.index("extract_milkdown") < call_order.index("persist")
        # AC2.2: navigation happened
        assert "navigate" in call_order
        # AC2.1: persist was called
        assert "persist" in call_order

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
