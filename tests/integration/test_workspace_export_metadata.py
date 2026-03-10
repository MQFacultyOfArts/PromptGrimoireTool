"""Integration tests for workspace export metadata resolution.

Verifies that get_workspace_export_metadata() returns the correct owner
and placement data for all workspace placement types, and that the
rendered filename stems use owner identity (not viewer identity).

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)

EXPORT_DATE = date(2026, 3, 9)


async def _setup_hierarchy(
    suffix: str,
) -> tuple:
    """Create Course -> Week -> Activity hierarchy with unique codes."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"E{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code, name=f"Export Test {suffix}", semester="2026-S1"
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title=f"Activity {suffix}")
    return course, week, activity


class TestGetWorkspaceExportMetadata:
    """Raw metadata resolution tests."""

    @pytest.mark.asyncio
    async def test_activity_placed_returns_owner_and_hierarchy(self) -> None:
        """Activity-placed workspace returns owner and full hierarchy.

        Verifies AC1.1 and AC1.2: metadata uses workspace owner, not viewer.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            place_workspace_in_activity,
            update_workspace_title,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-owner-{tag}@test.local",
            display_name="Alice Nguyen",
        )
        # viewer exists but should NOT appear in metadata
        await create_user(
            email=f"em-viewer-{tag}@test.local",
            display_name="Bob Smith",
        )

        course, _week, activity = await _setup_hierarchy(tag)
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)
        await update_workspace_title(ws.id, "My Essay")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)

        assert meta is not None
        assert meta.course_code == course.code
        assert meta.activity_title == activity.title
        assert meta.workspace_title == "My Essay"
        assert meta.owner_display_name == "Alice Nguyen"

    @pytest.mark.asyncio
    async def test_course_placed_has_no_activity_title(self) -> None:
        """Course-placed workspace returns course_code but activity_title=None.

        Verifies AC1.3: course-placed workspaces defer activity fallback.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            place_workspace_in_course,
            update_workspace_title,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-course-{tag}@test.local",
            display_name="Carol Deng",
        )
        course, _week, _activity = await _setup_hierarchy(tag)
        ws = await create_workspace()
        await place_workspace_in_course(ws.id, course.id)
        await update_workspace_title(ws.id, "Loose Essay")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)

        assert meta is not None
        assert meta.course_code == course.code
        assert meta.activity_title is None
        assert meta.workspace_title == "Loose Essay"
        assert meta.owner_display_name == "Carol Deng"

    @pytest.mark.asyncio
    async def test_loose_workspace_has_no_course_or_activity(self) -> None:
        """Fully loose workspace returns None for course_code and activity_title.

        Verifies AC1.4.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            update_workspace_title,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-loose-{tag}@test.local",
            display_name="Dan Kim",
        )
        ws = await create_workspace()
        await update_workspace_title(ws.id, "Freeform Notes")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)

        assert meta is not None
        assert meta.course_code is None
        assert meta.activity_title is None
        assert meta.workspace_title == "Freeform Notes"
        assert meta.owner_display_name == "Dan Kim"

    @pytest.mark.asyncio
    async def test_blank_workspace_title_returns_blank(self) -> None:
        """Blank workspace title is returned as-is (fallback is builder's job).

        Verifies AC1.5: raw metadata preserves blank title.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            update_workspace_title,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-blank-{tag}@test.local",
            display_name="Eve Park",
        )
        ws = await create_workspace()
        await update_workspace_title(ws.id, "")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)

        assert meta is not None
        assert meta.workspace_title == ""

    @pytest.mark.asyncio
    async def test_blank_owner_display_name_returns_blank(self) -> None:
        """Blank owner display name is returned as-is (fallback is builder's job).

        Verifies AC1.6: raw metadata preserves blank owner name.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            update_workspace_title,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-blankname-{tag}@test.local",
            display_name="",
        )
        ws = await create_workspace()
        await update_workspace_title(ws.id, "Some Title")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)

        assert meta is not None
        assert meta.owner_display_name == ""

    @pytest.mark.asyncio
    async def test_no_owner_acl_returns_none_display_name(self) -> None:
        """Workspace with no owner ACL row returns owner_display_name=None."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
        )

        ws = await create_workspace()

        meta = await get_workspace_export_metadata(ws.id)

        assert meta is not None
        assert meta.owner_display_name is None

    @pytest.mark.asyncio
    async def test_missing_workspace_returns_none(self) -> None:
        """Non-existent workspace returns None.

        Verifies AC1.6 edge case.
        """
        from promptgrimoire.db.workspaces import get_workspace_export_metadata

        result = await get_workspace_export_metadata(uuid4())
        assert result is None


class TestWorkspaceExportMetadataFilenameContract:
    """End-to-end tests: raw metadata -> rendered filename stem."""

    @pytest.mark.asyncio
    async def test_activity_placed_stem_uses_owner_name(self) -> None:
        """Activity-placed workspace stem uses owner name, not viewer.

        Verifies AC1.1, AC1.2.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            place_workspace_in_activity,
            update_workspace_title,
        )
        from promptgrimoire.export.filename import (
            PdfExportFilenameContext,
            build_pdf_export_stem,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-stem-act-{tag}@test.local",
            display_name="Alice Nguyen",
        )
        course, _week, activity = await _setup_hierarchy(tag)
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)
        await update_workspace_title(ws.id, "My Essay")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)
        assert meta is not None

        ctx = PdfExportFilenameContext(
            course_code=meta.course_code,
            activity_title=meta.activity_title,
            workspace_title=meta.workspace_title,
            owner_display_name=meta.owner_display_name,
            export_date=EXPORT_DATE,
        )
        stem = build_pdf_export_stem(ctx)

        assert "Nguyen" in stem
        assert "Alice" in stem
        assert course.code in stem
        assert "20260309" in stem
        # Viewer name must NOT appear
        assert "Bob" not in stem
        assert "Smith" not in stem

    @pytest.mark.asyncio
    async def test_course_placed_stem_contains_loose_work(self) -> None:
        """Course-placed workspace stem uses Loose_Work for activity slot.

        Verifies AC1.3.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            place_workspace_in_course,
            update_workspace_title,
        )
        from promptgrimoire.export.filename import (
            PdfExportFilenameContext,
            build_pdf_export_stem,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-stem-crs-{tag}@test.local",
            display_name="Carol Deng",
        )
        course, _week, _activity = await _setup_hierarchy(tag)
        ws = await create_workspace()
        await place_workspace_in_course(ws.id, course.id)
        await update_workspace_title(ws.id, "Loose Essay")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)
        assert meta is not None

        ctx = PdfExportFilenameContext(
            course_code=meta.course_code,
            activity_title=meta.activity_title,
            workspace_title=meta.workspace_title,
            owner_display_name=meta.owner_display_name,
            export_date=EXPORT_DATE,
        )
        stem = build_pdf_export_stem(ctx)

        assert "Loose_Work" in stem
        assert course.code in stem
        assert "Deng" in stem

    @pytest.mark.asyncio
    async def test_loose_stem_contains_unplaced_and_loose_work(self) -> None:
        """Fully loose workspace stem starts with Unplaced and contains Loose_Work.

        Verifies AC1.4.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            update_workspace_title,
        )
        from promptgrimoire.export.filename import (
            PdfExportFilenameContext,
            build_pdf_export_stem,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-stem-loose-{tag}@test.local",
            display_name="Dan Kim",
        )
        ws = await create_workspace()
        await update_workspace_title(ws.id, "Freeform Notes")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)
        assert meta is not None

        ctx = PdfExportFilenameContext(
            course_code=meta.course_code,
            activity_title=meta.activity_title,
            workspace_title=meta.workspace_title,
            owner_display_name=meta.owner_display_name,
            export_date=EXPORT_DATE,
        )
        stem = build_pdf_export_stem(ctx)

        assert stem.startswith("Unplaced_")
        assert "Loose_Work" in stem
        assert "Kim" in stem

    @pytest.mark.asyncio
    async def test_blank_title_stem_uses_workspace_fallback(self) -> None:
        """Blank workspace title becomes Workspace in the stem.

        Verifies AC1.5.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            update_workspace_title,
        )
        from promptgrimoire.export.filename import (
            PdfExportFilenameContext,
            build_pdf_export_stem,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-stem-blank-{tag}@test.local",
            display_name="Eve Park",
        )
        ws = await create_workspace()
        await update_workspace_title(ws.id, "")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)
        assert meta is not None

        ctx = PdfExportFilenameContext(
            course_code=meta.course_code,
            activity_title=meta.activity_title,
            workspace_title=meta.workspace_title,
            owner_display_name=meta.owner_display_name,
            export_date=EXPORT_DATE,
        )
        stem = build_pdf_export_stem(ctx)

        assert "Workspace" in stem

    @pytest.mark.asyncio
    async def test_blank_owner_stem_uses_unknown_unknown(self) -> None:
        """Blank owner display name becomes Unknown_Unknown in the stem.

        Verifies AC1.6.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace_export_metadata,
            update_workspace_title,
        )
        from promptgrimoire.export.filename import (
            PdfExportFilenameContext,
            build_pdf_export_stem,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"em-stem-unk-{tag}@test.local",
            display_name="",
        )
        ws = await create_workspace()
        await update_workspace_title(ws.id, "Some Title")
        await grant_permission(ws.id, owner.id, "owner")

        meta = await get_workspace_export_metadata(ws.id)
        assert meta is not None

        ctx = PdfExportFilenameContext(
            course_code=meta.course_code,
            activity_title=meta.activity_title,
            workspace_title=meta.workspace_title,
            owner_display_name=meta.owner_display_name,
            export_date=EXPORT_DATE,
        )
        stem = build_pdf_export_stem(ctx)

        assert "Unknown_Unknown" in stem
