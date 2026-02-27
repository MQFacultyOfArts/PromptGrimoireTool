"""HTML input pipeline for processing various document formats."""

from promptgrimoire.input_pipeline.html_input import (
    CONTENT_TYPES,
    ContentType,
    detect_content_type,
    extract_text_from_html,
    insert_markers_into_dom,
    process_input,
)
from promptgrimoire.input_pipeline.paragraph_map import (
    build_paragraph_map,
    detect_source_numbering,
)

__all__ = [
    "CONTENT_TYPES",
    "ContentType",
    "build_paragraph_map",
    "detect_content_type",
    "detect_source_numbering",
    "extract_text_from_html",
    "insert_markers_into_dom",
    "process_input",
]
