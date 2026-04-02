"""Unit tests for serialise_items() — pure serialisation of CRDT highlights."""

from __future__ import annotations

import pytest

from promptgrimoire.pages.annotation.items_serialise import serialise_items
from promptgrimoire.pages.annotation.tags import TagInfo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tag_info_map() -> dict[str, TagInfo]:
    return {
        "tag-1": TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="tag-1"),
        "tag-2": TagInfo(name="Legal Issues", colour="#ff7f0e", raw_key="tag-2"),
    }


@pytest.fixture
def tag_colours() -> dict[str, str]:
    return {
        "tag-1": "#1f77b4",
        "tag-2": "#ff7f0e",
    }


def _make_highlight(
    *,
    hl_id: str = "hl-1",
    tag: str = "tag-1",
    text: str = "some highlighted text",
    author: str = "Alice Smith",
    user_id: str = "user-alice",
    start_char: int = 10,
    end_char: int = 50,
    para_ref: str | None = "[3]",
    comments: list[dict] | None = None,
) -> dict:
    hl: dict = {
        "id": hl_id,
        "document_id": "doc-1",
        "start_char": start_char,
        "end_char": end_char,
        "tag": tag,
        "text": text,
        "author": author,
        "user_id": user_id,
        "created_at": "2026-03-01T10:00:00",
        "comments": comments or [],
    }
    if para_ref is not None:
        hl["para_ref"] = para_ref
    return hl


def _make_comment(
    *,
    comment_id: str = "c-1",
    author: str = "Bob Jones",
    user_id: str = "user-bob",
    text: str = "Great point",
    created_at: str = "2026-03-01T11:00:00",
) -> dict:
    return {
        "id": comment_id,
        "author": author,
        "user_id": user_id,
        "text": text,
        "created_at": created_at,
    }


_COMMON_KWARGS: dict = {
    "user_id": "user-alice",
    "viewer_is_privileged": False,
    "privileged_user_ids": frozenset(),
    "can_annotate": True,
    "anonymous_sharing": False,
}


# ---------------------------------------------------------------------------
# 1. Basic serialisation
# ---------------------------------------------------------------------------


class TestBasicSerialisation:
    def test_two_highlights_produce_correct_fields(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        highlights = [
            _make_highlight(
                hl_id="hl-1", tag="tag-1", text="first text", start_char=0, end_char=10
            ),
            _make_highlight(
                hl_id="hl-2",
                tag="tag-2",
                text="second text",
                start_char=20,
                end_char=40,
            ),
        ]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            **_COMMON_KWARGS,
        )

        assert len(result) == 2

        item0 = result[0]
        assert item0["id"] == "hl-1"
        assert item0["tag_key"] == "tag-1"
        assert item0["tag_display"] == "Jurisdiction"
        assert item0["color"] == "#1f77b4"
        assert item0["start_char"] == 0
        assert item0["end_char"] == 10
        assert item0["para_ref"] == "[3]"
        assert item0["text"] == "first text"
        assert item0["text_preview"] == "first text"

        item1 = result[1]
        assert item1["id"] == "hl-2"
        assert item1["tag_key"] == "tag-2"
        assert item1["tag_display"] == "Legal Issues"
        assert item1["color"] == "#ff7f0e"


# ---------------------------------------------------------------------------
# 2. Comment serialisation
# ---------------------------------------------------------------------------


class TestCommentSerialisation:
    def test_comments_sorted_by_created_at(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        # Comments deliberately out of order
        comments = [
            _make_comment(
                comment_id="c-2", created_at="2026-03-01T12:00:00", text="Later"
            ),
            _make_comment(
                comment_id="c-1", created_at="2026-03-01T11:00:00", text="Earlier"
            ),
        ]
        highlights = [_make_highlight(comments=comments)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            **_COMMON_KWARGS,
        )

        serialised_comments = result[0]["comments"]
        assert len(serialised_comments) == 2
        assert serialised_comments[0]["id"] == "c-1"
        assert serialised_comments[0]["text"] == "Earlier"
        assert serialised_comments[0]["created_at"] == "2026-03-01T11:00:00"
        assert serialised_comments[1]["id"] == "c-2"
        assert serialised_comments[1]["text"] == "Later"

    def test_comment_has_display_author(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        comments = [_make_comment(author="Bob Jones", user_id="user-bob")]
        highlights = [_make_highlight(comments=comments)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            **_COMMON_KWARGS,
        )

        c = result[0]["comments"][0]
        assert c["display_author"] == "Bob Jones"
        assert c["author"] == "Bob Jones"


# ---------------------------------------------------------------------------
# 3. Author anonymisation
# ---------------------------------------------------------------------------


class TestAuthorAnonymisation:
    def test_other_users_highlight_anonymised(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        highlights = [
            _make_highlight(author="Bob Jones", user_id="user-bob"),
        ]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            user_id="user-alice",
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=True,
        )

        item = result[0]
        # Should NOT be the raw author name
        assert item["display_author"] != "Bob Jones"
        # Raw author field preserved
        assert item["author"] == "Bob Jones"
        # Should be a deterministic pseudonym, not empty
        assert len(item["display_author"]) > 0

    def test_own_highlight_not_anonymised(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        highlights = [
            _make_highlight(author="Alice Smith", user_id="user-alice"),
        ]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            user_id="user-alice",
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=True,
        )

        assert result[0]["display_author"] == "Alice Smith"


# ---------------------------------------------------------------------------
# 4. Permission can_delete (highlight)
# ---------------------------------------------------------------------------


class TestCanDeleteHighlight:
    def test_own_highlight_can_delete(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        highlights = [_make_highlight(user_id="user-alice")]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            user_id="user-alice",
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=False,
        )

        assert result[0]["can_delete"] is True

    def test_other_highlight_non_privileged_cannot_delete(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        highlights = [_make_highlight(user_id="user-bob")]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            user_id="user-alice",
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=False,
        )

        assert result[0]["can_delete"] is False

    def test_privileged_user_can_delete_any_highlight(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        highlights = [_make_highlight(user_id="user-bob")]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            user_id="user-alice",
            viewer_is_privileged=True,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=False,
        )

        assert result[0]["can_delete"] is True


# ---------------------------------------------------------------------------
# 5. Permission can_delete (comment)
# ---------------------------------------------------------------------------


class TestCanDeleteComment:
    def test_own_comment_can_delete(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        comments = [_make_comment(user_id="user-alice")]
        highlights = [_make_highlight(comments=comments)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            user_id="user-alice",
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=False,
        )

        assert result[0]["comments"][0]["can_delete"] is True

    def test_other_comment_non_privileged_cannot_delete(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        comments = [_make_comment(user_id="user-bob")]
        highlights = [_make_highlight(comments=comments)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            user_id="user-alice",
            viewer_is_privileged=False,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=False,
        )

        assert result[0]["comments"][0]["can_delete"] is False

    def test_privileged_user_can_delete_any_comment(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        comments = [_make_comment(user_id="user-bob")]
        highlights = [_make_highlight(comments=comments)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            user_id="user-alice",
            viewer_is_privileged=True,
            privileged_user_ids=frozenset(),
            can_annotate=True,
            anonymous_sharing=False,
        )

        assert result[0]["comments"][0]["can_delete"] is True


# ---------------------------------------------------------------------------
# 6. Deleted tag
# ---------------------------------------------------------------------------


class TestDeletedTag:
    def test_missing_tag_shows_recovered_label(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        highlights = [_make_highlight(tag="tag-deleted")]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            **_COMMON_KWARGS,
        )

        assert result[0]["tag_display"] == "\u26a0 recovered"
        assert result[0]["color"] == "#999999"


# ---------------------------------------------------------------------------
# 7. Empty para_ref
# ---------------------------------------------------------------------------


class TestEmptyParaRef:
    def test_missing_para_ref_returns_empty_string(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        highlights = [_make_highlight(para_ref=None)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            **_COMMON_KWARGS,
        )

        assert result[0]["para_ref"] == ""


# ---------------------------------------------------------------------------
# 8. Text preview
# ---------------------------------------------------------------------------


class TestTextPreview:
    def test_short_text_unchanged(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        short = "Hello world"
        highlights = [_make_highlight(text=short)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            **_COMMON_KWARGS,
        )

        assert result[0]["text_preview"] == short
        assert result[0]["text"] == short

    def test_exactly_80_chars_unchanged(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        text_80 = "x" * 80
        highlights = [_make_highlight(text=text_80)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            **_COMMON_KWARGS,
        )

        assert result[0]["text_preview"] == text_80

    def test_long_text_truncated_with_ellipsis(
        self, tag_info_map: dict[str, TagInfo], tag_colours: dict[str, str]
    ) -> None:
        text_100 = "a" * 100
        highlights = [_make_highlight(text=text_100)]

        result = serialise_items(
            highlights,
            tag_info_map,
            tag_colours,
            **_COMMON_KWARGS,
        )

        assert result[0]["text_preview"] == "a" * 80 + "..."
        assert result[0]["text"] == text_100
