"""Assessment-fixture provisioning shared by the perf probes.

Generalises the Narayan-only scaffolding from the cram probe over any
extracted-workspace fixture (Narayan and Savage today): rehydrate the
fixture, bind it as an Activity template, clone per synthetic student,
and restore the original binding afterwards.

Each fixture JSON is a prod extract (``scripts/extract_workspace.py``)
whose workspace id is fixed, so rehydration is idempotent
(delete-then-reinsert).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

NARAYAN_WORKSPACE_ID = "c7cf540f-53df-407e-b043-cc6f6e30cf5b"
SAVAGE_WORKSPACE_ID = "8b7f15e9-49b8-4da7-bc4c-f1d7e50c5f1f"
CASE_BRIEF_TAG_COUNT = 10


@dataclass(frozen=True)
class AssessmentFixture:
    """One rehydratable assessment workspace fixture."""

    name: str
    workspace_id: str
    json_path: Path


NARAYAN_FIXTURE = AssessmentFixture(
    name="narayan",
    workspace_id=NARAYAN_WORKSPACE_ID,
    json_path=FIXTURES_DIR / "narayan_workspace.json",
)
SAVAGE_FIXTURE = AssessmentFixture(
    name="savage",
    workspace_id=SAVAGE_WORKSPACE_ID,
    json_path=FIXTURES_DIR / "savage_workspace.json",
)


def ensure_fixture_workspace(fixture: AssessmentFixture) -> str:
    """Rehydrate a fixture workspace into the test DB; return its id."""
    from promptgrimoire.config import get_settings

    if not fixture.json_path.exists():
        pytest.skip(
            f"Workspace JSON not found at {fixture.json_path}. "
            "Extract from prod with scripts/extract_workspace.py first."
        )

    from scripts.rehydrate_workspace import rehydrate

    db_url = get_settings().database.url
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)
    result = rehydrate(fixture.json_path, db_url)
    assert result["workspace_id"] == fixture.workspace_id
    return fixture.workspace_id


async def create_template_activity(
    fixture: AssessmentFixture,
    *,
    course_name: str,
) -> tuple[str, str]:
    """Create an Activity whose template workspace is the fixture.

    Returns (activity_id, old_template_id) for later restoration.
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Activity, Workspace
    from promptgrimoire.db.weeks import create_week, publish_week

    suffix = uuid4().hex[:8]
    course = await create_course(
        code=f"CR{suffix[:6].upper()}",
        name=course_name,
        semester="2026-S2",
    )
    week = await create_week(course_id=course.id, week_number=5, title="Week 5")
    await publish_week(week.id)
    activity = await create_activity(week_id=week.id, title=f"{course_name} {suffix}")

    async with get_session() as session:
        db_activity = await session.get(Activity, activity.id)
        assert db_activity is not None
        old_template_id = str(db_activity.template_workspace_id)
        db_activity.template_workspace_id = UUID(fixture.workspace_id)
        session.add(db_activity)

        old_template = await session.get(Workspace, UUID(old_template_id))
        if old_template is not None:
            old_template.activity_id = None
            session.add(old_template)

        fixture_ws = await session.get(Workspace, UUID(fixture.workspace_id))
        assert fixture_ws is not None
        fixture_ws.activity_id = activity.id
        session.add(fixture_ws)

    return str(activity.id), old_template_id


async def restore_template_binding(
    fixture: AssessmentFixture,
    activity_id: str,
    old_template_id: str,
) -> None:
    """Restore the fixture to loose-workspace state after a probe."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Activity, Workspace

    async with get_session() as session:
        activity = await session.get(Activity, UUID(activity_id))
        if activity is not None:
            activity.template_workspace_id = UUID(old_template_id)
            session.add(activity)

        fixture_ws = await session.get(Workspace, UUID(fixture.workspace_id))
        if fixture_ws is not None:
            fixture_ws.activity_id = None
            session.add(fixture_ws)

        old_template = await session.get(Workspace, UUID(old_template_id))
        if old_template is not None:
            old_template.activity_id = UUID(activity_id)
            session.add(old_template)


async def provision_clone_for_email(activity_id: str, email: str) -> str:
    """Create or reuse a user, then clone the template for them."""
    from promptgrimoire.db.users import find_or_create_user
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    user, _ = await find_or_create_user(email, display_name=email.split("@", 1)[0])
    clone, _ = await clone_workspace_from_activity(UUID(activity_id), user.id)
    return str(clone.id)


def fixture_document_words(fixture: AssessmentFixture) -> list[str]:
    """Extract the fixture document's words for needle planning.

    The browser's text walker collapses whitespace, so a needle built
    from single-space-joined words matches what ``find_text_range``
    searches.
    """
    from selectolax.lexbor import LexborHTMLParser

    data = json.loads(fixture.json_path.read_text(encoding="utf-8"))
    html = data["documents"][0]["content"]
    words = LexborHTMLParser(html).text(separator=" ").split()
    min_words_needed = 200
    if len(words) < min_words_needed:
        msg = f"fixture document too short ({len(words)} words)"
        raise RuntimeError(msg)
    return words
