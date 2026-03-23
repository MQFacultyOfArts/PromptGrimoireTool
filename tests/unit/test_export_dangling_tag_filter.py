"""Tests for export dangling-tag filter and bail logic.

Tests the EXACT filter logic from pdf_export.py against various highlight/tag
combinations. Each test replicates the production code and asserts the correct
bail/proceed behaviour.

Semantics (as of fix):
- Any dangling tag reference → bail with error (error state, #410)
- Zero highlights + valid document → proceed (plain export)
- Zero highlights + no document → bail (handled by downstream guard)

Traceability:
- Branch: fix/export-dangling-tag-colour
- Issue: #410 (dangling tag references)
"""

from __future__ import annotations

from promptgrimoire.pages.annotation.tags import TagInfo

# ---------------------------------------------------------------------------
# Exact replica of the production filter from pdf_export.py.
# This MUST match the actual code character-for-character.
# ---------------------------------------------------------------------------


def _production_filter(
    highlights: list[dict],
    tag_info_list: list[TagInfo] | None,
) -> tuple[list[dict], int]:
    """Exact replica of pdf_export.py dangling-tag filter.

    Source:
        tag_name_map = {ti.raw_key: ti.name for ti in (state.tag_info_list or [])}
        valid = [hl for hl in highlights if hl.get("tag", "") in tag_name_map]
        dangling_count = len(highlights) - len(valid)

    Returns:
        (valid_highlights, dangling_count)
    """
    tag_name_map = {ti.raw_key: ti.name for ti in (tag_info_list or [])}
    valid = [hl for hl in highlights if hl.get("tag", "") in tag_name_map]
    dangling_count = len(highlights) - len(valid)
    return valid, dangling_count


def _production_bail_check(dangling_count: int) -> bool:
    """Exact replica of pdf_export.py bail condition.

    Source:
        if dangling_count > 0:
            # bail with error notification
    """
    return dangling_count > 0


# ---------------------------------------------------------------------------
# Zero-highlight scenarios (valid exports, must NOT bail)
# ---------------------------------------------------------------------------


class TestZeroHighlightsNoBail:
    """Zero highlights is a valid export — produces plain document."""

    def test_zero_highlights_with_tags(self) -> None:
        """Zero highlights + populated tag_info_list → no bail."""
        tag_info = [
            TagInfo(
                name="Jurisdiction",
                colour="#1f77b4",
                raw_key="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            ),
        ]
        highlights: list[dict] = []

        _valid, dangling_count = _production_filter(highlights, tag_info)
        bails = _production_bail_check(dangling_count)

        assert not bails, (
            "Zero-highlight export must NOT bail — "
            "workspace with no annotations is a valid export"
        )

    def test_zero_highlights_zero_tags(self) -> None:
        """Zero highlights + zero tags → no bail.

        Simulates test_cjk_export: workspace with seed_tags=False.
        """
        highlights: list[dict] = []

        _valid, dangling_count = _production_filter(highlights, tag_info_list=[])
        bails = _production_bail_check(dangling_count)

        assert not bails, (
            "Zero highlights + zero tags must not bail — "
            "this is the test_cjk_export scenario"
        )


# ---------------------------------------------------------------------------
# Dangling tag scenarios (error state, MUST bail)
# ---------------------------------------------------------------------------


class TestDanglingTagsBail:
    """Any dangling tag reference is an error state — must bail."""

    def test_all_highlights_dangling(self) -> None:
        """All highlights reference deleted tags → bail."""
        known_tag = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        deleted_tag = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        tag_info = [TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key=known_tag)]
        highlights = [
            {
                "tag": deleted_tag,
                "start_char": 0,
                "end_char": 10,
                "text": "x",
                "author": "a",
            },
        ]

        valid, dangling_count = _production_filter(highlights, tag_info)
        bails = _production_bail_check(dangling_count)

        assert len(valid) == 0
        assert dangling_count == 1
        assert bails, "Must bail when any highlights have dangling tags"

    def test_mixed_valid_and_dangling_still_bails(self) -> None:
        """Even one dangling highlight → bail. Cannot partially export."""
        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        dangling_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        tag_info = [TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key=valid_id)]
        highlights = [
            {
                "tag": valid_id,
                "start_char": 0,
                "end_char": 5,
                "text": "good",
                "author": "a",
            },
            {
                "tag": dangling_id,
                "start_char": 10,
                "end_char": 15,
                "text": "bad",
                "author": "a",
            },
        ]

        valid, dangling_count = _production_filter(highlights, tag_info)
        bails = _production_bail_check(dangling_count)

        assert len(valid) == 1
        assert dangling_count == 1
        assert bails, "Must bail when ANY highlights have dangling tags"

    def test_tag_info_none_treats_all_as_dangling(self) -> None:
        """tag_info_list=None → all highlights treated as dangling → bail.

        Phase 3b confirmed tag_info_list is never None at export time
        (workspace_tags_from_crdt always returns list[TagInfo]). The
        ``or []`` guard is defensive. This test documents that if it
        were somehow None, all highlights are treated as dangling.
        """
        highlights = [
            {
                "tag": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "start_char": 0,
                "end_char": 10,
                "text": "test",
                "author": "tester",
            },
        ]

        valid, dangling_count = _production_filter(highlights, tag_info_list=None)
        bails = _production_bail_check(dangling_count)

        assert len(valid) == 0
        assert dangling_count == 1
        assert bails

    def test_dangling_count_accurate(self) -> None:
        """Dangling count matches the number of filtered-out highlights."""
        valid_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        dangling_1 = "11111111-1111-1111-1111-111111111111"
        dangling_2 = "22222222-2222-2222-2222-222222222222"
        tag_info = [TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key=valid_id)]
        highlights = [
            {
                "tag": valid_id,
                "start_char": 0,
                "end_char": 5,
                "text": "ok",
                "author": "a",
            },
            {
                "tag": dangling_1,
                "start_char": 10,
                "end_char": 15,
                "text": "bad1",
                "author": "a",
            },
            {
                "tag": dangling_2,
                "start_char": 20,
                "end_char": 25,
                "text": "bad2",
                "author": "a",
            },
        ]

        valid, dangling_count = _production_filter(highlights, tag_info)

        assert len(valid) == 1
        assert dangling_count == 2


# ---------------------------------------------------------------------------
# Filter characterisation (tag key format matching)
# ---------------------------------------------------------------------------


class TestTagKeyFormatMatching:
    """Verify the filter matches highlight tag fields against TagInfo.raw_key."""

    def test_exact_uuid_match_kept(self) -> None:
        """Hyphenated UUID on both sides → highlight kept."""
        tag_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        tag_info = [TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key=tag_id)]
        highlights = [
            {
                "tag": tag_id,
                "start_char": 0,
                "end_char": 10,
                "text": "x",
                "author": "a",
            },
        ]

        valid, dangling_count = _production_filter(highlights, tag_info)
        assert len(valid) == 1
        assert dangling_count == 0

    def test_bare_uuid_is_dangling(self) -> None:
        """Bare hex UUID vs hyphenated raw_key → treated as dangling."""
        tag_id_hyphenated = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        tag_id_bare = tag_id_hyphenated.replace("-", "")
        tag_info = [
            TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key=tag_id_hyphenated)
        ]
        highlights = [
            {
                "tag": tag_id_bare,
                "start_char": 0,
                "end_char": 10,
                "text": "x",
                "author": "a",
            },
        ]

        valid, dangling_count = _production_filter(highlights, tag_info)
        assert len(valid) == 0
        assert dangling_count == 1

    def test_display_name_is_dangling(self) -> None:
        """Display name tag vs UUID raw_key → treated as dangling."""
        tag_info = [
            TagInfo(
                name="Jurisdiction",
                colour="#1f77b4",
                raw_key="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            ),
        ]
        highlights = [
            {
                "tag": "Jurisdiction",
                "start_char": 0,
                "end_char": 10,
                "text": "x",
                "author": "a",
            },
        ]

        valid, dangling_count = _production_filter(highlights, tag_info)
        assert len(valid) == 0
        assert dangling_count == 1
