"""Standalone snapshot delivery service.

Serves the initial annotation bundle (document HTML, highlights, tags,
sidebar items) from its own process so the NiceGUI event loop never
constructs or transmits it — the Phase 9 constraint (see
docs/design-notes/2026-08-16-initial-snapshot-delivery.md).

Entry point mirrors the export worker: ``python -m
promptgrimoire.snapshot_service``.  The app itself is plain FastAPI and
is exercised in-process by tests/integration/test_snapshot_service.py.
"""

from __future__ import annotations

import asyncio
import sys

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from promptgrimoire import sd_notify
from promptgrimoire.config import get_settings
from promptgrimoire.snapshot import build_snapshot_bundle, verify_snapshot_token

logger = structlog.get_logger()


def create_app(*, allow_origin: str) -> FastAPI:
    """Build the snapshot service ASGI app.

    One bundle endpoint plus a health probe.  The endpoint verifies the
    HMAC token minted by the NiceGUI process and adds no authorization of
    its own; 403 for any token failure, 404 when the workspace or
    document is gone.

    The bundle fetch is a CORS "simple request" (GET, no custom headers),
    so a response header per response replaces middleware: no preflight
    ever arrives.
    """
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    cors = {"Access-Control-Allow-Origin": allow_origin}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/snapshot")
    async def get_snapshot(t: str = "") -> JSONResponse:
        secret = get_settings().app.storage_secret.get_secret_value()
        claims = verify_snapshot_token(t, secret=secret)
        if claims is None:
            return JSONResponse({"detail": "invalid token"}, 403, headers=cors)
        bundle = await build_snapshot_bundle(claims)
        if bundle is None:
            logger.warning(
                "snapshot_not_found",
                workspace_id=claims.workspace_id,
                document_id=claims.document_id,
            )
            return JSONResponse({"detail": "not found"}, 404, headers=cors)
        logger.info(
            "snapshot_served",
            workspace_id=claims.workspace_id,
            document_id=claims.document_id,
            document_html_len=len(bundle["document_html"]),
            item_count=len(bundle["items"]),
        )
        return JSONResponse(bundle, headers=cors | {"Cache-Control": "no-store"})

    return app


async def main() -> int:
    """Run the standalone snapshot service until SIGTERM/SIGINT.

    uvicorn installs its own signal handlers; ``serve()`` returns after a
    graceful shutdown.
    """
    # Local imports: keep create_app importable without engine/log setup.
    from promptgrimoire.db import close_db, init_db  # noqa: PLC0415
    from promptgrimoire.logging_config import setup_logging  # noqa: PLC0415

    setup_logging()
    settings = get_settings()
    logger.info(
        "snapshot_service_starting",
        port=settings.snapshot.port,
        allow_origin=settings.snapshot.allow_origin,
    )
    await init_db()

    config = uvicorn.Config(
        create_app(allow_origin=settings.snapshot.allow_origin),
        host="127.0.0.1",
        port=settings.snapshot.port,
        log_config=None,
    )
    server = uvicorn.Server(config)
    sd_notify.notify("READY=1")
    await server.serve()

    sd_notify.notify("STOPPING=1")
    await close_db()
    logger.info("snapshot_service_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
