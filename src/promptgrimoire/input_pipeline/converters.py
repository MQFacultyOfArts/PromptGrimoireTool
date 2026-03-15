"""Converters for DOCX and PDF files to HTML.

DOCX uses mammoth (sync, in-memory).
PDF uses pymupdf4llm for extraction + pandoc for HTML conversion (async).
"""

from __future__ import annotations

import asyncio
import io
import logging
import re

import fitz
import mammoth
import pymupdf4llm
import structlog

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)


def convert_docx_to_html(content: bytes) -> str:
    """Convert DOCX bytes to HTML string.

    Raises:
        ValueError: If the content is not a valid DOCX file.
    """
    try:
        result = mammoth.convert_to_html(
            io.BytesIO(content),
            convert_image=lambda _image: [],
        )
    except Exception as exc:
        msg = f"Failed to convert DOCX: {exc}"
        raise ValueError(msg) from exc

    for message in result.messages:
        logger.warning("mammoth: %s", message)

    return result.value


_BULLET_FENCE_RE = re.compile(r"```\n(.*?)\n```", re.DOTALL)


def strip_bullet_code_fences(markdown: str) -> str:
    """Remove code fences that wrap bullet-point lists.

    pymupdf4llm sometimes wraps bullet lists in triple-backtick code fences,
    which pandoc renders as ``<pre><code>`` blocks instead of ``<ul><li>``
    lists.  This function strips the fences when ALL non-blank lines inside
    start with ``- `` (optionally indented).

    See: https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/349
    """
    if not markdown:
        return markdown

    def _replace(match: re.Match[str]) -> str:
        content = match.group(1)
        non_blank = [line for line in content.split("\n") if line.strip()]
        if non_blank and all(re.match(r"\s*- ", line) for line in non_blank):
            return content
        return match.group(0)

    return _BULLET_FENCE_RE.sub(_replace, markdown)


async def convert_pdf_to_html(content: bytes) -> str:
    """Convert PDF bytes to HTML string via pymupdf4llm + pandoc.

    Raises:
        ValueError: If the content is not a valid PDF or pandoc fails.
    """
    if not content:
        msg = "Failed to convert PDF: empty content"
        raise ValueError(msg)

    def _extract_markdown() -> str:
        doc = fitz.open(stream=content, filetype="pdf")
        return pymupdf4llm.to_markdown(doc, ignore_images=True)

    try:
        loop = asyncio.get_running_loop()
        markdown = await loop.run_in_executor(None, _extract_markdown)
    except RuntimeError as exc:
        msg = f"Failed to convert PDF: {exc}"
        raise ValueError(msg) from exc

    markdown = strip_bullet_code_fences(markdown)

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
    if proc.returncode != 0:
        raise ValueError(
            f"pandoc failed (rc={proc.returncode}): {stderr_bytes.decode()}"
        ) from None

    return stdout_bytes.decode()
