"""Unit tests for wargame team CRUD service contracts."""

from __future__ import annotations

from uuid import uuid4


class TestDuplicateCodenameError:
    """Contract tests for DuplicateCodenameError."""

    def test_stores_activity_id_codename_and_message(self) -> None:
        """The exception exposes duplicate context for callers."""
        from promptgrimoire.db.wargames import DuplicateCodenameError

        activity_id = uuid4()
        error = DuplicateCodenameError(activity_id, "RED-FOX")

        assert error.activity_id == activity_id
        assert error.codename == "RED-FOX"
        assert "RED-FOX" in str(error)
