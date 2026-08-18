"""Integration tests for the standalone snapshot service ASGI app.

Exercises the FastAPI app in-process via httpx's ASGI transport: token
enforcement (signature, expiry), bundle delivery, CORS and cache headers.
The process lifecycle (uvicorn entry point) is exercised by the E2E lane.

Design: docs/design-notes/2026-08-16-initial-snapshot-delivery.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from promptgrimoire.config import get_settings
from promptgrimoire.snapshot import SnapshotClaims, mint_snapshot_token

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)

_ORIGIN = "http://testserver-app.example"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from promptgrimoire.snapshot_service import create_app

    app = create_app(allow_origin=_ORIGIN)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://snapshot.test"
    ) as c:
        yield c


def _secret() -> str:
    return get_settings().app.storage_secret.get_secret_value()


class TestSnapshotEndpointAuth:
    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/snapshot")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_garbage_token_rejected(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/snapshot", params={"t": "not-a-token"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client: httpx.AsyncClient) -> None:
        claims = SnapshotClaims(
            workspace_id=str(uuid4()),
            document_id=str(uuid4()),
            user_id="u-x",
            viewer_is_privileged=False,
            can_annotate=True,
            anonymous_sharing=False,
        )
        stale = mint_snapshot_token(claims, secret=_secret(), now=1000.0)
        response = await client.get("/snapshot", params={"t": stale})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_valid_token_missing_workspace_is_404(
        self, client: httpx.AsyncClient
    ) -> None:
        claims = SnapshotClaims(
            workspace_id=str(uuid4()),
            document_id=str(uuid4()),
            user_id="u-x",
            viewer_is_privileged=False,
            can_annotate=True,
            anonymous_sharing=False,
        )
        token = mint_snapshot_token(claims, secret=_secret())
        response = await client.get("/snapshot", params={"t": token})
        assert response.status_code == 404


class TestSnapshotEndpointDelivery:
    @pytest.mark.asyncio
    async def test_valid_token_returns_bundle_with_headers(
        self, client: httpx.AsyncClient
    ) -> None:
        from tests.integration.test_snapshot_bundle import _seed_snapshot_workspace

        ws_id, doc_id, _other, tag_a, _tag_b = await _seed_snapshot_workspace()
        claims = SnapshotClaims(
            workspace_id=str(ws_id),
            document_id=str(doc_id),
            user_id="u-alice",
            viewer_is_privileged=False,
            can_annotate=True,
            anonymous_sharing=False,
        )
        token = mint_snapshot_token(claims, secret=_secret())
        response = await client.get(
            "/snapshot", params={"t": token}, headers={"Origin": _ORIGIN}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["access-control-allow-origin"] == _ORIGIN

        bundle = response.json()
        assert "quick brown fox" in bundle["document_html"]
        assert tag_a in bundle["highlights"]
        assert len(bundle["items"]) == 2
        assert bundle["permissions"] == {"can_annotate": True}
