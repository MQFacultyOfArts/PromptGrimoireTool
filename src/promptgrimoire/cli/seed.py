"""Development data seeding commands."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.db.models import Activity, Course, User

console = Console()

seed_app = typer.Typer(help="Seed development data.")


async def _seed_user_and_course() -> tuple[User, Course]:
    """Create instructor user and course. Returns (user, course)."""
    from sqlmodel import select

    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Course
    from promptgrimoire.db.users import find_or_create_user

    user, user_created = await find_or_create_user(
        email="instructor@uni.edu",
        display_name="María García-López",
    )
    if not user_created and user.display_name != "María García-López":
        async with get_session() as session:
            session.add(user)
            user.display_name = "María García-López"
            await session.commit()
            await session.refresh(user)
    status = "[green]Created" if user_created else "[yellow]Exists"
    console.print(f"{status}:[/] instructor@uni.edu (id={user.id})")

    # Check for existing course first (code is not unique — same
    # code may appear in different semesters)
    async with get_session() as session:
        result = await session.exec(
            select(Course)
            .where(Course.code == "LAWS1100")
            .where(Course.semester == "2026-S1")
        )
        course = result.first()

    if course:
        console.print(f"[yellow]Course exists:[/] LAWS1100 (id={course.id})")
    else:
        course = await create_course(code="LAWS1100", name="Torts", semester="2026-S1")
        console.print(f"[green]Created course:[/] LAWS1100 (id={course.id})")

    return user, course


async def _seed_enrolment_and_weeks(course: Course) -> None:
    """Enrol mock users and create weeks with activities."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import (
        DuplicateEnrollmentError,
        enroll_user,
        update_course,
    )
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.users import find_or_create_user
    from promptgrimoire.db.weeks import create_week

    # Seed all mock users and enrol them
    mock_users = [
        ("instructor@uni.edu", "María García-López", "coordinator"),
        ("admin@example.com", "Admin User", "coordinator"),
        ("student@uni.edu", "José Núñez", "student"),
        ("test@example.com", "Wei Zhang", "student"),
    ]

    for email, name, role in mock_users:
        u, created = await find_or_create_user(email=email, display_name=name)
        if not created and u.display_name != name:
            async with get_session() as session:
                session.add(u)
                u.display_name = name
                await session.commit()
                await session.refresh(u)
        if email == "admin@example.com" and not u.is_admin:
            u.is_admin = True
            async with get_session() as session:
                session.add(u)
                await session.commit()
        status = "[green]Created" if created else "[yellow]Exists"
        console.print(f"{status}:[/] {email} ({u.display_name})")

        try:
            await enroll_user(course_id=course.id, user_id=u.id, role=role)
            console.print(f"  [green]Enrolled:[/] {email} as {role}")
        except DuplicateEnrollmentError:
            console.print(f"  [yellow]Already enrolled:[/] {email}")

    from sqlmodel import select

    from promptgrimoire.db.models import Week

    async with get_session() as session:
        result = await session.exec(select(Week).where(Week.course_id == course.id))
        existing_weeks = list(result.all())

    if existing_weeks:
        console.print(f"[yellow]Weeks exist:[/] {len(existing_weeks)} in course")
        return

    week1 = await create_week(course_id=course.id, week_number=1, title="Introduction")
    # Publish week 1; week 2 stays draft (is_published defaults to False)
    week1.is_published = True
    async with get_session() as session:
        session.add(week1)
        await session.commit()
    week2 = await create_week(
        course_id=course.id, week_number=2, title="Client Interviews"
    )
    console.print(f"[green]Created weeks:[/] 1, 2 (ids={week1.id}, {week2.id})")

    desc = "Read the interview transcript and annotate key issues."
    activity = await create_activity(
        week_id=week1.id,
        title="Annotate Becky Bennett Interview",
        description=desc,
        copy_protection=True,
    )
    console.print(f"[green]Created activity:[/] {activity.title} (id={activity.id})")

    await _seed_tags_for_activity(activity)
    await _seed_template_document(activity.template_workspace_id)

    await update_course(course.id, default_copy_protection=True)
    console.print("[green]Enabled:[/] default copy protection on course")


async def _seed_template_document(workspace_id: UUID) -> None:
    """Add a sample source document to the template workspace.

    Idempotent: skips if any documents already exist.
    """
    from promptgrimoire.db.workspace_documents import add_document, list_documents

    existing = await list_documents(workspace_id)
    if existing:
        console.print("[yellow]Document exists:[/] skipping document seed")
        return

    sample_html = (
        "<h1>Becky Bennett — Initial Client Interview</h1>"
        "<p>The following is a transcript of the initial interview with "
        "Becky Bennett regarding a workplace injury claim.</p>"
        "<h2>Background</h2>"
        "<p>Becky Bennett, aged 34, was employed as a warehouse "
        "supervisor at QuickShip Logistics Pty Ltd in Parramatta, NSW. "
        "On 15 March 2025, she suffered a back injury while lifting "
        "a heavy pallet that had been incorrectly stacked by a "
        "co-worker.</p>"
        "<h2>Interview Notes</h2>"
        "<p><strong>Q:</strong> Can you tell me what happened on the "
        "day of the incident?</p>"
        "<p><strong>A:</strong> I was doing my usual rounds checking "
        "the loading bay. There was a pallet that looked unstable — "
        "it was stacked way too high, maybe two metres. I tried to "
        "restack the top boxes to make it safe before the forklift "
        "came through. When I lifted the first box, I felt something "
        "go in my lower back. I couldn't straighten up.</p>"
        "<p><strong>Q:</strong> Had you reported the unsafe stacking "
        "before?</p>"
        "<p><strong>A:</strong> Yes, multiple times. I'd sent emails "
        "to my manager, Dave Chen, about the stacking problems. The "
        "casual staff weren't being trained properly. I've got copies "
        "of those emails.</p>"
        "<p><strong>Q:</strong> What happened after the injury?</p>"
        "<p><strong>A:</strong> Dave called an ambulance. I was taken "
        "to Westmead Hospital. They did scans and said I had a disc "
        "herniation at L4-L5. I've been off work since then. My GP "
        "says I need surgery but the workers' comp insurer is "
        "disputing whether it's work-related.</p>"
    )

    await add_document(
        workspace_id=workspace_id,
        type="source",
        content=sample_html,
        source_type="paste",
        title="Becky Bennett Interview Transcript",
    )
    console.print("[green]Seeded:[/] template document (Becky Bennett interview)")


async def _seed_tags_for_activity(activity: Activity) -> None:
    """Seed Legal Case Brief tag group and tags for an activity's template workspace.

    Idempotent: skips if any TagGroups already exist for the workspace.
    """
    from sqlmodel import select

    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Tag, TagGroup

    workspace_id = activity.template_workspace_id

    # Check if tags already exist (idempotent guard)
    async with get_session() as session:
        result = await session.exec(
            select(TagGroup).where(TagGroup.workspace_id == workspace_id)
        )
        if result.first() is not None:
            console.print("[yellow]Tags exist:[/] skipping tag seed")
            return

    # Legal Case Brief tags in three logical groups.
    # Colours are colorblind-accessible (Matplotlib tab10 palette).
    group_defs: list[tuple[str, str | None, list[tuple[str, str]]]] = [
        (
            "Case ID",
            "#4a90d9",
            [
                ("Jurisdiction", "#1f77b4"),
                ("Procedural History", "#ff7f0e"),
                ("Decision", "#e377c2"),
                ("Order", "#7f7f7f"),
            ],
        ),
        (
            "Analysis",
            "#d9534f",
            [
                ("Legally Relevant Facts", "#2ca02c"),
                ("Legal Issues", "#d62728"),
                ("Reasons", "#9467bd"),
                ("Court's Reasoning", "#8c564b"),
            ],
        ),
        (
            "Sources",
            "#5cb85c",
            [
                ("Domestic Sources", "#bcbd22"),
                ("Reflection", "#17becf"),
            ],
        ),
    ]

    async with get_session() as session:
        tag_count = 0
        for group_idx, (group_name, group_color, tags) in enumerate(group_defs):
            group = TagGroup(
                workspace_id=workspace_id,
                name=group_name,
                color=group_color,
                order_index=group_idx,
            )
            session.add(group)
            await session.flush()

            for tag_idx, (name, color) in enumerate(tags):
                tag = Tag(
                    workspace_id=workspace_id,
                    group_id=group.id,
                    name=name,
                    color=color,
                    locked=True,
                    order_index=tag_idx,
                )
                session.add(tag)
                tag_count += 1

        await session.flush()

        # Sync workspace counter columns after bulk insert
        from promptgrimoire.db.models import Workspace

        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            workspace.next_tag_order = tag_count
            workspace.next_group_order = len(group_defs)
            session.add(workspace)
            await session.flush()

    console.print(f"[green]Seeded tags:[/] {len(group_defs)} groups, {tag_count} tags")


@seed_app.command("run")
def run() -> None:
    """Seed the database with development data. Idempotent."""
    from promptgrimoire.config import get_settings

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    async def _seed() -> None:
        from promptgrimoire.db.engine import init_db
        from promptgrimoire.db.models import Activity

        await init_db()

        _user, course = await _seed_user_and_course()
        await _seed_enrolment_and_weeks(course)

        # Seed template document (idempotent, runs even if weeks
        # already exist — the document may be missing from earlier seeds).
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session

        async with get_session() as session:
            result = await session.exec(
                select(Activity).where(
                    Activity.title == "Annotate Becky Bennett Interview"
                )
            )
            activity = result.first()
        if activity:
            await _seed_template_document(activity.template_workspace_id)

        console.print()
        console.print(
            Panel(
                f"[bold]Login:[/] http://localhost:8080/login\n"
                f"[bold]Email:[/] instructor@uni.edu\n"
                f"[bold]Course:[/] http://localhost:8080/courses/{course.id}",
                title="Seed Data Ready",
            )
        )

    asyncio.run(_seed())
