"""Tests for POST /api/admin/kick endpoint.

Verifies:
- ban-user-102.AC6.1: Missing Authorization header returns 403
- ban-user-102.AC6.2: Wrong bearer token returns 403
- ban-user-102.AC6.3: Valid bearer token triggers ban check and disconnect
- ban-user-102.AC2.4: Banned user is kicked via disconnect_user
- Unconfigured secret returns 503 (fail closed)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from starlette.applications import Starlette
from starlette.routing import Route

from promptgrimoire import kick_user_handler


def _make_app() -> Starlette:
    """Create a minimal Starlette app with just the kick endpoint."""
    return Starlette(
        routes=[Route("/api/admin/kick", kick_user_handler, methods=["POST"])],
    )


def _mock_settings(secret: str = "test-secret") -> object:  # noqa: S107 -- test helper
    """Build a mock settings object with given admin_api_secret."""
    settings = MagicMock()
    settings.admin.admin_api_secret = SecretStr(secret)
    return settings


# ---------------------------------------------------------------------------
# AC6.1: Missing Authorization header -> 403
# ---------------------------------------------------------------------------
class TestMissingAuth:
    @pytest.mark.anyio
    async def test_no_auth_header_returns_403(self) -> None:
        """POST without Authorization header returns 403."""
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            with patch(
                "promptgrimoire.config.get_settings",
                return_value=_mock_settings("test-secret"),
            ):
                resp = await client.post(
                    "/api/admin/kick",
                    json={"user_id": str(uuid4())},
                )
        assert resp.status_code == 403
        assert resp.json()["error"] == "Forbidden"


# ---------------------------------------------------------------------------
# AC6.2: Wrong bearer token -> 403
# ---------------------------------------------------------------------------
class TestWrongToken:
    @pytest.mark.anyio
    async def test_wrong_token_returns_403(self) -> None:
        """POST with incorrect bearer token returns 403."""
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            with patch(
                "promptgrimoire.config.get_settings",
                return_value=_mock_settings("correct-secret"),
            ):
                resp = await client.post(
                    "/api/admin/kick",
                    json={"user_id": str(uuid4())},
                    headers={"Authorization": "Bearer wrong-token"},
                )
        assert resp.status_code == 403
        assert resp.json()["error"] == "Forbidden"


# ---------------------------------------------------------------------------
# AC6.3 + AC2.4: Valid token, banned user -> disconnect
# ---------------------------------------------------------------------------
class TestValidKick:
    @pytest.mark.anyio
    async def test_valid_token_banned_user_kicks(self) -> None:
        """Valid bearer token with banned user calls disconnect_user."""
        user_id = uuid4()
        app = _make_app()
        transport = httpx.ASGITransport(app=app)

        mock_is_banned = AsyncMock(return_value=True)
        mock_disconnect = MagicMock(return_value=3)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            with (
                patch(
                    "promptgrimoire.config.get_settings",
                    return_value=_mock_settings("my-secret"),
                ),
                patch(
                    "promptgrimoire.db.users.is_user_banned",
                    mock_is_banned,
                ),
                patch(
                    "promptgrimoire.auth.client_registry.disconnect_user",
                    mock_disconnect,
                ),
            ):
                resp = await client.post(
                    "/api/admin/kick",
                    json={"user_id": str(user_id)},
                    headers={"Authorization": "Bearer my-secret"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["kicked"] == 3
        assert data["was_banned"] is True
        mock_is_banned.assert_awaited_once_with(user_id)
        mock_disconnect.assert_called_once_with(user_id)

    @pytest.mark.anyio
    async def test_valid_token_not_banned_skips_kick(self) -> None:
        """Valid bearer token with non-banned user returns kicked=0."""
        user_id = uuid4()
        app = _make_app()
        transport = httpx.ASGITransport(app=app)

        mock_is_banned = AsyncMock(return_value=False)
        mock_disconnect = MagicMock(return_value=0)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            with (
                patch(
                    "promptgrimoire.config.get_settings",
                    return_value=_mock_settings("my-secret"),
                ),
                patch(
                    "promptgrimoire.db.users.is_user_banned",
                    mock_is_banned,
                ),
                patch(
                    "promptgrimoire.auth.client_registry.disconnect_user",
                    mock_disconnect,
                ),
            ):
                resp = await client.post(
                    "/api/admin/kick",
                    json={"user_id": str(user_id)},
                    headers={"Authorization": "Bearer my-secret"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["kicked"] == 0
        assert data["was_banned"] is False
        mock_is_banned.assert_awaited_once_with(user_id)
        mock_disconnect.assert_not_called()


# ---------------------------------------------------------------------------
# Invalid user_id -> 400
# ---------------------------------------------------------------------------
class TestInvalidUserId:
    @pytest.mark.anyio
    async def test_missing_user_id_returns_400(self) -> None:
        """POST without user_id in body returns 400."""
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            with patch(
                "promptgrimoire.config.get_settings",
                return_value=_mock_settings("my-secret"),
            ):
                resp = await client.post(
                    "/api/admin/kick",
                    json={},
                    headers={"Authorization": "Bearer my-secret"},
                )
        assert resp.status_code == 400
        assert "user_id" in resp.json()["error"]

    @pytest.mark.anyio
    async def test_invalid_uuid_returns_400(self) -> None:
        """POST with non-UUID user_id returns 400."""
        app = _make_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            with patch(
                "promptgrimoire.config.get_settings",
                return_value=_mock_settings("my-secret"),
            ):
                resp = await client.post(
                    "/api/admin/kick",
                    json={"user_id": "not-a-uuid"},
                    headers={"Authorization": "Bearer my-secret"},
                )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Task 3: Unconfigured secret -> 503 (fail closed)
# ---------------------------------------------------------------------------
class TestUnconfiguredSecret:
    @pytest.mark.anyio
    async def test_empty_secret_returns_503(self) -> None:
        """When ADMIN_API_SECRET is empty, endpoint returns 503."""
        app = _make_app()
        transport = httpx.ASGITransport(app=app)

        mock_disconnect = MagicMock()

        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            with (
                patch(
                    "promptgrimoire.config.get_settings",
                    return_value=_mock_settings(""),  # empty = unconfigured
                ),
                patch(
                    "promptgrimoire.auth.client_registry.disconnect_user",
                    mock_disconnect,
                ),
            ):
                resp = await client.post(
                    "/api/admin/kick",
                    json={"user_id": str(uuid4())},
                    headers={"Authorization": "Bearer some-token"},
                )

        assert resp.status_code == 503
        assert resp.json()["error"] == "ADMIN_API_SECRET not configured"
        # Must not attempt to validate auth or disconnect
        mock_disconnect.assert_not_called()
