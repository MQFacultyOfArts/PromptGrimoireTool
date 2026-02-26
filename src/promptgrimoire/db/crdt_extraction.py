"""CRDT text extraction for FTS indexing.

Provides the pure extraction function used by the search worker to
populate workspace.search_text from CRDT state.  The actual FTS
query lives in db/navigator.py (search_navigator).
"""

from __future__ import annotations

from promptgrimoire.crdt.annotation_doc import AnnotationDocument


def extract_searchable_text(
    crdt_state: bytes | None,
    tag_names: dict[str, str],
) -> str:
    """Extract searchable text from CRDT state for FTS indexing.

    Pure function: deserialises CRDT state and concatenates all
    textual content (highlight text, resolved tag names, comment
    text, response draft markdown, general notes).

    Parameters
    ----------
    crdt_state : bytes | None
        Serialised pycrdt state bytes, or None.
    tag_names : dict[str, str]
        Mapping of tag UUID strings to tag display names.
        Tags not found here are included as-is (legacy BriefTag
        fallback).

    Returns
    -------
    str
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
        if hl_text := highlight.get("text", ""):
            parts.append(hl_text)

        if tag := highlight.get("tag", ""):
            parts.append(tag_names.get(tag, tag))

        for comment in highlight.get("comments", []):
            if comment_text := comment.get("text", ""):
                parts.append(comment_text)

    # Response draft markdown (Tab 3)
    response_draft = doc.get_response_draft_markdown()
    if response_draft:
        parts.append(response_draft)

    # General notes
    general_notes = doc.get_general_notes()
    if general_notes:
        parts.append(general_notes)

    return "\n".join(parts)
