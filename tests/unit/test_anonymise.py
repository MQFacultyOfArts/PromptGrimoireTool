"""Tests for the anonymisation utility.

Verifies:
- AC4.3: Instructor/admin always sees real author
- AC4.4: Owner viewing own workspace sees real author
- AC4.5: Peer sees own annotations with real name, others with anonymised label
- AC4.6: Anonymised labels are deterministic adjective-animal names
"""

from __future__ import annotations

from promptgrimoire.auth.anonymise import anonymise_author, anonymise_display_name


class TestAnonymiseAuthor:
    """Tests for anonymise_author()."""

    def test_no_anonymisation_returns_real_author(self) -> None:
        """When anonymous_sharing is False, always return the real author."""
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-123",
            viewing_user_id="user-456",
            anonymous_sharing=False,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        assert result == "Alice Smith"

    def test_privileged_viewer_sees_real_author(self) -> None:
        """AC4.3: Instructor/admin always sees real author regardless of anonymity."""
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-123",
            viewing_user_id="user-789",
            anonymous_sharing=True,
            viewer_is_privileged=True,
            viewer_is_owner=False,
        )
        assert result == "Alice Smith"

    def test_owner_sees_real_author(self) -> None:
        """AC4.4: Owner viewing own workspace sees real author names."""
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-123",
            viewing_user_id="user-789",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=True,
        )
        assert result == "Alice Smith"

    def test_own_annotation_shows_real_name(self) -> None:
        """AC4.5: Peer sees own annotations with real name."""
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-123",
            viewing_user_id="user-123",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        assert result == "Alice Smith"

    def test_other_annotation_shows_anonymised(self) -> None:
        """AC4.5: Peer sees others' annotations with anonymised label."""
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-123",
            viewing_user_id="user-456",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        assert result != "Alice Smith"
        # Should be an adjective-animal label
        parts = result.split(" ")
        assert len(parts) == 2, f"Expected 'Adjective Animal', got '{result}'"

    def test_deterministic_same_user_id(self) -> None:
        """AC4.6: Same user_id always produces the same label."""
        result1 = anonymise_author(
            author="Alice Smith",
            user_id="user-123",
            viewing_user_id="user-456",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        result2 = anonymise_author(
            author="Alice Smith",
            user_id="user-123",
            viewing_user_id="user-456",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        assert result1 == result2

    def test_different_user_ids_produce_different_labels(self) -> None:
        """AC4.6: Different user_ids produce different labels."""
        result1 = anonymise_author(
            author="Alice Smith",
            user_id="user-aaa",
            viewing_user_id="user-456",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        result2 = anonymise_author(
            author="Bob Jones",
            user_id="user-bbb",
            viewing_user_id="user-456",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        assert result1 != result2

    def test_none_user_id_returns_unknown(self) -> None:
        """Legacy data without user_id returns 'Unknown' when anonymised."""
        result = anonymise_author(
            author="Old Author",
            user_id=None,
            viewing_user_id="user-456",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        assert result == "Unknown"

    def test_none_viewing_user_id_still_anonymises(self) -> None:
        """Unauthenticated viewer with anonymous_sharing sees anonymised label."""
        result = anonymise_author(
            author="Alice Smith",
            user_id="user-123",
            viewing_user_id=None,
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        assert result != "Alice Smith"
        parts = result.split(" ")
        assert len(parts) == 2

    def test_both_user_ids_none_not_treated_as_own(self) -> None:
        """When both user_id and viewing_user_id are None, do not treat as 'own'."""
        result = anonymise_author(
            author="Legacy Author",
            user_id=None,
            viewing_user_id=None,
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        # Should be "Unknown" because user_id is None (legacy data)
        assert result == "Unknown"


class TestAnonymiseDisplayName:
    """Tests for anonymise_display_name()."""

    def test_none_returns_unknown(self) -> None:
        """None user_id returns 'Unknown'."""
        assert anonymise_display_name(None) == "Unknown"

    def test_returns_adjective_animal(self) -> None:
        """Returns a two-word adjective-animal label."""
        result = anonymise_display_name("user-123")
        parts = result.split(" ")
        assert len(parts) == 2

    def test_deterministic(self) -> None:
        """Same user_id always produces the same label."""
        assert anonymise_display_name("user-xyz") == anonymise_display_name("user-xyz")

    def test_different_ids_different_labels(self) -> None:
        """Different user_ids produce different labels."""
        assert anonymise_display_name("user-aaa") != anonymise_display_name("user-bbb")

    def test_matches_anonymise_author_label(self) -> None:
        """anonymise_display_name matches anonymise_author for same user_id."""
        user_id = "user-consistency-check"
        display_label = anonymise_display_name(user_id)
        author_label = anonymise_author(
            author="Real Name",
            user_id=user_id,
            viewing_user_id="viewer-other",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        assert display_label == author_label
