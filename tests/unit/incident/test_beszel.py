"""Tests for Beszel metrics fetcher with mocked PocketBase API.

Verifies:
- Successful fetch: mock httpx response with realistic PocketBase JSON
  returns correct list of dicts with normalised column names
- Pagination: mock 2-page response returns all records from both pages
- Empty result: mock empty ``items`` array returns empty list
- Connection error: mock ``httpx.ConnectError`` raises ``SystemExit``
- HTTP error (e.g. 404): mock 404 response raises ``SystemExit``
- Compact key mapping: ``b`` -> ``net_sent/net_recv``,
  ``la`` -> ``load_1/5/15``, ``dr/dw`` -> ``disk_read/write``, etc.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from scripts.incident.parsers.beszel import fetch_beszel_metrics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HUB_URL = "http://localhost:8090"
START_UTC = "2026-03-16T05:00:00Z"
END_UTC = "2026-03-16T06:00:00Z"


def _make_record(
    created: str = "2026-03-16 05:30:00.000Z",
    *,
    cpu: float = 42.5,
    mu: float = 3200.0,
    mp: float = 78.1,
    b: list[float] | None = None,
    dr: float = 512.0,
    dw: float = 256.0,
    la: list[float] | None = None,
) -> dict:
    """Build a realistic PocketBase system_stats record.

    Uses the real Beszel v0.9+ stat key format:
    - ``b``: bandwidth ``[sent, recv]`` in bytes/s
    - ``la``: load average ``[1m, 5m, 15m]``
    """
    if b is None:
        b = [1024.0, 2048.0]
    if la is None:
        la = [1.2, 0.8, 0.5]
    return {
        "id": "abc123",
        "collectionId": "xyz",
        "collectionName": "system_stats",
        "created": created,
        "updated": created,
        "stats": {
            "cpu": cpu,
            "mu": mu,
            "mp": mp,
            "b": b,
            "dr": dr,
            "dw": dw,
            "la": la,
        },
        "system": "system-id",
        "type": "main",
    }


def _make_response(
    items: list[dict],
    page: int = 1,
    total_pages: int = 1,
    total_items: int | None = None,
    status_code: int = 200,
) -> MagicMock:
    """Build a mock httpx.Response with PocketBase list structure."""
    if total_items is None:
        total_items = len(items)
    body = {
        "page": page,
        "perPage": 200,
        "totalPages": total_pages,
        "totalItems": total_items,
        "items": items,
    }
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error",
            request=MagicMock(),
            response=resp,
        )
    return resp


def _make_auth_response() -> MagicMock:
    """Build a mock auth response with a token."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"token": "mock-token-abc"}
    return resp


def _patch_client_with_auth(records_resp):
    """Set up mock httpx.Client with auth + records responses.

    Returns the patch context manager. The client's POST returns
    the auth response, GET returns the records response.
    """
    p = patch("httpx.Client")

    def setup(MockClient):
        client_instance = MockClient.return_value.__enter__.return_value
        client_instance.post.return_value = _make_auth_response()
        if isinstance(records_resp, list):
            client_instance.get.side_effect = records_resp
        else:
            client_instance.get.return_value = records_resp
        return client_instance

    return p, setup


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# Patch env vars for all tests so _load_beszel_creds doesn't fail
_CRED_ENV = {
    "BESZEL_EMAIL": "test@example.com",
    "BESZEL_PASSWORD": "testpass",
}


class TestSuccessfulFetch:
    """Fetch returns correctly normalised dicts."""

    @patch.dict("os.environ", _CRED_ENV)
    def test_single_record(self) -> None:
        record = _make_record(created="2026-03-16 05:30:00.000Z")
        mock_resp = _make_response([record])

        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.return_value = mock_resp

            result = fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

        assert len(result) == 1
        row = result[0]
        assert row["ts_utc"] == "2026-03-16 05:30:00.000Z"
        assert row["cpu"] == 42.5
        assert row["mem_used"] == 3200.0
        assert row["mem_percent"] == 78.1
        assert row["net_sent"] == 1024.0
        assert row["net_recv"] == 2048.0
        assert row["disk_read"] == 512.0
        assert row["disk_write"] == 256.0
        assert row["load_1"] == 1.2
        assert row["load_5"] == 0.8
        assert row["load_15"] == 0.5


class TestCompactKeyMapping:
    """Compact JSON keys map to normalised column names."""

    @patch.dict("os.environ", _CRED_ENV)
    def test_bandwidth_maps_to_net_sent_recv(self) -> None:
        record = _make_record(b=[9999.0, 8888.0])
        mock_resp = _make_response([record])

        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.return_value = mock_resp

            result = fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

        assert result[0]["net_sent"] == 9999.0
        assert result[0]["net_recv"] == 8888.0

    @patch.dict("os.environ", _CRED_ENV)
    def test_dr_dw_map_to_disk_read_write(self) -> None:
        record = _make_record(dr=100.0, dw=200.0)
        mock_resp = _make_response([record])

        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.return_value = mock_resp

            result = fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

        assert result[0]["disk_read"] == 100.0
        assert result[0]["disk_write"] == 200.0

    @patch.dict("os.environ", _CRED_ENV)
    def test_load_average_array_maps(self) -> None:
        record = _make_record(la=[3.0, 2.0, 1.0])
        mock_resp = _make_response([record])

        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.return_value = mock_resp

            result = fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

        assert result[0]["load_1"] == 3.0
        assert result[0]["load_5"] == 2.0
        assert result[0]["load_15"] == 1.0

    @patch.dict("os.environ", _CRED_ENV)
    def test_mu_maps_to_mem_used(self) -> None:
        record = _make_record(mu=4096.0)
        mock_resp = _make_response([record])

        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.return_value = mock_resp

            result = fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

        assert result[0]["mem_used"] == 4096.0


class TestPagination:
    """Multi-page responses return all records."""

    @patch.dict("os.environ", _CRED_ENV)
    def test_two_pages(self) -> None:
        page1_record = _make_record(created="2026-03-16 05:10:00.000Z", cpu=10.0)
        page2_record = _make_record(created="2026-03-16 05:20:00.000Z", cpu=20.0)

        resp_page1 = _make_response(
            [page1_record], page=1, total_pages=2, total_items=2
        )
        resp_page2 = _make_response(
            [page2_record], page=2, total_pages=2, total_items=2
        )

        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.side_effect = [resp_page1, resp_page2]

            result = fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

        assert len(result) == 2
        assert result[0]["cpu"] == 10.0
        assert result[1]["cpu"] == 20.0


class TestEmptyResult:
    """Empty items array returns empty list."""

    @patch.dict("os.environ", _CRED_ENV)
    def test_empty_items(self) -> None:
        mock_resp = _make_response([], total_items=0)

        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.return_value = mock_resp

            result = fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

        assert result == []


class TestConnectionError:
    """Connection errors raise SystemExit with clear message."""

    @patch.dict("os.environ", _CRED_ENV)
    def test_connect_error(self) -> None:
        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(SystemExit) as exc_info:
                fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

            assert exc_info.value.code == 1


class TestHTTPError:
    """HTTP errors raise SystemExit with status code in message."""

    @patch.dict("os.environ", _CRED_ENV)
    def test_404_response(self) -> None:
        mock_resp = _make_response([], status_code=404)

        with patch("httpx.Client") as MockClient:
            client = MockClient.return_value.__enter__.return_value
            client.post.return_value = _make_auth_response()
            client.get.return_value = mock_resp

            with pytest.raises(SystemExit) as exc_info:
                fetch_beszel_metrics(HUB_URL, START_UTC, END_UTC)

            assert exc_info.value.code == 1
