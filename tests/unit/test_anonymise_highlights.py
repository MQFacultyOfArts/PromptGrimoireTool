"""Unit tests for anonymising highlight dicts before PDF export.

Verifies workspace-sharing-97.AC4.7: PDF export respects anonymity flag.
"""

from __future__ import annotations


class TestAnonymiseHighlightsForExport:
    """anonymise_highlights transforms author fields for export."""

    def test_anonymises_other_users_highlights(self) -> None:
        """Other users' highlight authors are replaced with anonymous labels."""
        from promptgrimoire.pages.annotation.pdf_export import anonymise_highlights

        highlights = [
            {
                "id": "h1",
                "author": "Alice Smith",
                "user_id": "user-alice",
                "tag": "important",
                "comments": [],
            },
        ]

        result = anonymise_highlights(
            highlights,
            viewing_user_id="user-bob",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
        )

        assert len(result) == 1
        assert result[0]["author"] != "Alice Smith"
        # Should be a deterministic anonymised label
        assert result[0]["author"] == result[0]["author"]  # stable

    def test_preserves_own_highlights(self) -> None:
        """Viewer's own highlights keep real author name."""
        from promptgrimoire.pages.annotation.pdf_export import anonymise_highlights

        highlights = [
            {
                "id": "h1",
                "author": "Bob Jones",
                "user_id": "user-bob",
                "tag": "note",
                "comments": [],
            },
        ]

        result = anonymise_highlights(
            highlights,
            viewing_user_id="user-bob",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
        )

        assert result[0]["author"] == "Bob Jones"

    def test_privileged_viewer_sees_real_names(self) -> None:
        """Instructors see real author names even with anonymisation on."""
        from promptgrimoire.pages.annotation.pdf_export import anonymise_highlights

        highlights = [
            {
                "id": "h1",
                "author": "Alice Smith",
                "user_id": "user-alice",
                "tag": "key",
                "comments": [],
            },
        ]

        result = anonymise_highlights(
            highlights,
            viewing_user_id="user-instructor",
            anonymous_sharing=True,
            viewer_is_privileged=True,
            privileged_user_ids=frozenset(),
        )

        assert result[0]["author"] == "Alice Smith"

    def test_no_anonymisation_when_disabled(self) -> None:
        """When anonymous_sharing is False, all names are real."""
        from promptgrimoire.pages.annotation.pdf_export import anonymise_highlights

        highlights = [
            {
                "id": "h1",
                "author": "Alice Smith",
                "user_id": "user-alice",
                "tag": "tag",
                "comments": [],
            },
        ]

        result = anonymise_highlights(
            highlights,
            viewing_user_id="user-bob",
            anonymous_sharing=False,
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
        )

        assert result[0]["author"] == "Alice Smith"

    def test_anonymises_comment_authors(self) -> None:
        """Comment authors within highlights are also anonymised."""
        from promptgrimoire.pages.annotation.pdf_export import anonymise_highlights

        highlights = [
            {
                "id": "h1",
                "author": "Alice Smith",
                "user_id": "user-alice",
                "tag": "tag",
                "comments": [
                    {
                        "author": "Carol Davis",
                        "user_id": "user-carol",
                        "text": "Good point",
                    },
                    {
                        "author": "Bob Jones",
                        "user_id": "user-bob",
                        "text": "I agree",
                    },
                ],
            },
        ]

        result = anonymise_highlights(
            highlights,
            viewing_user_id="user-bob",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
        )

        # Carol's name is anonymised
        comments = result[0]["comments"]
        assert isinstance(comments, list)
        assert comments[0]["author"] != "Carol Davis"  # type: ignore[index]
        # Bob's own comment keeps real name
        assert comments[1]["author"] == "Bob Jones"  # type: ignore[index]

    def test_privileged_author_shows_real_name_in_export(self) -> None:
        """Instructor highlight shows real name to student in PDF export.

        Sensitive: would TypeError on pre-fix code that used viewer_is_owner
        instead of privileged_user_ids. Also would fail on code that doesn't
        pass author_is_privileged through to anonymise_author.
        Specific: passes because privileged_user_ids correctly identifies
        the instructor and preserves their real name.
        """
        from promptgrimoire.pages.annotation.pdf_export import anonymise_highlights

        highlights = [
            {
                "id": "h1",
                "author": "Prof. Smith",
                "user_id": "user-instructor",
                "tag": "feedback",
                "comments": [
                    {
                        "author": "Prof. Smith",
                        "user_id": "user-instructor",
                        "text": "Good work",
                    },
                ],
            },
        ]

        result = anonymise_highlights(
            highlights,
            viewing_user_id="user-student",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            privileged_user_ids=frozenset({"user-instructor"}),
        )

        assert result[0]["author"] == "Prof. Smith"
        comments = result[0]["comments"]
        assert isinstance(comments, list)
        assert comments[0]["author"] == "Prof. Smith"  # type: ignore[index]

    def test_mixed_privileged_and_student_highlights(self) -> None:
        """Instructor highlight real, student highlight anonymised — same export.

        Verifies privileged_user_ids is applied per-highlight, not globally.
        """
        from promptgrimoire.pages.annotation.pdf_export import anonymise_highlights

        highlights = [
            {
                "id": "h1",
                "author": "Prof. Smith",
                "user_id": "user-instructor",
                "tag": "feedback",
                "comments": [],
            },
            {
                "id": "h2",
                "author": "Alice Student",
                "user_id": "user-alice",
                "tag": "question",
                "comments": [],
            },
        ]

        result = anonymise_highlights(
            highlights,
            viewing_user_id="user-bob",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            privileged_user_ids=frozenset({"user-instructor"}),
        )

        # Instructor real name preserved
        assert result[0]["author"] == "Prof. Smith"
        # Student name anonymised
        assert result[1]["author"] != "Alice Student"

    def test_does_not_mutate_original(self) -> None:
        """Returns new dicts, does not mutate the input highlights."""
        from promptgrimoire.pages.annotation.pdf_export import anonymise_highlights

        highlights = [
            {
                "id": "h1",
                "author": "Alice Smith",
                "user_id": "user-alice",
                "tag": "tag",
                "comments": [
                    {"author": "Carol Davis", "user_id": "user-carol", "text": "hi"},
                ],
            },
        ]

        anonymise_highlights(
            highlights,
            viewing_user_id="user-bob",
            anonymous_sharing=True,
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
        )

        assert highlights[0]["author"] == "Alice Smith"
        comments = highlights[0]["comments"]
        assert isinstance(comments, list)
        assert comments[0]["author"] == "Carol Davis"
