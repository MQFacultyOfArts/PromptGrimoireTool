"""Unit tests for region builder.

Tests the state machine that converts tokens to regions.
Uses tokens directly - does NOT call lexer.
"""

from dataclasses import FrozenInstanceError

import pytest

from promptgrimoire.export.latex import (
    MarkerToken,
    MarkerTokenType,
    Region,
    build_regions,
)


class TestRegionDataclass:
    """Tests for the Region dataclass itself."""

    def test_region_has_expected_fields(self) -> None:
        """Region has text, active, and annots fields."""
        region = Region(
            text="hello",
            active=frozenset({1, 2}),
            annots=[1],
        )
        assert region.text == "hello"
        assert region.active == frozenset({1, 2})
        assert region.annots == [1]

    def test_region_is_frozen(self) -> None:
        """Region is immutable."""
        region = Region(text="x", active=frozenset(), annots=[])
        with pytest.raises(FrozenInstanceError):
            region.text = "changed"  # type: ignore[invalid-assignment]

    def test_active_is_frozenset(self) -> None:
        """Active highlights must be frozenset."""
        region = Region(text="x", active=frozenset({1}), annots=[])
        assert isinstance(region.active, frozenset)

    def test_empty_region_valid(self) -> None:
        """Empty text with no active highlights is valid."""
        region = Region(text="", active=frozenset(), annots=[])
        assert region.text == ""
        assert len(region.active) == 0


class TestBuildRegions:
    """Tests for build_regions function."""

    def test_empty_tokens(self) -> None:
        """Empty token list returns empty region list."""
        assert build_regions([]) == []

    def test_text_only_single_region(self) -> None:
        """Single TEXT token produces single region with empty active set."""
        tokens = [
            MarkerToken(MarkerTokenType.TEXT, "hello world", None, 0, 11),
        ]
        regions = build_regions(tokens)
        assert len(regions) == 1
        assert regions[0].text == "hello world"
        assert regions[0].active == frozenset()
        assert regions[0].annots == []

    def test_single_highlight_three_regions(self) -> None:
        """HLSTART...text...HLEND produces before/during/after regions."""
        tokens = [
            MarkerToken(MarkerTokenType.TEXT, "before ", None, 0, 7),
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 7, 22),
            MarkerToken(MarkerTokenType.TEXT, "during", None, 22, 28),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 28, 41),
            MarkerToken(MarkerTokenType.TEXT, " after", None, 41, 47),
        ]
        regions = build_regions(tokens)

        assert len(regions) == 3
        assert regions[0] == Region("before ", frozenset(), [])
        assert regions[1] == Region("during", frozenset({1}), [])
        assert regions[2] == Region(" after", frozenset(), [])

    def test_non_overlapping_highlights(self) -> None:
        """Two non-overlapping highlights produce separate regions."""
        tokens = [
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 0, 15),
            MarkerToken(MarkerTokenType.TEXT, "first", None, 15, 20),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 20, 33),
            MarkerToken(MarkerTokenType.TEXT, " gap ", None, 33, 38),
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{2}ENDHL", 2, 38, 53),
            MarkerToken(MarkerTokenType.TEXT, "second", None, 53, 59),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{2}ENDHL", 2, 59, 72),
        ]
        regions = build_regions(tokens)

        assert len(regions) == 3
        assert regions[0] == Region("first", frozenset({1}), [])
        assert regions[1] == Region(" gap ", frozenset(), [])
        assert regions[2] == Region("second", frozenset({2}), [])

    def test_nested_highlights_example_a(self) -> None:
        """Example A from design: properly nested highlights."""
        tokens = [
            MarkerToken(MarkerTokenType.TEXT, "The ", None, 0, 4),
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 4, 19),
            MarkerToken(MarkerTokenType.TEXT, "quick ", None, 19, 25),
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{2}ENDHL", 2, 25, 40),
            MarkerToken(MarkerTokenType.TEXT, "fox", None, 40, 43),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{2}ENDHL", 2, 43, 56),
            MarkerToken(MarkerTokenType.TEXT, " brown", None, 56, 62),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 62, 75),
            MarkerToken(MarkerTokenType.TEXT, " dog", None, 75, 79),
        ]
        regions = build_regions(tokens)

        assert len(regions) == 5
        assert regions[0] == Region("The ", frozenset(), [])
        assert regions[1] == Region("quick ", frozenset({1}), [])
        assert regions[2] == Region("fox", frozenset({1, 2}), [])
        assert regions[3] == Region(" brown", frozenset({1}), [])
        assert regions[4] == Region(" dog", frozenset(), [])

    def test_interleaved_highlights_example_b(self) -> None:
        """Example B from design: interleaved (not properly nested)."""
        tokens = [
            MarkerToken(MarkerTokenType.TEXT, "The ", None, 0, 4),
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 4, 19),
            MarkerToken(MarkerTokenType.TEXT, "quick ", None, 19, 25),
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{2}ENDHL", 2, 25, 40),
            MarkerToken(MarkerTokenType.TEXT, "fox", None, 40, 43),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 43, 56),
            MarkerToken(MarkerTokenType.TEXT, " over", None, 56, 61),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{2}ENDHL", 2, 61, 74),
            MarkerToken(MarkerTokenType.TEXT, " dog", None, 74, 78),
        ]
        regions = build_regions(tokens)

        assert len(regions) == 5
        assert regions[0] == Region("The ", frozenset(), [])
        assert regions[1] == Region("quick ", frozenset({1}), [])
        assert regions[2] == Region("fox", frozenset({1, 2}), [])
        assert regions[3] == Region(" over", frozenset({2}), [])  # Key: only {2} active
        assert regions[4] == Region(" dog", frozenset(), [])

    def test_three_overlapping_example_c(self) -> None:
        """Example C from design: three overlapping highlights."""
        tokens = [
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 0, 15),
            MarkerToken(MarkerTokenType.TEXT, "a ", None, 15, 17),
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{2}ENDHL", 2, 17, 32),
            MarkerToken(MarkerTokenType.TEXT, "b ", None, 32, 34),
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{3}ENDHL", 3, 34, 49),
            MarkerToken(MarkerTokenType.TEXT, "c", None, 49, 50),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 50, 63),
            MarkerToken(MarkerTokenType.TEXT, " d", None, 63, 65),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{2}ENDHL", 2, 65, 78),
            MarkerToken(MarkerTokenType.TEXT, " e", None, 78, 80),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{3}ENDHL", 3, 80, 93),
        ]
        regions = build_regions(tokens)

        assert len(regions) == 5
        assert regions[0] == Region("a ", frozenset({1}), [])
        assert regions[1] == Region("b ", frozenset({1, 2}), [])
        assert regions[2] == Region("c", frozenset({1, 2, 3}), [])
        assert regions[3] == Region(" d", frozenset({2, 3}), [])
        assert regions[4] == Region(" e", frozenset({3}), [])

    def test_annmarker_associated_by_index(self) -> None:
        """ANNMARKER stores its index in the region where it appears."""
        tokens = [
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 0, 15),
            MarkerToken(MarkerTokenType.TEXT, "text", None, 15, 19),
            MarkerToken(MarkerTokenType.ANNMARKER, "ANNMARKER{1}ENDMARKER", 1, 19, 40),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 40, 53),
        ]
        regions = build_regions(tokens)

        # The annmarker appears after "text", so it's part of that region
        assert len(regions) == 1
        assert regions[0].text == "text"
        assert regions[0].active == frozenset({1})
        assert regions[0].annots == [1]

    def test_annmarker_not_position_dependent(self) -> None:
        """ANNMARKER{2} in a region where only {1} is active still records index 2."""
        tokens = [
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 0, 15),
            MarkerToken(MarkerTokenType.TEXT, "text", None, 15, 19),
            MarkerToken(MarkerTokenType.ANNMARKER, "ANNMARKER{2}ENDMARKER", 2, 19, 40),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 40, 53),
        ]
        regions = build_regions(tokens)

        # ANNMARKER{2} records index 2, even though only highlight 1 is active
        assert regions[0].annots == [2]

    def test_multiple_annmarkers_in_region(self) -> None:
        """Multiple ANNMARKER tokens in same region accumulate."""
        tokens = [
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 0, 15),
            MarkerToken(MarkerTokenType.TEXT, "text", None, 15, 19),
            MarkerToken(MarkerTokenType.ANNMARKER, "ANNMARKER{1}ENDMARKER", 1, 19, 40),
            MarkerToken(MarkerTokenType.ANNMARKER, "ANNMARKER{2}ENDMARKER", 2, 40, 61),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 61, 74),
        ]
        regions = build_regions(tokens)

        assert regions[0].annots == [1, 2]

    def test_active_set_is_frozenset(self) -> None:
        """Region.active is frozenset for immutability."""
        tokens = [
            MarkerToken(MarkerTokenType.HLSTART, "HLSTART{1}ENDHL", 1, 0, 15),
            MarkerToken(MarkerTokenType.TEXT, "x", None, 15, 16),
            MarkerToken(MarkerTokenType.HLEND, "HLEND{1}ENDHL", 1, 16, 29),
        ]
        regions = build_regions(tokens)
        assert isinstance(regions[0].active, frozenset)

    def test_spaces_included_in_regions(self) -> None:
        """Whitespace is preserved in region text."""
        tokens = [
            MarkerToken(MarkerTokenType.TEXT, "  spaces  ", None, 0, 10),
        ]
        regions = build_regions(tokens)
        assert regions[0].text == "  spaces  "
