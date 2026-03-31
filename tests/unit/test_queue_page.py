"""Tests for /queue raw Starlette HTML page.

Verifies:
- AC4.5: Response is HTMLResponse, no NiceGUI imports
- AC4.1: HTML contains position element
- AC4.2: HTML contains polling JS
- AC4.6: HTML contains expired element with rejoin link
- XSS prevention: script injection in token is escaped
- Open-redirect guard: malicious return URLs default to /
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """Minimal Starlette app with just the queue page route."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    from promptgrimoire.queue_handlers import queue_page_handler

    app = Starlette(routes=[Route("/queue", queue_page_handler, methods=["GET"])])
    return TestClient(app)


class TestQueuePageStructure:
    """AC4.5: raw Starlette HTML, no NiceGUI overhead."""

    def test_returns_html_response(self, client: TestClient) -> None:
        resp = client.get("/queue?t=tok&return=/some/page")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_no_nicegui_in_response(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/queue?t=tok&return=/")
        # NiceGUI injects its own JS/CSS; none should be present
        assert "nicegui" not in resp.text.lower()


class TestQueuePageElements:
    """AC4.1: position element, AC4.6: expired/rejoin."""

    def test_has_position_element(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/queue?t=tok&return=/")
        assert 'id="position"' in resp.text

    def test_has_expired_element(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/queue?t=tok&return=/")
        assert 'id="expired"' in resp.text

    def test_has_rejoin_link(self, client: TestClient) -> None:
        resp = client.get("/queue?t=tok&return=/")
        assert 'id="rejoin"' in resp.text


class TestQueuePagePolling:
    """AC4.2: polls /api/queue/status via vanilla JS."""

    def test_contains_polling_js(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/queue?t=tok&return=/")
        assert "/api/queue/status?t=" in resp.text
        assert "setTimeout(poll" in resp.text
        assert "setTimeout(poll, 5000)" in resp.text


class TestQueuePageXSSPrevention:
    """Token with script injection is JSON-escaped."""

    def test_script_injection_escaped(
        self,
        client: TestClient,
    ) -> None:
        malicious = "</script><script>alert(1)"
        resp = client.get(f"/queue?t={malicious}&return=/")
        # The raw </script> must not appear unescaped
        # json.dumps + replace("</", "<\\/") produces <\/script>
        assert "</script><script>alert(1)" not in resp.text
        assert "<\\/script>" in resp.text


class TestQueuePageOpenRedirectGuard:
    """Malicious return URLs must default to /."""

    def test_javascript_protocol_rejected(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/queue?t=tok&return=javascript:alert(1)")
        # The returnUrl in JS should be "/" not the malicious URL
        assert "javascript:alert(1)" not in resp.text

    def test_protocol_relative_rejected(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/queue?t=tok&return=//evil.com")
        assert "//evil.com" not in resp.text

    def test_absolute_url_rejected(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/queue?t=tok&return=https://evil.com")
        assert "https://evil.com" not in resp.text

    def test_valid_relative_path_accepted(
        self,
        client: TestClient,
    ) -> None:
        resp = client.get("/queue?t=tok&return=/courses/123")
        assert "/courses/123" in resp.text
