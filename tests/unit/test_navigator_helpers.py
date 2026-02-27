"""Unit tests for navigator pure helper functions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from promptgrimoire.db.navigator import NavigatorRow
from promptgrimoire.pages.navigator._helpers import (
    breadcrumb,
    format_updated_at,
    group_by_owner,
    group_rows_by_section,
    group_shared_in_unit_by_course,
    workspace_url,
)


def _make_row(
    *,
    section: str = "my_work",
    course_code: str | None = None,
    week_title: str | None = None,
    activity_title: str | None = None,
    updated_at: datetime | None = None,
    workspace_id: UUID | None = None,
    course_id: UUID | None = None,
    owner_user_id: UUID | None = None,
) -> NavigatorRow:
    """Build a NavigatorRow with sensible defaults."""
    return NavigatorRow(
        section=section,
        section_priority=1,
        workspace_id=workspace_id or uuid4(),
        activity_id=None,
        activity_title=activity_title,
        week_title=week_title,
        week_number=None,
        course_id=course_id,
        course_code=course_code,
        course_name=None,
        title=None,
        updated_at=updated_at,
        owner_user_id=owner_user_id,
        owner_display_name=None,
        permission="owner",
        shared_with_class=False,
        anonymous_sharing=False,
        owner_is_privileged=False,
        sort_key=datetime.now(UTC),
        row_id=uuid4(),
    )


class TestFormatUpdatedAt:
    def test_none_returns_empty(self) -> None:
        row = _make_row(updated_at=None)
        assert format_updated_at(row) == ""

    def test_formats_date(self) -> None:
        dt = datetime(2026, 2, 15, 14, 30, tzinfo=UTC)
        row = _make_row(updated_at=dt)
        assert format_updated_at(row) == "15 Feb 2026, 14:30"


class TestBreadcrumb:
    def test_full_breadcrumb(self) -> None:
        row = _make_row(
            course_code="LAWS1100",
            week_title="Week 1",
            activity_title="Annotate Interview",
        )
        assert breadcrumb(row) == "LAWS1100 > Week 1 > Annotate Interview"

    def test_course_only(self) -> None:
        row = _make_row(course_code="LAWS1100")
        assert breadcrumb(row) == "LAWS1100"

    def test_empty(self) -> None:
        row = _make_row()
        assert breadcrumb(row) == ""

    def test_partial(self) -> None:
        row = _make_row(course_code="LAWS1100", activity_title="Brief")
        assert breadcrumb(row) == "LAWS1100 > Brief"


class TestWorkspaceUrl:
    def test_url_format(self) -> None:
        ws_id = UUID("12345678-1234-1234-1234-123456789abc")
        url = workspace_url(ws_id)
        assert url == "/annotation?workspace_id=12345678-1234-1234-1234-123456789abc"


class TestGroupRowsBySection:
    def test_groups_by_section(self) -> None:
        rows = [
            _make_row(section="my_work"),
            _make_row(section="unstarted"),
            _make_row(section="my_work"),
        ]
        groups = group_rows_by_section(rows)
        assert len(groups["my_work"]) == 2
        assert len(groups["unstarted"]) == 1

    def test_empty_input(self) -> None:
        assert group_rows_by_section([]) == {}


class TestGroupSharedInUnitByCourse:
    def test_groups_by_course_id(self) -> None:
        c1, c2 = uuid4(), uuid4()
        rows = [
            _make_row(course_id=c1),
            _make_row(course_id=c2),
            _make_row(course_id=c1),
        ]
        groups = group_shared_in_unit_by_course(rows)
        assert len(groups[c1]) == 2
        assert len(groups[c2]) == 1

    def test_none_course_id_skipped(self) -> None:
        rows = [_make_row(course_id=None)]
        groups = group_shared_in_unit_by_course(rows)
        assert groups == {}


class TestGroupByOwner:
    def test_groups_by_owner(self) -> None:
        u1, u2 = uuid4(), uuid4()
        rows = [
            _make_row(owner_user_id=u1),
            _make_row(owner_user_id=u2),
            _make_row(owner_user_id=u1),
        ]
        groups = group_by_owner(rows)
        assert len(groups[u1]) == 2
        assert len(groups[u2]) == 1

    def test_none_owner(self) -> None:
        rows = [_make_row(owner_user_id=None)]
        groups = group_by_owner(rows)
        assert len(groups[None]) == 1
