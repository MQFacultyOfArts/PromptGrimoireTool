"""Data models for legal case documents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedRTF:
    """Result of parsing an RTF file for case brief annotation.

    Attributes:
        original_blob: Raw RTF file content as bytes for DB storage.
        html: LibreOffice HTML output for faithful browser rendering.
        source_filename: Original filename for metadata.
    """

    original_blob: bytes
    html: str
    source_filename: str
