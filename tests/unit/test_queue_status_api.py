"""Tests for /api/queue/status Starlette endpoint.

Verifies:
- AC4.3: Valid token returns position/total/admitted/expired JSON
- AC4.4: Invalid or missing token returns admitted=false, expired=true
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Generator

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def mock_state() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_state: MagicMock) -> Generator[TestClient]:
    """Minimal Starlette app with just the queue status route."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    from promptgrimoire.queue_handlers import queue_status_handler

    app = Starlette(
        routes=[Route("/api/queue/status", queue_status_handler, methods=["GET"])]
    )

    with patch("promptgrimoire.admission.get_admission_state", return_value=mock_state):
        yield TestClient(app)


class TestQueueStatusQueued:
    """AC4.3: queued user gets position and total."""

    def test_returns_position_and_total(
        self, client: TestClient, mock_state: MagicMock
    ) -> None:
        mock_state.get_queue_status.return_value = {
            "position": 2,
            "total": 5,
            "admitted": False,
            "expired": False,
        }
        with patch(
            "promptgrimoire.admission.get_admission_state", return_value=mock_state
        ):
            resp = client.get("/api/queue/status?t=some-token")

        assert resp.status_code == 200
        data = resp.json()
        assert data["position"] == 2
        assert data["total"] == 5
        assert data["admitted"] is False
        assert data["expired"] is False
        mock_state.get_queue_status.assert_called_with("some-token")


class TestQueueStatusAdmitted:
    """AC4.3: admitted user gets admitted=true."""

    def test_returns_admitted_true(
        self, client: TestClient, mock_state: MagicMock
    ) -> None:
        mock_state.get_queue_status.return_value = {
            "position": 0,
            "total": 5,
            "admitted": True,
            "expired": False,
        }
        with patch(
            "promptgrimoire.admission.get_admission_state", return_value=mock_state
        ):
            resp = client.get("/api/queue/status?t=valid-admitted-token")

        assert resp.status_code == 200
        data = resp.json()
        assert data["admitted"] is True
        assert data["expired"] is False


class TestQueueStatusInvalidToken:
    """AC4.4: invalid token returns expired=true."""

    def test_invalid_token(self, client: TestClient, mock_state: MagicMock) -> None:
        mock_state.get_queue_status.return_value = {
            "position": 0,
            "total": 0,
            "admitted": False,
            "expired": True,
        }
        with patch(
            "promptgrimoire.admission.get_admission_state", return_value=mock_state
        ):
            resp = client.get("/api/queue/status?t=invalid-token")

        assert resp.status_code == 200
        data = resp.json()
        assert data["admitted"] is False
        assert data["expired"] is True

    def test_missing_token(self, client: TestClient, mock_state: MagicMock) -> None:
        mock_state.get_queue_status.return_value = {
            "position": 0,
            "total": 0,
            "admitted": False,
            "expired": True,
        }
        with patch(
            "promptgrimoire.admission.get_admission_state", return_value=mock_state
        ):
            resp = client.get("/api/queue/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["admitted"] is False
        assert data["expired"] is True
        mock_state.get_queue_status.assert_called_with("")
