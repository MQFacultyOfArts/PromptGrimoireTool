"""Characterisation tests for pure card data functions.

Tests lock down existing behaviour of pure functions used in card rendering
across Annotate, Organise, and Respond tabs. No NiceGUI or database required.

Traceability:
- Plan: phase_01.md Task 1 (multi-doc-tabs-186-plan-a)
- Protects: multi-doc-tabs-186.AC11 (Card Consistency)
"""

from __future__ import annotations

from typing import Any

from promptgrimoire.auth.anonymise import anonymise_author
from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.pages.annotation.cards import _author_initials
from promptgrimoire.pages.annotation.respond import group_highlights_by_tag

# ---------------------------------------------------------------------------
# _author_initials
# ---------------------------------------------------------------------------


class TestAuthorInitials:
    """Tests for _author_initials() in cards.py."""

    def test_two_word_name(self) -> None:
        assert _author_initials("Alice Smith") == "A.S."

    def test_single_name(self) -> None:
        assert _author_initials("Ada") == "A."

    def test_hyphenated_name(self) -> None:
        assert _author_initials("Brian Ballsun-Stanton") == "B.B.S."

    def test_empty_string(self) -> None:
        # Empty string has no segments -> empty initials with trailing dot
        assert _author_initials("") == "."

    def test_whitespace_only(self) -> None:
        assert _author_initials("   ") == "."

    def test_three_word_name(self) -> None:
        assert _author_initials("Mary Jane Watson") == "M.J.W."


# ---------------------------------------------------------------------------
# anonymise_author
# ---------------------------------------------------------------------------


class TestAnonymiseAuthor:
    """Tests for anonymise_author() in auth/anonymise.py."""

    def test_no_anonymisation_returns_real_name(self) -> None:
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-1",
            viewing_user_id="user-2",
            anonymous_sharing=False,
            viewer_is_privileged=False,
        )
        assert result == "Alice Smith"

    def test_privileged_viewer_sees_real_name(self) -> None:
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-1",
            viewing_user_id="user-2",
            anonymous_sharing=True,
            viewer_is_privileged=True,
        )
        assert result == "Alice Smith"

    def test_privileged_author_shows_real_name(self) -> None:
        result = anonymise_author(
            author="Prof. Jones",
            user_id="user-instructor",
            viewing_user_id="user-student",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            author_is_privileged=True,
        )
        assert result == "Prof. Jones"

    def test_own_annotation_shows_real_name(self) -> None:
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-1",
            viewing_user_id="user-1",
            anonymous_sharing=True,
            viewer_is_privileged=False,
        )
        assert result == "Alice Smith"

    def test_other_user_anonymised(self) -> None:
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-1",
            viewing_user_id="user-2",
            anonymous_sharing=True,
            viewer_is_privileged=False,
        )
        assert result != "Alice Smith"
        # Should be a deterministic adjective-animal label
        assert " " in result  # Two words

    def test_legacy_data_no_user_id(self) -> None:
        result = anonymise_author(
            author="Old Author",
            user_id=None,
            viewing_user_id="user-2",
            anonymous_sharing=True,
            viewer_is_privileged=False,
        )
        assert result == "Unknown"

    def test_deterministic_label(self) -> None:
        """Same user_id always produces the same anonymised label."""
        r1 = anonymise_author(
            author="Alice",
            user_id="user-fixed",
            viewing_user_id="user-other",
            anonymous_sharing=True,
            viewer_is_privileged=False,
        )
        r2 = anonymise_author(
            author="Alice",
            user_id="user-fixed",
            viewing_user_id="user-other",
            anonymous_sharing=True,
            viewer_is_privileged=False,
        )
        assert r1 == r2


# ---------------------------------------------------------------------------
# group_highlights_by_tag
# ---------------------------------------------------------------------------


class _FakeTagInfo:
    """Minimal TagInfo stand-in for testing group_highlights_by_tag."""

    def __init__(self, raw_key: str, name: str) -> None:
        self.raw_key = raw_key
        self.name = name


class TestGroupHighlightsByTag:
    """Tests for group_highlights_by_tag() in respond.py."""

    def _make_doc_with_highlights(
        self, highlights: list[dict[str, Any]]
    ) -> AnnotationDocument:
        doc = AnnotationDocument("test-doc")
        for hl in highlights:
            doc.add_highlight(
                start_char=hl.get("start_char", 0),
                end_char=hl.get("end_char", 10),
                tag=hl.get("tag", ""),
                text=hl.get("text", "test text"),
                author=hl.get("author", "Author"),
            )
        return doc

    def test_empty_input(self) -> None:
        doc = AnnotationDocument("test-doc")
        tags: list[Any] = [_FakeTagInfo("tag_a", "Tag A")]
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)
        assert tagged == {"Tag A": []}
        assert untagged == []
        assert has_any is False

    def test_multiple_tags(self) -> None:
        doc = self._make_doc_with_highlights(
            [
                {"tag": "jurisdiction", "text": "hl1"},
                {"tag": "legal_issues", "text": "hl2"},
            ]
        )
        tags: list[Any] = [
            _FakeTagInfo("jurisdiction", "Jurisdiction"),
            _FakeTagInfo("legal_issues", "Legal Issues"),
        ]
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)
        assert len(tagged["Jurisdiction"]) == 1
        assert len(tagged["Legal Issues"]) == 1
        assert untagged == []
        assert has_any is True

    def test_highlight_with_no_matching_tag(self) -> None:
        doc = self._make_doc_with_highlights(
            [
                {"tag": "unknown_tag", "text": "orphan"},
            ]
        )
        tags: list[Any] = [_FakeTagInfo("jurisdiction", "Jurisdiction")]
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)
        assert tagged["Jurisdiction"] == []
        assert len(untagged) == 1
        assert has_any is True

    def test_highlight_with_empty_tag(self) -> None:
        doc = self._make_doc_with_highlights(
            [
                {"tag": "", "text": "no tag"},
            ]
        )
        tags: list[Any] = [_FakeTagInfo("jurisdiction", "Jurisdiction")]
        _tagged, untagged, _has_any = group_highlights_by_tag(tags, doc)
        assert len(untagged) == 1

    def test_no_tags_defined(self) -> None:
        doc = self._make_doc_with_highlights(
            [
                {"tag": "something", "text": "hl"},
            ]
        )
        tags: list[Any] = []
        tagged, untagged, has_any = group_highlights_by_tag(tags, doc)
        assert tagged == {}
        assert len(untagged) == 1
        assert has_any is True
