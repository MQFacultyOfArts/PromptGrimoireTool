"""Full-text search infrastructure for workspace content.

Provides CRDT text extraction for FTS indexing and query helpers
for searching workspace documents and CRDT-sourced text.
"""

from __future__ import annotations

import logging

from promptgrimoire.crdt.annotation_doc import AnnotationDocument

logger = logging.getLogger(__name__)


def extract_searchable_text(
    crdt_state: bytes | None,
    tag_names: dict[str, str],
) -> str:
    """Extract searchable text from CRDT state for FTS indexing.

    Pure function: deserialises CRDT state and concatenates all
    textual content (highlight text, resolved tag names, comment
    text, response draft markdown, general notes).

    Args:
        crdt_state: Serialised pycrdt state bytes, or None.
        tag_names: Mapping of tag UUID strings to tag display
            names. Tags not found here are included as-is
            (legacy BriefTag fallback).

    Returns:
        Concatenated searchable text, or empty string if
        crdt_state is None.
    """
    if crdt_state is None:
        return ""

    doc = AnnotationDocument("extraction-tmp")
    doc.apply_update(crdt_state)

    parts: list[str] = []

    # Extract from highlights: text, resolved tags, comments
    for highlight in doc.get_all_highlights():
        hl_text = highlight.get("text", "")
        if hl_text:
            parts.append(str(hl_text))

        tag_raw = highlight.get("tag", "")
        if tag_raw:
            tag_str = str(tag_raw)
            resolved = tag_names.get(tag_str, tag_str)
            parts.append(resolved)

        for comment in highlight.get("comments", []):
            comment_text = comment.get("text", "")
            if comment_text:
                parts.append(str(comment_text))

    # Response draft markdown (Tab 3)
    response_draft = doc.get_response_draft_markdown()
    if response_draft:
        parts.append(response_draft)

    # General notes
    general_notes = doc.get_general_notes()
    if general_notes:
        parts.append(general_notes)

    return "\n".join(parts)
