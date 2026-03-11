"""Unit tests for wargame turn cycle pure domain helpers."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pycrdt
import pytest

from promptgrimoire.wargame.turn_cycle import (
    NO_MOVE_SENTINEL,
    build_summary_prompt,
    build_turn_prompt,
    calculate_deadline,
    expand_bootstrap,
    extract_move_text,
    render_prompt,
)


def _make_crdt_bytes(content: str) -> bytes:
    """Create CRDT bytes with content_markdown text."""
    doc = pycrdt.Doc()
    text = pycrdt.Text()
    doc["content_markdown"] = text
    with doc.transaction():
        text += content
    return doc.get_update()


class TestExpandBootstrap:
    """Tests for expand_bootstrap."""

    def test_substitutes_codename_placeholder(self) -> None:
        """Replaces {codename} with the team codename."""
        template = "You are team {codename}. Begin your mission."
        result = expand_bootstrap(template, "BOLD-GRIFFIN")
        assert result == "You are team BOLD-GRIFFIN. Begin your mission."

    def test_survives_json_braces_in_template(self) -> None:
        """Templates with JSON-like braces are not corrupted."""
        template = 'Config: {"key": "value"}. Team: {codename}.'
        result = expand_bootstrap(template, "CALM-OTTER")
        assert result == 'Config: {"key": "value"}. Team: CALM-OTTER.'

    def test_no_placeholder_returns_unchanged(self) -> None:
        """Template without {codename} is returned as-is."""
        template = "A scenario with no placeholder."
        result = expand_bootstrap(template, "BOLD-GRIFFIN")
        assert result == template


class TestCalculateDeadline:
    """Tests for calculate_deadline."""

    def test_delta_mode_adds_duration(self) -> None:
        """Delta mode: publish_time + timer_delta."""
        publish = datetime(2026, 3, 11, 10, 0, tzinfo=UTC)
        delta = timedelta(hours=2)
        result = calculate_deadline(
            publish_time=publish, timer_delta=delta, timer_wall_clock=None
        )
        assert result == datetime(2026, 3, 11, 12, 0, tzinfo=UTC)

    def test_wall_clock_future_today(self) -> None:
        """Wall-clock mode: time in the future today returns today."""
        publish = datetime(2026, 3, 11, 10, 0, tzinfo=UTC)
        wall = time(17, 0)
        result = calculate_deadline(
            publish_time=publish, timer_delta=None, timer_wall_clock=wall
        )
        assert result == datetime(2026, 3, 11, 17, 0, tzinfo=UTC)

    def test_wall_clock_past_today_rolls_to_next_day(self) -> None:
        """Wall-clock mode: time already past rolls to next day."""
        publish = datetime(2026, 3, 11, 18, 0, tzinfo=UTC)
        wall = time(9, 0)
        result = calculate_deadline(
            publish_time=publish, timer_delta=None, timer_wall_clock=wall
        )
        assert result == datetime(2026, 3, 12, 9, 0, tzinfo=UTC)

    def test_both_fields_set_raises_value_error(self) -> None:
        """Both timer fields set raises ValueError."""
        publish = datetime(2026, 3, 11, 10, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="exactly one"):
            calculate_deadline(
                publish_time=publish,
                timer_delta=timedelta(hours=1),
                timer_wall_clock=time(17, 0),
            )

    def test_neither_field_set_raises_value_error(self) -> None:
        """Neither timer field set raises ValueError."""
        publish = datetime(2026, 3, 11, 10, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="exactly one"):
            calculate_deadline(
                publish_time=publish, timer_delta=None, timer_wall_clock=None
            )


class TestExtractMoveText:
    """Tests for extract_move_text (AC4)."""

    def test_populated_crdt_returns_content(self) -> None:
        """AC4.1: Markdown extracted from populated CRDT move buffer."""
        crdt_bytes = _make_crdt_bytes("## Attack the northern flank\n\nSend scouts.")
        result = extract_move_text(crdt_bytes)
        assert result == "## Attack the northern flank\n\nSend scouts."

    def test_none_returns_sentinel(self) -> None:
        """AC4.2: None CRDT state returns NO_MOVE_SENTINEL."""
        result = extract_move_text(None)
        assert result == NO_MOVE_SENTINEL

    def test_whitespace_only_returns_sentinel(self) -> None:
        """AC4.3: Whitespace-only CRDT content returns NO_MOVE_SENTINEL."""
        crdt_bytes = _make_crdt_bytes("   \n\t  ")
        result = extract_move_text(crdt_bytes)
        assert result == NO_MOVE_SENTINEL

    def test_empty_crdt_document_returns_sentinel(self) -> None:
        """Empty CRDT document with no content_markdown returns sentinel."""
        doc = pycrdt.Doc()
        crdt_bytes = doc.get_update()
        result = extract_move_text(crdt_bytes)
        assert result == NO_MOVE_SENTINEL


class TestRenderPrompt:
    """Tests for render_prompt."""

    def test_renders_static_text(self) -> None:
        """Static t-string renders to its text."""
        result = render_prompt(t"Hello world")
        assert result == "Hello world"

    def test_renders_interpolated_values(self) -> None:
        """Interpolated values are stringified."""
        name = "Alice"
        result = render_prompt(t"Hello {name}")
        assert result == "Hello Alice"

    def test_handles_repr_conversion(self) -> None:
        """!r conversion applies repr()."""
        name = "Alice"
        result = render_prompt(t"Name: {name!r}")
        assert result == "Name: 'Alice'"

    def test_handles_str_conversion(self) -> None:
        """!s conversion applies str()."""
        value = 42
        result = render_prompt(t"Value: {value!s}")
        assert result == "Value: 42"


class TestBuildTurnPrompt:
    """Tests for build_turn_prompt."""

    def test_contains_interpolated_values(self) -> None:
        """Output includes move text and game state."""
        result = build_turn_prompt("Attack north", "Round 3 state")
        assert "Attack north" in result
        assert "Round 3 state" in result

    def test_contains_xml_tags(self) -> None:
        """Output has game_state and cadet_orders XML structure."""
        result = build_turn_prompt("orders", "state")
        assert "<game_state>" in result
        assert "</game_state>" in result
        assert "<cadet_orders>" in result
        assert "</cadet_orders>" in result


class TestBuildSummaryPrompt:
    """Tests for build_summary_prompt."""

    def test_contains_response_text(self) -> None:
        """Output includes the response text."""
        result = build_summary_prompt("The scouts found a river crossing.")
        assert "The scouts found a river crossing." in result

    def test_contains_response_xml_tag(self) -> None:
        """Output has response XML structure."""
        result = build_summary_prompt("text")
        assert "<response>" in result
        assert "</response>" in result
