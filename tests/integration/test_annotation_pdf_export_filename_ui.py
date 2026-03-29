"""PDF export filename policy — end-to-end through the real export path.

Verifies that clicking Export PDF on the annotation page produces an ExportJob
in the database whose ``payload["filename"]`` matches the filename policy.

Feature borders tested:
- Placed workspace: filename contains course code, activity, owner, date
  (not ``workspace_{uuid}``)
- Respond tab: same workspace yields identical filename regardless of tab
- Loose workspace: unplaced workspace uses fallback segments ("Unplaced", date)

Mocks (environment, not seam):
- ``_server_local_export_date``: controls the date segment of the filename
- ``_start_export_polling``: prevents background timer (no worker in test)
- ``_extract_response_markdown``: Now reads from the CRDT mirror (no JS
  round-trip), but the test harness has no CRDT state. Returns empty string
  (response text is irrelevant to filename policy).

NiceGUI dispatches async click handlers as background tasks via
``handle_event`` → ``background_tasks.create()``. So after firing the
click event, we poll the DB for the ExportJob rather than assuming the
handler completed synchronously.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import ExportJob
from promptgrimoire.export.filename import (
    PdfExportFilenameContext,
    build_pdf_export_stem,
)
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _click_testid,
    _find_by_testid,
    _fire_event_listeners_async,
    _should_see_testid,
    wait_for,
    wait_for_annotation_load,
)

if TYPE_CHECKING:
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.nicegui_ui,
]

FIXED_DATE = date(2026, 3, 9)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _create_course() -> tuple[UUID, str]:
    """Create a course with a unique code. Returns (course_id, code)."""
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"EXP{uid.upper()}"
    course = await create_course(
        code=code, name=f"Export Test {uid}", semester="2026-S1"
    )
    return course.id, code


async def _enroll(course_id: UUID, email: str, role: str) -> UUID:
    """Ensure user exists and enroll them. Returns user_id."""
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.users import find_or_create_user

    user_record, _ = await find_or_create_user(
        email=email, display_name=email.split("@", maxsplit=1)[0]
    )
    await enroll_user(course_id=course_id, user_id=user_record.id, role=role)
    return user_record.id


async def _create_week(course_id: UUID) -> UUID:
    from promptgrimoire.db.weeks import create_week

    week = await create_week(course_id=course_id, week_number=1, title="Export Week")
    return week.id


async def _create_activity(
    week_id: UUID, title: str = "Export Activity"
) -> tuple[UUID, UUID]:
    from promptgrimoire.db.activities import create_activity

    activity = await create_activity(week_id=week_id, title=title)
    return activity.id, activity.template_workspace_id


async def _add_document(workspace_id: UUID) -> UUID:
    """Add a minimal source document to the workspace. Returns document id."""
    from promptgrimoire.db.workspace_documents import add_document

    doc = await add_document(
        workspace_id=workspace_id,
        type="source",
        content="<p>Test content for export.</p>",
        source_type="paste",
        title="Test Source",
    )
    return doc.id


async def _setup_placed_workspace(
    email: str = "exporter@uni.edu",
    activity_title: str = "Export Activity",
) -> tuple[UUID, UUID, str]:
    """Create course/week/activity/workspace with document and owner ACL.

    Returns (workspace_id, user_id, course_code).
    """
    from promptgrimoire.db.acl import grant_permission
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    course_id, code = await _create_course()
    user_id = await _enroll(course_id, email, "student")
    week_id = await _create_week(course_id)
    _activity_id, template_ws_id = await _create_activity(week_id, title=activity_title)

    # Add a doc to the template so the clone has content
    await _add_document(template_ws_id)

    # Clone a student workspace (returns tuple of workspace + doc map)
    ws, _doc_map = await clone_workspace_from_activity(_activity_id, user_id)
    await grant_permission(ws.id, user_id, "owner")

    # Set a workspace title
    from promptgrimoire.db.engine import get_session

    async with get_session() as session:
        from promptgrimoire.db.models import Workspace

        db_ws = await session.get(Workspace, ws.id)
        assert db_ws is not None
        db_ws.title = "My Analysis"
        session.add(db_ws)
        await session.flush()

    return ws.id, user_id, code


async def _setup_loose_workspace(
    email: str = "loose@uni.edu",
) -> tuple[UUID, UUID]:
    """Create a loose workspace (no course/activity placement) with owner ACL.

    Returns (workspace_id, user_id).
    """
    from promptgrimoire.db.acl import grant_permission
    from promptgrimoire.db.users import find_or_create_user
    from promptgrimoire.db.workspaces import create_workspace

    user_record, _ = await find_or_create_user(email=email, display_name="Loose User")
    ws = await create_workspace()
    await grant_permission(ws.id, user_record.id, "owner")
    await _add_document(ws.id)

    return ws.id, user_record.id


# ---------------------------------------------------------------------------
# DB query helper
# ---------------------------------------------------------------------------


async def _get_export_job(user_id: UUID, workspace_id: UUID):
    """Fetch the most recent ExportJob for this user+workspace.

    Uses a simple query (not the production ``get_active_job_for_user``)
    to avoid coupling to its datetime-based active/expired filters.
    """
    from sqlmodel import col, select

    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import ExportJob

    async with get_session() as session:
        stmt = (
            select(ExportJob)
            .where(
                ExportJob.user_id == user_id,
                ExportJob.workspace_id == workspace_id,
            )
            .order_by(col(ExportJob.created_at).desc())
            .limit(1)
        )
        return (await session.exec(stmt)).first()


def _expected_filename(meta, export_date: date = FIXED_DATE) -> str:
    """Build expected filename from workspace metadata using the real policy."""
    return build_pdf_export_stem(
        PdfExportFilenameContext(
            course_code=meta.course_code,
            activity_title=meta.activity_title,
            workspace_title=meta.workspace_title,
            owner_display_name=meta.owner_display_name,
            export_date=export_date,
        )
    )


def _apply_export_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply environment mocks shared by all export filename tests."""
    import promptgrimoire.pages.annotation.pdf_export as pdf_mod

    monkeypatch.setattr(pdf_mod, "_server_local_export_date", lambda: FIXED_DATE)
    monkeypatch.setattr(pdf_mod, "_start_export_polling", lambda *_a, **_kw: None)
    # _extract_response_markdown now reads from the CRDT mirror (sync),
    # but the test harness has no CRDT state. Response text feeds
    # notes_latex (pdf_export.py:499), not the filename under test,
    # so this mock is inert for the filename assertion.

    def _no_crdt_markdown(_state: object) -> str:
        return ""

    monkeypatch.setattr(pdf_mod, "_extract_response_markdown", _no_crdt_markdown)


async def _click_export_and_wait_for_job(
    nicegui_user: User,
    user_id: UUID,
    ws_id: UUID,
) -> ExportJob:
    """Click Export PDF and poll DB until the ExportJob appears.

    NiceGUI dispatches async click handlers as background tasks, so
    the handler may still be running when ``_fire_event_listeners_async``
    returns. We poll the DB for the job instead of assuming synchronous
    completion.
    """
    btn = _find_by_testid(nicegui_user, "export-pdf-btn")
    assert btn is not None
    await _fire_event_listeners_async(btn, "click")

    async def _poll() -> ExportJob | None:
        return await _get_export_job(user_id, ws_id)

    job = await wait_for(_poll, timeout=10.0)
    assert isinstance(job, ExportJob), (
        "No ExportJob created after 10s — export handler bailed"
    )
    return job


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnnotateTabExportFilename:
    """Placed workspace export: filename follows policy, not workspace_{uuid}."""

    @pytest.mark.asyncio
    async def test_annotate_export_uses_policy_filename(
        self, nicegui_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Click Export PDF → ExportJob in DB has policy-derived filename.

        Positive border: filename contains course code + activity + owner + date.
        Negative border: filename is NOT ``workspace_{uuid}``.
        """
        email = "exporter@uni.edu"
        ws_id, user_id, _course_code = await _setup_placed_workspace(email=email)

        _apply_export_mocks(monkeypatch)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "export-pdf-btn")

        job = await _click_export_and_wait_for_job(nicegui_user, user_id, ws_id)

        filename = job.payload["filename"]

        from promptgrimoire.db.workspaces import get_workspace_export_metadata

        meta = await get_workspace_export_metadata(ws_id)
        assert meta is not None
        expected = _expected_filename(meta)

        assert filename == expected
        assert filename != f"workspace_{ws_id}"


class TestRespondTabExportFilename:
    """Respond tab export yields identical filename for the same workspace."""

    @pytest.mark.asyncio
    async def test_respond_tab_same_filename(
        self, nicegui_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Switch to Respond tab, export → same filename as Annotate tab.

        Feature border: filename is workspace-derived, not tab-derived.
        """
        email = "respond@uni.edu"
        ws_id, user_id, _course_code = await _setup_placed_workspace(
            email=email, activity_title="Respond Activity"
        )

        _apply_export_mocks(monkeypatch)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "export-pdf-btn")

        # Switch to Respond tab
        await _should_see_testid(nicegui_user, "tab-respond")
        _click_testid(nicegui_user, "tab-respond")
        await _should_see_testid(nicegui_user, "export-pdf-btn")

        job = await _click_export_and_wait_for_job(nicegui_user, user_id, ws_id)

        filename = job.payload["filename"]

        from promptgrimoire.db.workspaces import get_workspace_export_metadata

        meta = await get_workspace_export_metadata(ws_id)
        assert meta is not None
        expected = _expected_filename(meta)

        assert filename == expected
        assert filename != f"workspace_{ws_id}"


class TestLooseWorkspaceExportFilename:
    """Unplaced workspace uses fallback filename, never workspace_{uuid}."""

    @pytest.mark.asyncio
    async def test_loose_workspace_uses_fallback_policy(
        self, nicegui_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Export from loose workspace → fallback segments in filename.

        Positive border: filename contains "Unplaced" and the fixed date.
        Negative border: filename is NOT ``workspace_{uuid}``.
        """
        email = "loose@uni.edu"
        ws_id, user_id = await _setup_loose_workspace(email=email)

        _apply_export_mocks(monkeypatch)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await wait_for_annotation_load(nicegui_user)
        await _should_see_testid(nicegui_user, "export-pdf-btn")

        job = await _click_export_and_wait_for_job(nicegui_user, user_id, ws_id)

        filename = job.payload["filename"]

        assert filename != f"workspace_{ws_id}"
        assert "Unplaced" in filename
        assert "20260309" in filename
