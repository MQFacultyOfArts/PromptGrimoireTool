"""Unit tests for word count badge formatting.

Pure function tests — no async, no DB, no UI.
Verifies AC4.2, AC4.3, AC4.4, AC4.5, AC4.6, AC4.8.
"""

from __future__ import annotations

import pytest

from promptgrimoire.pages.annotation.word_count_badge import (
    BadgeState,
    format_word_count_badge,
)

# CSS class constants for assertions
_NEUTRAL = "text-sm text-gray-600 bg-gray-100 px-2 py-0.5 rounded"
_AMBER = "text-sm text-amber-800 bg-amber-100 px-2 py-0.5 rounded"
_RED = "text-sm text-red-800 bg-red-100 px-2 py-0.5 rounded"


class TestBadgeStateDataclass:
    """BadgeState is a frozen dataclass with text and css_classes."""

    def test_frozen(self) -> None:
        state = BadgeState(text="Words: 0", css_classes=_NEUTRAL)
        with pytest.raises(AttributeError):
            state.text = "changed"  # type: ignore[invalid-assignment]  # intentional: testing runtime immutability


class TestFormatWordCountBadge:
    """Tests for format_word_count_badge covering AC4 cases."""

    @pytest.mark.parametrize(
        ("count", "minimum", "limit", "expected_text", "expected_classes"),
        [
            pytest.param(
                1234,
                None,
                1500,
                "Words: 1,234 / 1,500",
                _NEUTRAL,
                id="AC4.3-neutral-under-limit",
            ),
            pytest.param(
                1380,
                None,
                1500,
                "Words: 1,380 / 1,500 (approaching limit)",
                _AMBER,
                id="AC4.4-amber-90pct",
            ),
            pytest.param(
                1567,
                None,
                1500,
                "Words: 1,567 / 1,500 (over limit)",
                _RED,
                id="AC4.5-red-over-limit",
            ),
            pytest.param(
                234,
                500,
                None,
                "Words: 234 / 500 minimum (below minimum)",
                _RED,
                id="AC4.6-red-below-minimum",
            ),
            pytest.param(
                612,
                500,
                None,
                "Words: 612 / 500 minimum",
                _NEUTRAL,
                id="AC4.8-min-only-met-neutral",
            ),
        ],
    )
    def test_ac_cases(
        self,
        count: int,
        minimum: int | None,
        limit: int | None,
        expected_text: str,
        expected_classes: str,
    ) -> None:
        result = format_word_count_badge(count, minimum, limit)
        assert result.text == expected_text
        assert result.css_classes == expected_classes


class TestBadgeEdgeCases:
    """Edge case tests for format_word_count_badge.

    Verifies AC4.2 (no limits graceful handling) and boundary conditions.
    """

    @pytest.mark.parametrize(
        ("count", "minimum", "limit", "expected_text", "expected_classes"),
        [
            pytest.param(
                0,
                None,
                1500,
                "Words: 0 / 1,500",
                _NEUTRAL,
                id="zero-count-limit-only",
            ),
            pytest.param(
                0,
                100,
                1500,
                "Words: 0 / 1,500 (below minimum)",
                _RED,
                id="zero-count-both-limits",
            ),
            pytest.param(
                0,
                None,
                None,
                "Words: 0",
                _NEUTRAL,
                id="zero-count-no-limits",
            ),
            pytest.param(
                1500,
                None,
                1500,
                "Words: 1,500 / 1,500 (over limit)",
                _RED,
                id="exactly-at-limit-is-over",
            ),
            pytest.param(
                1350,
                None,
                1500,
                "Words: 1,350 / 1,500 (approaching limit)",
                _AMBER,
                id="exactly-90pct-is-amber",
            ),
            pytest.param(
                1349,
                None,
                1500,
                "Words: 1,349 / 1,500",
                _NEUTRAL,
                id="just-below-90pct-is-neutral",
            ),
            pytest.param(
                50,
                100,
                500,
                "Words: 50 / 500 (below minimum)",
                _RED,
                id="both-limits-below-min",
            ),
        ],
    )
    def test_edge_cases(
        self,
        count: int,
        minimum: int | None,
        limit: int | None,
        expected_text: str,
        expected_classes: str,
    ) -> None:
        result = format_word_count_badge(count, minimum, limit)
        assert result.text == expected_text
        assert result.css_classes == expected_classes


class TestBadgeCombinedMinMax:
    """Tests for badge with both word_minimum and word_limit set.

    Verifies AC4.3 (neutral in range), AC4.6 (below minimum with both limits).
    """

    @pytest.mark.parametrize(
        ("count", "minimum", "limit", "expected_text", "expected_classes"),
        [
            pytest.param(
                50,
                100,
                500,
                "Words: 50 / 500 (below minimum)",
                _RED,
                id="below-minimum-red",
            ),
            pytest.param(
                150,
                100,
                500,
                "Words: 150 / 500",
                _NEUTRAL,
                id="within-range-neutral",
            ),
            pytest.param(
                460,
                100,
                500,
                "Words: 460 / 500 (approaching limit)",
                _AMBER,
                id="approaching-limit-amber",
            ),
            pytest.param(
                550,
                100,
                500,
                "Words: 550 / 500 (over limit)",
                _RED,
                id="over-limit-red",
            ),
        ],
    )
    def test_combined_limits(
        self,
        count: int,
        minimum: int | None,
        limit: int | None,
        expected_text: str,
        expected_classes: str,
    ) -> None:
        result = format_word_count_badge(count, minimum, limit)
        assert result.text == expected_text
        assert result.css_classes == expected_classes
