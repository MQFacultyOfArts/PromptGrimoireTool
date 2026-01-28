"""Unit tests for region builder.

Tests the state machine that converts tokens to regions.
Uses tokens directly - does NOT call lexer.
"""

from dataclasses import FrozenInstanceError

import pytest

from promptgrimoire.export.latex import Region


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
