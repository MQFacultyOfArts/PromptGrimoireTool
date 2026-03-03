"""Development data seeding commands."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
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
        display_name="Test Instructor",
    )
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
        ("instructor@uni.edu", "Test Instructor", "coordinator"),
        ("admin@example.com", "Admin User", "coordinator"),
        ("student@uni.edu", "Test Student", "student"),
        ("test@example.com", "Test User", "student"),
    ]

    for email, name, role in mock_users:
        u, created = await find_or_create_user(email=email, display_name=name)
        if email == "admin@example.com" and not u.is_admin:
            u.is_admin = True
            async with get_session() as session:
                session.add(u)
                await session.commit()
        status = "[green]Created" if created else "[yellow]Exists"
        console.print(f"{status}:[/] {email}")

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

    await update_course(course.id, default_copy_protection=True)
    console.print("[green]Enabled:[/] default copy protection on course")


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

        await init_db()

        _user, course = await _seed_user_and_course()
        await _seed_enrolment_and_weeks(course)

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
