"""Unit tests for TagInfo abstraction and BriefTag mapper.

Verifies that brief_tags_to_tag_info() correctly converts BriefTag enum members
into a list of TagInfo instances with proper display names and colours.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_03.md Task 1
- AC: three-tab-ui.AC2.1 (data structure)
"""

from __future__ import annotations

import re

from promptgrimoire.models.case import TAG_COLORS, BriefTag
from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info


class TestBriefTagsToTagInfo:
    """Verify brief_tags_to_tag_info() mapper produces correct TagInfo list."""

    def test_brief_tags_to_tag_info_returns_all_tags(self) -> None:
        """Result has 10 entries, one per BriefTag member."""
        result = brief_tags_to_tag_info()
        assert len(result) == 10
        assert len(result) == len(BriefTag)

    def test_tag_info_names_are_title_case(self) -> None:
        """Each name matches tag.value.replace('_', ' ').title()."""
        result = brief_tags_to_tag_info()
        for tag_info, brief_tag in zip(result, BriefTag, strict=True):
            expected_name = brief_tag.value.replace("_", " ").title()
            assert tag_info.name == expected_name, (
                f"Expected {expected_name!r}, got {tag_info.name!r} for {brief_tag}"
            )

    def test_tag_info_colours_are_hex(self) -> None:
        """Each colour starts with '#' and has 7 characters (e.g. '#1f77b4')."""
        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        result = brief_tags_to_tag_info()
        for tag_info in result:
            assert hex_pattern.match(tag_info.colour), (
                f"Invalid hex colour: {tag_info.colour!r} for tag {tag_info.name!r}"
            )

    def test_tag_info_colours_match_tag_colors(self) -> None:
        """Each colour matches TAG_COLORS[tag] for the corresponding BriefTag."""
        result = brief_tags_to_tag_info()
        for tag_info, brief_tag in zip(result, BriefTag, strict=True):
            expected_colour = TAG_COLORS[brief_tag]
            assert tag_info.colour == expected_colour, (
                f"Expected {expected_colour!r}, got {tag_info.colour!r} for {brief_tag}"
            )

    def test_tag_info_is_dataclass_with_expected_fields(self) -> None:
        """TagInfo instances have name and colour string fields."""
        result = brief_tags_to_tag_info()
        tag_info = result[0]
        assert isinstance(tag_info.name, str)
        assert isinstance(tag_info.colour, str)
        assert tag_info.name != ""
        assert tag_info.colour != ""

    def test_order_matches_enum_order(self) -> None:
        """Tag info list preserves BriefTag enum declaration order."""
        result = brief_tags_to_tag_info()
        expected_order = [t.value.replace("_", " ").title() for t in BriefTag]
        actual_order = [t.name for t in result]
        assert actual_order == expected_order
