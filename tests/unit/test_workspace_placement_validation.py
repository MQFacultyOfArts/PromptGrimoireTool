"""Unit tests for Workspace placement mutual exclusivity validation.

Tests the Pydantic model_validator that enforces activity_id and course_id
are mutually exclusive on the Workspace model. No database required.

Note: SQLModel table=True classes bypass Pydantic validators on direct
construction (Workspace(...)). The validator fires via model_validate(),
which is the codepath used when loading from DB or validating user input.
We test both paths: model_validate for validator coverage, and the DB
CHECK constraint is tested in integration tests.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.db.models import Workspace


class TestWorkspacePlacementExclusivity:
    """Tests for the _check_placement_exclusivity model validator."""

    def test_both_none_is_valid(self) -> None:
        """Workspace with neither activity_id nor course_id is valid."""
        ws = Workspace.model_validate({})
        assert ws.activity_id is None
        assert ws.course_id is None

    def test_activity_only_is_valid(self) -> None:
        """Workspace with only activity_id set is valid."""
        ws = Workspace.model_validate({"activity_id": uuid4()})
        assert ws.activity_id is not None
        assert ws.course_id is None

    def test_course_only_is_valid(self) -> None:
        """Workspace with only course_id set is valid."""
        ws = Workspace.model_validate({"course_id": uuid4()})
        assert ws.course_id is not None
        assert ws.activity_id is None

    def test_both_set_raises_value_error(self) -> None:
        """Workspace with both activity_id and course_id raises ValueError."""
        with pytest.raises(ValueError, match="cannot be placed in both"):
            Workspace.model_validate({"activity_id": uuid4(), "course_id": uuid4()})

    def test_direct_construction_bypasses_validator(self) -> None:
        """SQLModel table=True direct construction skips Pydantic validators.

        This documents the known SQLModel behavior: the CHECK constraint
        at the database level (tested in integration tests) is the actual
        guard for direct construction paths.
        """
        # This does NOT raise -- SQLModel uses SQLAlchemy's __init__, not Pydantic's
        ws = Workspace(activity_id=uuid4(), course_id=uuid4())
        assert ws.activity_id is not None
        assert ws.course_id is not None

    def test_enable_save_as_draft_defaults_false(self) -> None:
        """enable_save_as_draft defaults to False."""
        ws = Workspace()
        assert ws.enable_save_as_draft is False

    def test_enable_save_as_draft_can_be_set(self) -> None:
        """enable_save_as_draft can be set to True."""
        ws = Workspace(enable_save_as_draft=True)
        assert ws.enable_save_as_draft is True
