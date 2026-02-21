"""Unit tests for TagGroup and Tag model defaults and field behavior.

Verifies AC1.1 (TagGroup fields), AC1.2 (Tag fields), AC1.4 (policy columns).
"""

from __future__ import annotations

from uuid import UUID


class TestTagGroupDefaults:
    """Verify TagGroup model field defaults and types (AC1.1)."""

    def test_has_auto_uuid(self, make_tag_group) -> None:
        """TagGroup gets an auto-generated UUID primary key."""
        group = make_tag_group()
        assert isinstance(group.id, UUID)

    def test_name_stored(self, make_tag_group) -> None:
        """TagGroup stores its name."""
        group = make_tag_group(name="Legal Case Brief")
        assert group.name == "Legal Case Brief"

    def test_order_index_defaults_zero(self, make_tag_group) -> None:
        """TagGroup order_index defaults to 0."""
        group = make_tag_group()
        assert group.order_index == 0

    def test_has_created_at(self, make_tag_group) -> None:
        """TagGroup has a created_at timestamp."""
        group = make_tag_group()
        assert group.created_at is not None

    def test_workspace_id_required(self, make_tag_group) -> None:
        """TagGroup stores its workspace_id."""
        group = make_tag_group()
        assert isinstance(group.workspace_id, UUID)


class TestTagDefaults:
    """Verify Tag model field defaults and types (AC1.2)."""

    def test_has_auto_uuid(self, make_tag) -> None:
        """Tag gets an auto-generated UUID primary key."""
        tag = make_tag()
        assert isinstance(tag.id, UUID)

    def test_workspace_id_required(self, make_tag) -> None:
        """Tag stores its workspace_id."""
        tag = make_tag()
        assert isinstance(tag.workspace_id, UUID)

    def test_group_id_defaults_none(self, make_tag) -> None:
        """Tag group_id defaults to None (ungrouped)."""
        tag = make_tag()
        assert tag.group_id is None

    def test_name_stored(self, make_tag) -> None:
        """Tag stores its name."""
        tag = make_tag(name="Jurisdiction")
        assert tag.name == "Jurisdiction"

    def test_description_defaults_none(self, make_tag) -> None:
        """Tag description defaults to None."""
        tag = make_tag()
        assert tag.description is None

    def test_color_stored(self, make_tag) -> None:
        """Tag stores its hex color."""
        tag = make_tag(color="#ff7f0e")
        assert tag.color == "#ff7f0e"

    def test_locked_defaults_false(self, make_tag) -> None:
        """Tag locked defaults to False."""
        tag = make_tag()
        assert tag.locked is False

    def test_order_index_defaults_zero(self, make_tag) -> None:
        """Tag order_index defaults to 0."""
        tag = make_tag()
        assert tag.order_index == 0

    def test_has_created_at(self, make_tag) -> None:
        """Tag has a created_at timestamp."""
        tag = make_tag()
        assert tag.created_at is not None


class TestActivityTagCreationPolicy:
    """Verify Activity.allow_tag_creation defaults (AC1.4)."""

    def test_activity_allow_tag_creation_defaults_none(self) -> None:
        """Activity.allow_tag_creation defaults to None (inherit from course)."""
        from promptgrimoire.db.models import Activity

        activity = Activity(
            week_id=UUID("00000000-0000-0000-0000-000000000001"),
            template_workspace_id=UUID("00000000-0000-0000-0000-000000000002"),
            title="Test",
        )
        assert activity.allow_tag_creation is None


class TestCourseTagCreationPolicy:
    """Verify Course.default_allow_tag_creation defaults (AC1.4)."""

    def test_course_default_allow_tag_creation_defaults_true(self) -> None:
        """Course.default_allow_tag_creation defaults to True."""
        from promptgrimoire.db.models import Course

        course = Course(
            code="TEST101",
            name="Test Course",
            semester="2026-S1",
        )
        assert course.default_allow_tag_creation is True
