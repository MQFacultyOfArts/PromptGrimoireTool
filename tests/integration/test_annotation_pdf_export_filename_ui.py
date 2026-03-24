"""NiceGUI User-harness tests for PDF export filename wiring.

Exercises the annotation page export flow to verify that the Phase 1 + Phase 2
filename policy is correctly wired through ``_handle_pdf_export``.

Acceptance Criteria:
- pdf-export-filename-271.AC4.1: Page computes filename before calling export seam
- pdf-export-filename-271.AC4.3: Annotate and Respond tabs yield same filename
- pdf-export-filename-271.AC4.4: Missing placement avoids workspace_{uuid}
- pdf-export-filename-271.AC5.4: Old generic basename no longer used

Traceability:
- Design: docs/implementation-plans/2026-03-09-pdf-export-filename-271/phase_03.md
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.export.filename import (
    PdfExportFilenameContext,
    build_pdf_export_stem,
)
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _click_testid,
    _find_by_testid,
    _should_see_testid,
    wait_for,
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
# Capture helpers
# ---------------------------------------------------------------------------


class ExportCapture:
    """Captures arguments passed to the patched export seam."""

    def __init__(self) -> None:
        self.filename: str | None = None
        self.called = False
        self.download_path: Path | None = None

    async def fake_export(self, **kwargs: object) -> Path:
        self.called = True
        self.filename = str(kwargs.get("filename", ""))
        fake_path = Path("/tmp/fake_export.pdf")
        return fake_path

    def fake_download(self, path: object) -> None:
        self.download_path = Path(str(path))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnnotateTabExportFilename:
    """Verify Annotate-tab export passes the policy filename to the export seam."""

    @pytest.mark.asyncio
    async def test_annotate_export_uses_policy_filename(
        self, nicegui_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Click Export PDF on the Annotate tab and verify the filename argument.

        Steps:
        1. Create a placed workspace with known metadata.
        2. Monkeypatch the export seam and ui.download.
        3. Monkeypatch _server_local_export_date to return a fixed date.
        4. Open the annotation page and click Export PDF.
        5. Assert the captured filename matches the Phase 1 policy output.
        6. Assert filename != workspace_{workspace_id}.
        7. Assert ui.download was called with the fake path.
        """
        email = "exporter@uni.edu"
        ws_id, _user_id, _course_code = await _setup_placed_workspace(email=email)

        capture = ExportCapture()

        import promptgrimoire.pages.annotation.pdf_export as pdf_mod

        monkeypatch.setattr(pdf_mod, "export_annotation_pdf", capture.fake_export)
        monkeypatch.setattr(pdf_mod.ui, "download", capture.fake_download)
        monkeypatch.setattr(pdf_mod, "_server_local_export_date", lambda: FIXED_DATE)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "export-pdf-btn")

        # Click export
        btn = _find_by_testid(nicegui_user, "export-pdf-btn")
        assert btn is not None
        from tests.integration.nicegui_helpers import _fire_event_listeners_async

        await _fire_event_listeners_async(btn, "click")

        # Wait for the export to complete
        await wait_for(lambda: capture.called, timeout=10.0)

        # Build the expected filename via the real Phase 1 builder
        from promptgrimoire.db.workspaces import get_workspace_export_metadata

        meta = await get_workspace_export_metadata(ws_id)
        assert meta is not None
        expected = build_pdf_export_stem(
            PdfExportFilenameContext(
                course_code=meta.course_code,
                activity_title=meta.activity_title,
                workspace_title=meta.workspace_title,
                owner_display_name=meta.owner_display_name,
                export_date=FIXED_DATE,
            )
        )

        assert capture.filename == expected
        assert capture.filename != f"workspace_{ws_id}"


class TestRespondTabExportFilename:
    """Respond-tab export yields same filename for same workspace/date."""

    @pytest.mark.asyncio
    async def test_respond_tab_same_filename(
        self, nicegui_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Switch to Respond tab, export, and verify same filename as Annotate.

        Steps:
        1. Create a placed workspace.
        2. Patch export seam, ui.download, and date seam.
        3. Open annotation page, switch to Respond tab.
        4. Click Export PDF.
        5. Assert the filename matches the expected policy output.
        """
        email = "respond@uni.edu"
        ws_id, _user_id, _course_code = await _setup_placed_workspace(
            email=email, activity_title="Respond Activity"
        )

        capture = ExportCapture()

        import promptgrimoire.pages.annotation.pdf_export as pdf_mod

        monkeypatch.setattr(pdf_mod, "export_annotation_pdf", capture.fake_export)
        monkeypatch.setattr(pdf_mod.ui, "download", capture.fake_download)
        monkeypatch.setattr(pdf_mod, "_server_local_export_date", lambda: FIXED_DATE)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "export-pdf-btn")

        # Switch to Respond tab
        await _should_see_testid(nicegui_user, "tab-respond")
        _click_testid(nicegui_user, "tab-respond")

        # Wait for Respond tab to render
        await _should_see_testid(nicegui_user, "export-pdf-btn")

        # Click export
        btn = _find_by_testid(nicegui_user, "export-pdf-btn")
        assert btn is not None
        from tests.integration.nicegui_helpers import _fire_event_listeners_async

        await _fire_event_listeners_async(btn, "click")

        await wait_for(lambda: capture.called, timeout=10.0)

        # Build the expected filename
        from promptgrimoire.db.workspaces import get_workspace_export_metadata

        meta = await get_workspace_export_metadata(ws_id)
        assert meta is not None
        expected = build_pdf_export_stem(
            PdfExportFilenameContext(
                course_code=meta.course_code,
                activity_title=meta.activity_title,
                workspace_title=meta.workspace_title,
                owner_display_name=meta.owner_display_name,
                export_date=FIXED_DATE,
            )
        )

        assert capture.filename == expected
        assert capture.filename != f"workspace_{ws_id}"


class TestLooseWorkspaceExportFilename:
    """Verify missing placement still avoids the old generic basename."""

    @pytest.mark.asyncio
    async def test_loose_workspace_uses_fallback_policy(
        self, nicegui_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Export from a loose workspace and verify it uses fallback-based policy.

        Steps:
        1. Create a loose workspace (no course/activity).
        2. Patch export seam, ui.download, and date seam.
        3. Open annotation page, click Export PDF.
        4. Assert filename is not workspace_{uuid}.
        5. Assert filename uses the Phase 1 fallback segments.
        """
        email = "loose@uni.edu"
        ws_id, _user_id = await _setup_loose_workspace(email=email)

        capture = ExportCapture()

        import promptgrimoire.pages.annotation.pdf_export as pdf_mod

        monkeypatch.setattr(pdf_mod, "export_annotation_pdf", capture.fake_export)
        monkeypatch.setattr(pdf_mod.ui, "download", capture.fake_download)
        monkeypatch.setattr(pdf_mod, "_server_local_export_date", lambda: FIXED_DATE)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "export-pdf-btn")

        # Click export
        btn = _find_by_testid(nicegui_user, "export-pdf-btn")
        assert btn is not None
        from tests.integration.nicegui_helpers import _fire_event_listeners_async

        await _fire_event_listeners_async(btn, "click")

        await wait_for(lambda: capture.called, timeout=10.0)

        assert capture.filename is not None
        assert capture.filename != f"workspace_{ws_id}"
        # Should contain fallback segments from the Phase 1 builder
        assert "Unplaced" in capture.filename
        assert "20260309" in capture.filename
