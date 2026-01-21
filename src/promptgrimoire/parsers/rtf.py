"""Parser for RTF (Rich Text Format) court judgment files."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from promptgrimoire.models import ParsedRTF

# Maximum file size: 10MB (per PRD security requirements)
_MAX_FILE_SIZE = 10 * 1024 * 1024


def parse_rtf(path: Path) -> ParsedRTF:
    """Parse an RTF file to HTML.

    Uses LibreOffice for HTML conversion (preserves styles/layout).

    Args:
        path: Path to the RTF file.

    Returns:
        ParsedRTF with original blob and HTML.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file is too large, not valid RTF, or conversion fails.
    """
    if not path.exists():
        raise FileNotFoundError(f"RTF file not found: {path}")

    # Check file size before reading
    file_size = path.stat().st_size
    if file_size > _MAX_FILE_SIZE:
        msg = f"RTF file exceeds 10MB limit ({file_size} bytes): {path}"
        raise ValueError(msg)

    # Read raw bytes
    original_blob = path.read_bytes()

    # Validate RTF format
    if not original_blob.lstrip().startswith(b"{\\rtf"):
        raise ValueError(f"File does not appear to be valid RTF: {path}")

    # Convert to HTML using LibreOffice (preserves styles)
    html = _convert_rtf_to_html_libreoffice(path)

    return ParsedRTF(
        original_blob=original_blob,
        html=html,
        source_filename=path.name,
    )


def _convert_rtf_to_html_libreoffice(path: Path) -> str:
    """Convert RTF to HTML using LibreOffice headless mode.

    LibreOffice preserves RTF styles, fonts, and layout better than pandoc.

    Args:
        path: Path to the RTF file.

    Returns:
        HTML string with embedded styles.

    Raises:
        ValueError: If LibreOffice conversion fails.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "html",
                "--outdir",
                tmpdir,
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,  # We handle errors manually
        )

        if result.returncode != 0:
            raise ValueError(f"LibreOffice conversion failed: {result.stderr}")

        # LibreOffice outputs filename.html
        html_filename = path.stem + ".html"
        html_path = Path(tmpdir) / html_filename

        try:
            return html_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ValueError(
                f"LibreOffice did not produce expected output: {html_filename}"
            ) from None
