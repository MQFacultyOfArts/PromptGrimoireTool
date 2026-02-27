"""Unit tests for CRDT text extraction for FTS indexing.

Tests the pure extract_searchable_text() function without database access.
Verifies AC8.5 (empty content handling) and correct extraction of highlights,
comments, tag names, response draft, and general notes.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.db.crdt_extraction import extract_searchable_text


def _build_crdt_state(
    *,
    highlights: list[dict[str, Any]] | None = None,
    general_notes: str = "",
    response_draft_markdown: str = "",
) -> bytes:
    """Build a CRDT state blob from structured test data.

    Creates an AnnotationDocument, populates it with the given data,
    and returns the serialised bytes.
    """
    doc = AnnotationDocument("test-extraction")

    for hl in highlights or []:
        highlight_id = doc.add_highlight(
            start_char=int(hl.get("start_char", 0)),
            end_char=int(hl.get("end_char", 10)),
            tag=str(hl.get("tag", "default")),
            text=str(hl.get("text", "")),
            author="test-author",
        )
        comments: list[str] = hl.get("comments", [])
        for comment in comments:
            doc.add_comment(highlight_id, author="test-author", text=str(comment))

    if general_notes:
        doc.set_general_notes(general_notes)

    if response_draft_markdown:
        # Write to the response_draft_markdown Text field directly
        rdm = doc.response_draft_markdown
        rdm += response_draft_markdown

    return doc.get_full_state()


class TestExtractSearchableTextNone:
    """Tests for None crdt_state input."""

    def test_none_crdt_state_returns_empty_string(self) -> None:
        """AC8.5: None crdt_state returns empty string."""
        result = extract_searchable_text(crdt_state=None, tag_names={})
        assert result == ""


class TestExtractSearchableTextHighlights:
    """Tests for highlight text extraction."""

    def test_highlight_text_included(self) -> None:
        """Highlighted source text appears in extracted output."""
        crdt_state = _build_crdt_state(
            highlights=[{"text": "negligence claim", "tag": "legal-issue"}],
        )
        result = extract_searchable_text(crdt_state=crdt_state, tag_names={})
        assert "negligence claim" in result

    def test_multiple_highlights_all_included(self) -> None:
        """All highlights are extracted."""
        crdt_state = _build_crdt_state(
            highlights=[
                {"text": "first highlight", "tag": "tag-a"},
                {"text": "second highlight", "tag": "tag-b"},
            ],
        )
        result = extract_searchable_text(crdt_state=crdt_state, tag_names={})
        assert "first highlight" in result
        assert "second highlight" in result


class TestExtractSearchableTextTagResolution:
    """Tests for tag UUID resolution via tag_names dict."""

    def test_tag_uuid_resolved_to_name(self) -> None:
        """Tag UUID present in tag_names dict is resolved to tag name."""
        tag_uuid = str(uuid4())
        crdt_state = _build_crdt_state(
            highlights=[{"text": "some text", "tag": tag_uuid}],
        )
        result = extract_searchable_text(
            crdt_state=crdt_state,
            tag_names={tag_uuid: "Jurisdiction"},
        )
        assert "Jurisdiction" in result

    def test_tag_uuid_not_in_tag_names_passes_through(self) -> None:
        """Tag string not in tag_names dict appears as-is (legacy fallback)."""
        legacy_tag = "BriefTag:damages"
        crdt_state = _build_crdt_state(
            highlights=[{"text": "some text", "tag": legacy_tag}],
        )
        result = extract_searchable_text(
            crdt_state=crdt_state,
            tag_names={},
        )
        assert legacy_tag in result


class TestExtractSearchableTextComments:
    """Tests for comment text extraction."""

    def test_comment_text_included(self) -> None:
        """Comment text from highlights appears in output."""
        crdt_state = _build_crdt_state(
            highlights=[
                {
                    "text": "highlighted passage",
                    "tag": "analysis",
                    "comments": ["This is an important finding"],
                },
            ],
        )
        result = extract_searchable_text(crdt_state=crdt_state, tag_names={})
        assert "This is an important finding" in result

    def test_multiple_comments_all_included(self) -> None:
        """All comments from a highlight are extracted."""
        crdt_state = _build_crdt_state(
            highlights=[
                {
                    "text": "passage",
                    "tag": "tag",
                    "comments": ["first comment", "second comment"],
                },
            ],
        )
        result = extract_searchable_text(crdt_state=crdt_state, tag_names={})
        assert "first comment" in result
        assert "second comment" in result


class TestExtractSearchableTextResponseDraft:
    """Tests for response draft markdown extraction."""

    def test_response_draft_included(self) -> None:
        """Response draft markdown content appears in output."""
        crdt_state = _build_crdt_state(
            response_draft_markdown="## Analysis\n\nThe plaintiff has a strong case.",
        )
        result = extract_searchable_text(crdt_state=crdt_state, tag_names={})
        assert "The plaintiff has a strong case" in result


class TestExtractSearchableTextGeneralNotes:
    """Tests for general notes extraction."""

    def test_general_notes_included(self) -> None:
        """General notes content appears in output."""
        crdt_state = _build_crdt_state(
            general_notes="Need to review the statute of limitations.",
        )
        result = extract_searchable_text(crdt_state=crdt_state, tag_names={})
        assert "Need to review the statute of limitations" in result


class TestExtractSearchableTextCombined:
    """Tests for combined extraction from all sources."""

    def test_all_sources_combined(self) -> None:
        """Output contains text from all sources.

        Checks highlights, comments, tags, notes, and draft.
        """
        tag_uuid = str(uuid4())
        crdt_state = _build_crdt_state(
            highlights=[
                {
                    "text": "workplace injury",
                    "tag": tag_uuid,
                    "comments": ["Relates to duty of care"],
                },
            ],
            general_notes="Key case for tort analysis",
            response_draft_markdown="The defendant breached their duty",
        )
        result = extract_searchable_text(
            crdt_state=crdt_state,
            tag_names={tag_uuid: "Negligence"},
        )
        assert "workplace injury" in result
        assert "Negligence" in result
        assert "Relates to duty of care" in result
        assert "Key case for tort analysis" in result
        assert "The defendant breached their duty" in result
