"""Integration tests for cli_loadtest.py's raw-SQL migrated queries.

Covers the ADR 0004 requirement that every migrated query keep or gain
integration coverage that executes against Postgres
(docs/architecture/raw-sql-convention.md), plus characterisation coverage
for the DB-touching helpers extracted from _seed_student_workspaces and
_seed_acl_shares during the ty-bump complexity cleanup (both functions were
flagged over the complexity-15 threshold and had zero prior test coverage).

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from promptgrimoire.db.models import User

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_week_activity(*, title: str = "Query Test Activity"):
    """Create Course -> Week -> Activity with a template workspace.

    Returns (Course, Week, Activity).
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code, name="LoadtestQueryTest", semester="2026-S1"
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title=title)
    return course, week, activity


async def _make_student(email_prefix: str = "loadtest-query") -> User:
    from promptgrimoire.db.users import find_or_create_user

    user, _created = await find_or_create_user(
        email=f"{email_prefix}-{uuid4().hex[:8]}@test.local",
        display_name="Query Test Student",
    )
    return user


class TestCheckWorkspaceExists:
    """Migrated from SQLModel .join() -- raw SQL with a JOIN + owner filter."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_workspace(self) -> None:
        from promptgrimoire.cli_loadtest import _check_workspace_exists

        _course, _week, activity = await _make_course_week_activity()
        student = await _make_student()

        assert await _check_workspace_exists(activity.id, student.id) is False

    @pytest.mark.asyncio
    async def test_returns_true_after_owner_workspace_created(self) -> None:
        from promptgrimoire.cli_loadtest import _check_workspace_exists
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        _course, _week, activity = await _make_course_week_activity()
        student = await _make_student()

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        await grant_permission(workspace.id, student.id, "owner")

        assert await _check_workspace_exists(activity.id, student.id) is True

    @pytest.mark.asyncio
    async def test_ignores_non_owner_permission(self) -> None:
        """A viewer-only ACL entry must not count as 'workspace exists'."""
        from promptgrimoire.cli_loadtest import _check_workspace_exists
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        _course, _week, activity = await _make_course_week_activity()
        student = await _make_student("loadtest-query-viewer")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        await grant_permission(workspace.id, student.id, "viewer")

        assert await _check_workspace_exists(activity.id, student.id) is False


class TestResolveCourseIdForCode:
    """Migrated from SQLModel .join() -- raw SQL joining week to activity."""

    @pytest.mark.asyncio
    async def test_resolves_course_id_via_activity_hierarchy(self) -> None:
        from promptgrimoire.cli_loadtest import (
            _course_id_cache,
            _resolve_course_id_for_code,
        )

        course, _week, activity = await _make_course_week_activity()
        code = course.code
        _course_id_cache.pop(code, None)  # avoid cross-test cache bleed

        course_activities = {code: [(activity, activity.template_workspace_id)]}
        resolved = await _resolve_course_id_for_code(code, course_activities)

        assert resolved == course.id

    @pytest.mark.asyncio
    async def test_caches_result_across_calls(self) -> None:
        from promptgrimoire.cli_loadtest import (
            _course_id_cache,
            _resolve_course_id_for_code,
        )

        course, _week, activity = await _make_course_week_activity()
        code = course.code
        _course_id_cache.pop(code, None)

        course_activities = {code: [(activity, activity.template_workspace_id)]}
        first = await _resolve_course_id_for_code(code, course_activities)
        # Second call passes an empty mapping: if the result weren't cached,
        # `acts = course_activities.get(code, [])` would be empty and this
        # would return None instead of the cached course id.
        second = await _resolve_course_id_for_code(code, {})

        assert first == course.id
        assert second == course.id

    @pytest.mark.asyncio
    async def test_returns_none_for_course_with_no_activities(self) -> None:
        from promptgrimoire.cli_loadtest import (
            _course_id_cache,
            _resolve_course_id_for_code,
        )

        code = f"NOACT{uuid4().hex[:6].upper()}"
        _course_id_cache.pop(code, None)

        assert await _resolve_course_id_for_code(code, {}) is None


class TestEnsureActivitiesForCourse:
    """Migrated from SQLModel .in_() -- raw SQL with = ANY(...)."""

    @pytest.mark.asyncio
    async def test_second_pass_reuses_activity_found_by_raw_sql(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The existing_acts query must find activities created by a prior
        pass, so a second pass reuses rather than duplicates them."""
        import promptgrimoire.cli_loadtest as loadtest_mod
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.weeks import create_week

        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(
            code=code, name="Ensure Activities Test", semester="2026-S1"
        )
        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        async with get_session() as session:
            session.add(week)
            week.is_published = True
            await session.flush()
            await session.refresh(week)

        week_map = {1: week}
        monkeypatch.setitem(
            loadtest_mod.ACTIVITY_DEFS, code, [(1, "Shared Activity Title")]
        )

        first_pass = await loadtest_mod._ensure_activities_for_course(code, week_map)
        assert len(first_pass) == 1
        created_activity_id = first_pass[0][0].id

        second_pass = await loadtest_mod._ensure_activities_for_course(code, week_map)

        assert len(second_pass) == 1
        assert second_pass[0][0].id == created_activity_id


class TestFetchCandidateWorkspaces:
    """Migrated from SQLModel .join() x3 -- raw SQL with three JOINs."""

    @pytest.mark.asyncio
    async def test_excludes_template_and_non_owner_workspaces(self) -> None:
        from promptgrimoire.cli_loadtest import _fetch_candidate_workspaces
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        course, _week, activity = await _make_course_week_activity()
        student = await _make_student("loadtest-query-candidate")

        # Owner workspace on a real activity: should be a candidate.
        student_ws = await create_workspace()
        await place_workspace_in_activity(student_ws.id, activity.id)
        await grant_permission(student_ws.id, student.id, "owner")

        # Same activity, viewer-only: must be excluded (not owner).
        other_ws = await create_workspace()
        await place_workspace_in_activity(other_ws.id, activity.id)
        viewer = await _make_student("loadtest-query-candidate-viewer")
        await grant_permission(other_ws.id, viewer.id, "viewer")

        # The activity's own template workspace has an owner too (from
        # create_activity's bootstrap) but must never appear as a candidate.
        candidates = await _fetch_candidate_workspaces({course.code: course})

        candidate_ids = {ws_id for ws_id, _owner, _cid in candidates}
        assert student_ws.id in candidate_ids
        assert other_ws.id not in candidate_ids
        assert activity.template_workspace_id not in candidate_ids

        owner_lookup = {ws_id: owner for ws_id, owner, _cid in candidates}
        assert owner_lookup[student_ws.id] == student.id

    @pytest.mark.asyncio
    async def test_no_courses_returns_empty(self) -> None:
        from promptgrimoire.cli_loadtest import _fetch_candidate_workspaces

        assert await _fetch_candidate_workspaces({}) == []


class TestGrantSharesForWorkspace:
    """Extracted from _seed_acl_shares (complexity 18 -> decomposed)."""

    @pytest.mark.asyncio
    async def test_grants_one_or_two_shares_excluding_owner(self) -> None:
        from promptgrimoire.cli_loadtest import _grant_shares_for_workspace
        from promptgrimoire.db.workspaces import create_workspace

        owner = await _make_student("loadtest-query-owner")
        peer_a = await _make_student("loadtest-query-peer-a")
        peer_b = await _make_student("loadtest-query-peer-b")
        course_id = uuid4()

        workspace = await create_workspace()
        course_students = {course_id: [owner, peer_a, peer_b]}

        granted = await _grant_shares_for_workspace(
            workspace.id, owner.id, course_id, course_students
        )

        assert 1 <= granted <= 2

        grants = await _fetch_acl_grants(workspace.id)
        assert owner.id not in grants
        assert len(grants) == granted
        assert set(grants).issubset({peer_a.id, peer_b.id})
        assert all(perm in ("editor", "viewer") for perm in grants.values())

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_eligible_students(self) -> None:
        """Only the owner is enrolled in the course -- nobody to share with."""
        from promptgrimoire.cli_loadtest import _grant_shares_for_workspace
        from promptgrimoire.db.workspaces import create_workspace

        owner = await _make_student("loadtest-query-solo-owner")
        course_id = uuid4()
        workspace = await create_workspace()
        course_students = {course_id: [owner]}

        granted = await _grant_shares_for_workspace(
            workspace.id, owner.id, course_id, course_students
        )

        assert granted == 0
        assert await _fetch_acl_grants(workspace.id) == {}

    @pytest.mark.asyncio
    async def test_returns_zero_when_course_has_no_students_mapped(self) -> None:
        from promptgrimoire.cli_loadtest import _grant_shares_for_workspace
        from promptgrimoire.db.workspaces import create_workspace

        owner_id = uuid4()
        workspace = await create_workspace()

        granted = await _grant_shares_for_workspace(workspace.id, owner_id, uuid4(), {})

        assert granted == 0


async def _fetch_acl_grants(workspace_id: UUID) -> dict[UUID, str]:
    """Read back ACL grants for a workspace via the same raw-SQL idiom."""
    from sqlalchemy import tstring

    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        rows = await session.execute(
            tstring(
                t"""
                SELECT user_id, permission
                FROM acl_entry
                WHERE workspace_id = {workspace_id}
                """
            )
        )
        return {row.user_id: row.permission for row in rows}


class TestBuildTemplateDocCache:
    """Extracted from _seed_student_workspaces (complexity 27 -> decomposed)."""

    @pytest.mark.asyncio
    async def test_fetches_once_per_unique_template_id(self) -> None:
        from promptgrimoire.cli_loadtest import _build_template_doc_cache
        from promptgrimoire.db.workspace_documents import add_document

        _course, _week, activity = await _make_course_week_activity()
        tmpl_id = activity.template_workspace_id
        await add_document(
            workspace_id=tmpl_id,
            type="source",
            content="<p>hello</p>",
            source_type="html",
            title="Doc 1",
        )

        # Same template id appears twice across two "activities" -- the
        # cache must still hold exactly one fetch's worth of documents.
        course_activities = {"X": [(activity, tmpl_id), (activity, tmpl_id)]}

        cache = await _build_template_doc_cache(course_activities)

        assert tmpl_id in cache
        assert len(cache[tmpl_id]) == 1
        assert cache[tmpl_id][0].title == "Doc 1"

    @pytest.mark.asyncio
    async def test_empty_course_activities_produces_empty_cache(self) -> None:
        from promptgrimoire.cli_loadtest import _build_template_doc_cache

        assert await _build_template_doc_cache({}) == {}


class TestCreateActivityWorkspacesForStudent:
    """Extracted from _seed_student_workspaces (complexity 27 -> decomposed)."""

    @pytest.mark.asyncio
    async def test_creates_workspace_when_probability_roll_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import promptgrimoire.cli_loadtest as loadtest_mod
        from promptgrimoire.db.workspace_documents import add_document

        _course, _week, activity = await _make_course_week_activity()
        tmpl_id = activity.template_workspace_id
        await add_document(
            workspace_id=tmpl_id,
            type="source",
            content="<p>x</p>",
            source_type="html",
            title="Template Doc",
        )
        student = await _make_student("loadtest-query-actor")

        # Force the 70%-chance roll to always pass (random() <= threshold).
        monkeypatch.setattr(loadtest_mod.random, "random", lambda: 0.0)

        course_activities = {"X": [(activity, tmpl_id)]}
        template_doc_cache = await loadtest_mod._build_template_doc_cache(
            course_activities
        )

        (
            ws_count,
            doc_count,
            shared_count,
        ) = await loadtest_mod._create_activity_workspaces_for_student(
            student, ["X"], course_activities, template_doc_cache
        )

        assert ws_count == 1
        assert doc_count == 1
        assert shared_count in (0, 1)
        assert await loadtest_mod._check_workspace_exists(activity.id, student.id)

    @pytest.mark.asyncio
    async def test_skips_when_probability_roll_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import promptgrimoire.cli_loadtest as loadtest_mod

        _course, _week, activity = await _make_course_week_activity()
        student = await _make_student("loadtest-query-actor-skip")

        # Force the roll to always fail (random() > threshold).
        monkeypatch.setattr(loadtest_mod.random, "random", lambda: 1.0)

        result = await loadtest_mod._create_activity_workspaces_for_student(
            student, ["X"], {"X": [(activity, activity.template_workspace_id)]}, {}
        )

        assert result == (0, 0, 0)
        assert not await loadtest_mod._check_workspace_exists(activity.id, student.id)

    @pytest.mark.asyncio
    async def test_skips_activity_the_student_already_has_a_workspace_for(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import promptgrimoire.cli_loadtest as loadtest_mod
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        _course, _week, activity = await _make_course_week_activity()
        student = await _make_student("loadtest-query-actor-exists")

        existing_ws = await create_workspace()
        await place_workspace_in_activity(existing_ws.id, activity.id)
        await grant_permission(existing_ws.id, student.id, "owner")

        # Force the roll to pass so idempotency, not probability, is what's
        # under test here.
        monkeypatch.setattr(loadtest_mod.random, "random", lambda: 0.0)

        result = await loadtest_mod._create_activity_workspaces_for_student(
            student, ["X"], {"X": [(activity, activity.template_workspace_id)]}, {}
        )

        assert result == (0, 0, 0)


class TestPrintSummary:
    """Migrated from SQLModel .like()/.in_() -- raw SQL with LIKE / = ANY(...)."""

    @pytest.mark.asyncio
    async def test_reports_accurate_scoped_enrollment_and_phase_counts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import promptgrimoire.cli_loadtest as loadtest_mod
        from promptgrimoire.db.courses import enroll_user

        course, _week, _activity = await _make_course_week_activity()
        student = await _make_student("loadtest-summary")
        await enroll_user(course_id=course.id, user_id=student.id, role="student")

        captured: list[str] = []
        monkeypatch.setattr(loadtest_mod.console, "print", captured.append)

        counts = loadtest_mod.LoadTestCounts(
            activity_ws_count=1,
            loose_ws_count=2,
            total_doc_count=3,
            share_count=4,
            shared_with_class_count=5,
        )
        await loadtest_mod._print_summary(
            courses={course.code: course},
            course_activities={},
            counts=counts,
        )

        rendered = "\n".join(str(c) for c in captured)
        # Enrollment count is scoped to this one freshly-created course, so
        # it is exact even under parallel test execution.
        assert "Enrollments: 1" in rendered
        assert "Workspaces (activity): 1" in rendered
        assert "Workspaces (loose): 2" in rendered
        assert "Documents: 3" in rendered
        assert "ACL shares: 4" in rendered
        assert "Workspaces with shared_with_class: 5" in rendered

    @pytest.mark.asyncio
    async def test_zero_enrollments_for_course_with_no_students(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import promptgrimoire.cli_loadtest as loadtest_mod

        course, _week, _activity = await _make_course_week_activity()

        captured: list[str] = []
        monkeypatch.setattr(loadtest_mod.console, "print", captured.append)

        await loadtest_mod._print_summary(
            courses={course.code: course},
            course_activities={},
            counts=loadtest_mod.LoadTestCounts(
                activity_ws_count=0,
                loose_ws_count=0,
                total_doc_count=0,
                share_count=0,
                shared_with_class_count=0,
            ),
        )

        rendered = "\n".join(str(c) for c in captured)
        assert "Enrollments: 0" in rendered


class TestValidateEnsureStudentWorkspace:
    """Migrated from SQLModel .join() -- raw SQL, same shape as
    _check_workspace_exists but selecting the workspace id itself."""

    @pytest.mark.asyncio
    async def test_finds_existing_owner_workspace_via_raw_sql(self) -> None:
        from promptgrimoire.cli_loadtest import _validate_ensure_student_workspace
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        _course, _week, activity = await _make_course_week_activity()
        student = await _make_student("loadtest-query-validate")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        await grant_permission(workspace.id, student.id, "owner")

        resolved = await _validate_ensure_student_workspace(
            activity, activity.template_workspace_id, student
        )

        assert resolved == workspace.id
