"""Converters for DOCX and PDF files to HTML.

DOCX uses mammoth (sync, in-memory).
PDF uses pymupdf4llm for extraction + pandoc for HTML conversion (async).
"""

from __future__ import annotations

import asyncio
import io
import logging
import subprocess

import fitz
import mammoth
import pymupdf4llm

logger = logging.getLogger(__name__)


def convert_docx_to_html(content: bytes) -> str:
    """Convert DOCX bytes to HTML string.

    Raises:
        ValueError: If the content is not a valid DOCX file.
    """
    try:
        result = mammoth.convert_to_html(io.BytesIO(content))
    except Exception as exc:
        msg = f"Failed to convert DOCX: {exc}"
        raise ValueError(msg) from exc

    for message in result.messages:
        logger.warning("mammoth: %s", message)

    return result.value


async def convert_pdf_to_html(content: bytes) -> str:
    """Convert PDF bytes to HTML string via pymupdf4llm + pandoc.

    Raises:
        ValueError: If the content is not a valid PDF or pandoc fails.
    """
    if not content:
        msg = "Failed to convert PDF: empty content"
        raise ValueError(msg)

    try:
        doc = fitz.open(stream=content, filetype="pdf")
        markdown = pymupdf4llm.to_markdown(doc)
    except RuntimeError as exc:
        msg = f"Failed to convert PDF: {exc}"
        raise ValueError(msg) from exc

    proc = await asyncio.create_subprocess_exec(
        "pandoc",
        "-f",
        "markdown",
        "-t",
        "html",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate(
        input=markdown.encode(),
    )
    # returncode is guaranteed set after communicate() returns
    if proc.returncode and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode,
            ["pandoc"],
            stderr_bytes.decode(),
        )

    return stdout_bytes.decode()
