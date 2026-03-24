"""Download route for token-based PDF delivery.

Serves compiled PDFs via time-limited download tokens created by
the export worker after successful LaTeX compilation.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from nicegui import app
from starlette.responses import FileResponse, JSONResponse, Response

from promptgrimoire.db.export_jobs import get_job_by_token

logger = structlog.get_logger()


@app.get("/export/{token}/download")
async def download_export(token: str) -> Response:
    """Serve a compiled PDF via download token."""
    job = await get_job_by_token(token)

    if job is None:
        return JSONResponse(
            {"detail": "Export not found or expired"},
            status_code=404,
        )

    if job.pdf_path is None:
        logger.warning("export_pdf_path_null", export_job_id=str(job.id))
        return JSONResponse(
            {"detail": "Export file not available"},
            status_code=404,
        )

    pdf_path = Path(job.pdf_path)
    if not pdf_path.exists():
        logger.warning(
            "export_pdf_missing",
            export_job_id=str(job.id),
            pdf_path=str(pdf_path),
        )
        return JSONResponse(
            {"detail": "Export file no longer available"},
            status_code=404,
        )

    logger.info("export_pdf_served", export_job_id=str(job.id))
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
    )
