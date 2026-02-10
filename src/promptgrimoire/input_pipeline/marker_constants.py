"""Marker format constants for HTML annotation markers.

These marker strings are inserted into HTML at character positions matching
the UI's extract_text_from_html character indexing. They survive Pandoc
HTML-to-LaTeX conversion as plain text.

Used by input_pipeline/html_input.py (insert_markers_into_dom).
"""

from __future__ import annotations

import re

# Unique marker format that survives Pandoc conversion
# Format: ANNMARKER{index}ENDMARKER for annotation insertion point
# Format: HLSTART{index}ENDHL and HLEND{index}ENDHL for highlight boundaries
MARKER_TEMPLATE = "ANNMARKER{}ENDMARKER"
MARKER_PATTERN = re.compile(r"ANNMARKER(\d+)ENDMARKER")
HLSTART_TEMPLATE = "HLSTART{}ENDHL"
HLEND_TEMPLATE = "HLEND{}ENDHL"
HLSTART_PATTERN = re.compile(r"HLSTART(\d+)ENDHL")
HLEND_PATTERN = re.compile(r"HLEND(\d+)ENDHL")
