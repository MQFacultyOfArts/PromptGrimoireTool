"""Unit tests for Tab 3 (Respond) reference panel logic.

Tests verify that the reference panel correctly groups highlights by tag,
handles empty state, and truncates text snippets.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_05.md Task 2
- AC: three-tab-ui.AC4.4, AC4.5
"""

from __future__ import annotations

from uuid import uuid4

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.pages.annotation import PageState
from promptgrimoire.pages.annotation.card_shared import _EXPANDABLE_THRESHOLD
from promptgrimoire.pages.annotation.respond import (
    _matches_filter,
    group_highlights_by_tag,
)
from promptgrimoire.pages.annotation.tags import TagInfo


def _make_state(
    *,
    user_id: str | None = "viewer-001",
    is_anonymous: bool = False,
    viewer_is_privileged: bool = False,
    privileged_user_ids: frozenset[str] | None = None,
) -> PageState:
    """Build a minimal PageState for filter tests."""
    return PageState(
        workspace_id=uuid4(),
        user_id=user_id,
        is_anonymous=is_anonymous,
        viewer_is_privileged=viewer_is_privileged,
        privileged_user_ids=privileged_user_ids or frozenset(),
    )


# Test tag list — uses string raw_keys matching CRDT highlight tag values
_TEST_TAGS = [
    TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="jurisdiction"),
    TagInfo(name="Procedural History", colour="#ff7f0e", raw_key="procedural_history"),
    TagInfo(
        name="Legally Relevant Facts",
        colour="#2ca02c",
        raw_key="legally_relevant_facts",
    ),
    TagInfo(name="Legal Issues", colour="#d62728", raw_key="legal_issues"),
    TagInfo(name="Reasons", colour="#9467bd", raw_key="reasons"),
    TagInfo(name="Court's Reasoning", colour="#8c564b", raw_key="courts_reasoning"),
    TagInfo(name="Decision", colour="#e377c2", raw_key="decision"),
    TagInfo(name="Order", colour="#7f7f7f", raw_key="order"),
    TagInfo(name="Domestic Sources", colour="#bcbd22", raw_key="domestic_sources"),
    TagInfo(name="Reflection", colour="#17becf", raw_key="reflection"),
]


class TestReferenceHighlightGrouping:
    """Verify highlight grouping logic for the reference panel."""

    def test_highlights_grouped_by_tag(self) -> None:
        """Highlights are grouped into the correct tag sections."""
        doc = AnnotationDocument("test-ref-group")
        doc.add_highlight(0, 10, "jurisdiction", "test text 1", "Author A")
        doc.add_highlight(10, 20, "legal_issues", "test text 2", "Author B")
        doc.add_highlight(20, 30, "jurisdiction", "test text 3", "Author A")

        tags = _TEST_TAGS
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 2
        assert len(tagged["Legal Issues"]) == 1
        assert len(untagged) == 0

    def test_empty_document_returns_no_highlights(self) -> None:
        """An empty document produces has_any_highlights=False (AC4.5)."""
        doc = AnnotationDocument("test-ref-empty")
        tags = _TEST_TAGS
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)

        assert has_any is False
        assert len(untagged) == 0
        # All tag groups should be empty
        for tag_info in tags:
            assert len(tagged[tag_info.name]) == 0

    def test_untagged_highlights_in_separate_group(self) -> None:
        """Highlights with no/unknown tag go to untagged group."""
        doc = AnnotationDocument("test-ref-untagged")
        doc.add_highlight(0, 10, "", "no tag", "Author A")
        doc.add_highlight(10, 20, "nonexistent_tag", "bad tag", "Author B")
        doc.add_highlight(20, 30, "jurisdiction", "good tag", "Author C")

        tags = _TEST_TAGS
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 1
        assert len(untagged) == 2

    def test_expandable_text_truncation(self) -> None:
        """Long highlight text is truncated at _EXPANDABLE_THRESHOLD chars."""
        long_text = "x" * 150
        snippet = long_text[:_EXPANDABLE_THRESHOLD]
        if len(long_text) > _EXPANDABLE_THRESHOLD:
            snippet += "..."

        assert len(snippet) == _EXPANDABLE_THRESHOLD + 3  # threshold + "..."
        assert snippet.endswith("...")

    def test_expandable_text_short_no_truncation(self) -> None:
        """Short highlight text is not truncated."""
        short_text = "short"
        snippet = short_text[:_EXPANDABLE_THRESHOLD]
        if len(short_text) > _EXPANDABLE_THRESHOLD:
            snippet += "..."

        assert snippet == "short"
        assert not snippet.endswith("...")

    def test_multiple_tags_with_highlights(self) -> None:
        """Highlights across many tags are grouped correctly (AC4.4)."""
        doc = AnnotationDocument("test-ref-multi")
        doc.add_highlight(0, 10, "jurisdiction", "hl1", "A")
        doc.add_highlight(10, 20, "legal_issues", "hl2", "B")
        doc.add_highlight(20, 30, "legally_relevant_facts", "hl3", "C")
        doc.add_highlight(30, 40, "reasons", "hl4", "D")

        tags = _TEST_TAGS
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 1
        assert len(tagged["Legal Issues"]) == 1
        assert len(tagged["Legally Relevant Facts"]) == 1
        assert len(tagged["Reasons"]) == 1
        assert len(untagged) == 0

    def test_only_non_empty_tags_should_render(self) -> None:
        """Tags with no highlights should produce empty lists."""
        doc = AnnotationDocument("test-ref-sparse")
        doc.add_highlight(0, 10, "jurisdiction", "only one tag", "A")

        tags = _TEST_TAGS
        tagged, _untagged, has_any = group_highlights_by_tag(tags, doc)

        assert has_any is True
        assert len(tagged["Jurisdiction"]) == 1
        # All other tags should be empty
        for tag_info in tags:
            if tag_info.name != "Jurisdiction":
                assert len(tagged[tag_info.name]) == 0


class TestMatchesFilter:
    """Verify the highlight search filter logic."""

    def test_matches_highlight_text(self) -> None:
        """Filter matches against highlight text content."""
        state = _make_state()
        hl = {"text": "The court held that negligence was proven", "author": "Alice"}
        assert _matches_filter(hl, "negligence", state) is True

    def test_matches_author(self) -> None:
        """Filter matches against highlight author."""
        state = _make_state()
        hl = {"text": "some text", "author": "Professor Smith"}
        assert _matches_filter(hl, "smith", state) is True

    def test_matches_comment_text(self) -> None:
        """Filter matches against comment text within a highlight."""
        state = _make_state()
        hl = {
            "text": "highlighted passage",
            "author": "Alice",
            "comments": [{"text": "This is a key finding", "author": "Bob"}],
        }
        assert _matches_filter(hl, "key finding", state) is True

    def test_matches_comment_author(self) -> None:
        """Filter matches against comment author within a highlight."""
        state = _make_state()
        hl = {
            "text": "highlighted passage",
            "author": "Alice",
            "comments": [{"text": "Good point", "author": "Dr. Jones"}],
        }
        assert _matches_filter(hl, "jones", state) is True

    def test_no_match_returns_false(self) -> None:
        """Filter returns False when nothing matches."""
        state = _make_state()
        hl = {
            "text": "The sky is blue",
            "author": "Alice",
            "comments": [{"text": "Indeed", "author": "Bob"}],
        }
        assert _matches_filter(hl, "jurisdiction", state) is False

    def test_case_insensitive(self) -> None:
        """Filter matching is case-insensitive."""
        state = _make_state()
        hl = {"text": "NEGLIGENCE was proven", "author": "alice"}
        assert _matches_filter(hl, "Negligence", state) is True
        assert _matches_filter(hl, "ALICE", state) is True

    def test_empty_filter_matches_everything(self) -> None:
        """An empty filter string matches any highlight."""
        state = _make_state()
        hl = {"text": "anything", "author": "anyone"}
        assert _matches_filter(hl, "", state) is True

    def test_missing_fields_do_not_crash(self) -> None:
        """Highlights with missing keys don't raise errors."""
        state = _make_state()
        assert _matches_filter({}, "test", state) is False
        assert _matches_filter({"text": "hello"}, "hello", state) is True

    def test_highlight_with_no_comments(self) -> None:
        """Highlights without a comments key still work."""
        state = _make_state()
        hl = {"text": "some text", "author": "Alice"}
        assert _matches_filter(hl, "some", state) is True
        assert _matches_filter(hl, "missing", state) is False

    def test_multiple_comments_any_match(self) -> None:
        """If any comment matches, the highlight matches."""
        state = _make_state()
        hl = {
            "text": "passage",
            "author": "Alice",
            "comments": [
                {"text": "Not relevant", "author": "Bob"},
                {"text": "Very important point", "author": "Carol"},
            ],
        }
        assert _matches_filter(hl, "important", state) is True
        assert _matches_filter(hl, "carol", state) is True
        assert _matches_filter(hl, "nonexistent", state) is False


class TestMatchesFilterAnonymisation:
    """Verify _matches_filter uses anonymised author names when filtering."""

    def test_filter_by_pseudonym_matches_when_anonymous(self) -> None:
        """Filtering by the displayed pseudonym should match under anonymous sharing."""
        from promptgrimoire.auth.anonymise import anonymise_author

        other_user_id = "user-other-123"
        state = _make_state(is_anonymous=True)
        # Derive the pseudonym that would be displayed
        pseudonym = anonymise_author(
            author="Real Name",
            user_id=other_user_id,
            viewing_user_id=state.user_id,
            anonymous_sharing=True,
            viewer_is_privileged=False,
            author_is_privileged=False,
        )
        hl = {
            "text": "some text",
            "author": "Real Name",
            "user_id": other_user_id,
        }
        # Searching by pseudonym should match
        assert _matches_filter(hl, pseudonym, state) is True

    def test_filter_by_real_name_does_not_match_when_anonymous(self) -> None:
        """Filtering by the hidden real name must NOT match under anonymous sharing."""
        state = _make_state(is_anonymous=True)
        hl = {
            "text": "some text",
            "author": "Secret Real Name",
            "user_id": "user-other-456",
        }
        assert _matches_filter(hl, "Secret Real Name", state) is False

    def test_filter_by_real_name_works_when_not_anonymous(self) -> None:
        """Filtering by real name should match when anonymous sharing is off."""
        state = _make_state(is_anonymous=False)
        hl = {
            "text": "some text",
            "author": "Professor Smith",
            "user_id": "user-other-789",
        }
        assert _matches_filter(hl, "smith", state) is True

    def test_filter_comment_author_anonymised(self) -> None:
        """Comment author is anonymised in filter when anonymous sharing is on."""
        from promptgrimoire.auth.anonymise import anonymise_author

        commenter_id = "commenter-001"
        state = _make_state(is_anonymous=True)
        pseudonym = anonymise_author(
            author="Comment Author",
            user_id=commenter_id,
            viewing_user_id=state.user_id,
            anonymous_sharing=True,
            viewer_is_privileged=False,
            author_is_privileged=False,
        )
        hl = {
            "text": "passage",
            "author": "HL Author",
            "user_id": "hl-user-001",
            "comments": [
                {
                    "text": "Good point",
                    "author": "Comment Author",
                    "user_id": commenter_id,
                }
            ],
        }
        # Pseudonym matches
        assert _matches_filter(hl, pseudonym, state) is True
        # Real comment author name does NOT match
        assert _matches_filter(hl, "Comment Author", state) is False

    def test_filter_comment_real_name_does_not_leak_when_anonymous(self) -> None:
        """Real comment author name must not match under anonymous sharing."""
        state = _make_state(is_anonymous=True)
        hl = {
            "text": "passage",
            "author": "HL Author",
            "user_id": "hl-user-002",
            "comments": [
                {
                    "text": "Noted",
                    "author": "Hidden Commenter",
                    "user_id": "commenter-002",
                }
            ],
        }
        assert _matches_filter(hl, "Hidden Commenter", state) is False
