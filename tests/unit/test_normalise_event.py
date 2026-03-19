"""Tests for normalise_event() error class key generation."""

from __future__ import annotations

from scripts.incident.analysis import normalise_event


class TestNormaliseEvent:
    def test_hex_address(self) -> None:
        assert normalise_event("Error at 0x7f2a3b4c5d6e") == "Error at <ADDR>"

    def test_uuid(self) -> None:
        assert (
            normalise_event("Session abc12345-def6-7890-abcd-ef0123456789 expired")
            == "Session <UUID> expired"
        )

    def test_task_name(self) -> None:
        assert normalise_event("Task-42 failed") == "Task-<N> failed"

    def test_invalidate_pool_state(self) -> None:
        """INVALIDATE strips transient counters but keeps size."""
        raw = (
            "INVALIDATE Connection <ADDR>"
            " (Pool size=10 checked_in=5 checked_out=3 overflow=2/20)"
        )
        expected = "INVALIDATE Connection <ADDR> (Pool size=10)"
        assert normalise_event(raw) == expected

    def test_mixed_uuid_and_hex(self) -> None:
        """UUID replaced before hex address — both handled correctly."""
        raw = "Obj abc12345-def6-7890-abcd-ef0123456789 at 0xdeadbeef"
        expected = "Obj <UUID> at <ADDR>"
        assert normalise_event(raw) == expected

    def test_no_op(self) -> None:
        assert normalise_event("normal log message") == "normal log message"

    def test_empty_string(self) -> None:
        assert normalise_event("") == ""
