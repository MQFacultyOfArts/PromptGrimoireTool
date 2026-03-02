"""User and role management commands."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import typer
from rich.console import Console

if TYPE_CHECKING:
    from datetime import datetime

admin_app = typer.Typer(help="User, role, and course enrollment management.")

# ---------------------------------------------------------------------------
# Helper functions (migrated from cli_legacy.py)
# ---------------------------------------------------------------------------


def _format_last_login(dt: datetime | None) -> str:
    """Format a last_login timestamp for display."""
    if dt is None:
        return "Never"
    return dt.strftime("%Y-%m-%d %H:%M")


async def _find_course(code: str, semester: str):
    """Look up a course by code + semester. Returns None if not found."""
    from sqlmodel import select

    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Course

    async with get_session() as session:
        result = await session.exec(
            select(Course).where(Course.code == code).where(Course.semester == semester)
        )
        return result.first()


async def _require_user(email: str, con: Console):
    """Look up user by email or exit with error."""
    from promptgrimoire.db.users import get_user_by_email

    user = await get_user_by_email(email)
    if user is None:
        con.print(f"[red]Error:[/] no user found with email '{email}'")
        con.print("[dim]User must log in at least once.[/]")
        sys.exit(1)
    return user


async def _require_course(code: str, semester: str, con: Console):
    """Look up course by code+semester or exit with error."""
    course = await _find_course(code, semester)
    if course is None:
        con.print(f"[red]Error:[/] no course found: {code} {semester}")
        sys.exit(1)
    return course


async def _update_stytch_metadata(
    user,
    trusted_metadata: dict,
    *,
    console: Console,
) -> bool:
    """Update a user's trusted_metadata in Stytch.

    Returns True on success, False if Stytch is not configured or update fails.
    """
    from promptgrimoire.auth import get_auth_client
    from promptgrimoire.config import get_settings

    settings = get_settings()
    if not settings.stytch.default_org_id:
        console.print(
            "[yellow]Warning:[/] STYTCH__DEFAULT_ORG_ID not set, skipping Stytch update"
        )
        return False

    if not user.stytch_member_id:
        console.print(
            f"[yellow]Warning:[/] No stytch_member_id for '{user.email}'. "
            "User must log in via SSO first."
        )
        return False

    auth_client = get_auth_client()
    result = await auth_client.update_member_trusted_metadata(
        organization_id=settings.stytch.default_org_id,
        member_id=user.stytch_member_id,
        trusted_metadata=trusted_metadata,
    )

    if result.success:
        console.print(f"[green]Updated Stytch[/] trusted_metadata for '{user.email}'")
        return True
    console.print(f"[red]Stytch update failed:[/] {result.error}")
    return False


# ---------------------------------------------------------------------------
# Command functions (migrated from cli_legacy.py)
# ---------------------------------------------------------------------------


async def _cmd_list(
    *,
    include_all: bool = False,
    console: Console | None = None,
) -> None:
    """List users as a Rich table."""
    from rich.table import Table

    from promptgrimoire.db.users import list_all_users, list_users

    con = console or Console()
    users = await list_all_users() if include_all else await list_users()

    if not users:
        con.print("[yellow]No users found.[/]")
        return

    table = Table(title="Users")
    table.add_column("Email", style="cyan")
    table.add_column("Name")
    table.add_column("Admin")
    table.add_column("Last Login")

    for u in users:
        table.add_row(
            u.email,
            u.display_name,
            "[green]Yes[/]" if u.is_admin else "No",
            _format_last_login(u.last_login),
        )

    con.print(table)


async def _cmd_create(
    email: str,
    *,
    name: str | None = None,
    console: Console | None = None,
) -> None:
    """Create a new user."""
    from promptgrimoire.db.users import find_or_create_user

    con = console or Console()
    display_name = name or email.split("@", maxsplit=1)[0].replace(".", " ").title()
    user, created = await find_or_create_user(email=email, display_name=display_name)
    if created:
        con.print(f"[green]Created[/] user '{email}' ({display_name}, id={user.id})")
    else:
        con.print(f"[yellow]Already exists:[/] '{email}' (id={user.id})")


async def _cmd_show(
    email: str,
    *,
    console: Console | None = None,
) -> None:
    """Show a single user's details and course enrollments."""
    from rich.table import Table

    from promptgrimoire.db.courses import get_course_by_id, list_user_enrollments

    con = console or Console()
    user = await _require_user(email, con)

    con.print(f"\n[bold]{user.display_name}[/] ({user.email})")
    con.print(f"  Admin: {'[green]Yes[/]' if user.is_admin else 'No'}")
    con.print(f"  Last login: {_format_last_login(user.last_login)}")
    con.print(f"  ID: [dim]{user.id}[/]")

    enrollments = await list_user_enrollments(user.id)
    if not enrollments:
        con.print("\n  [dim]No course enrollments.[/]")
        return

    table = Table(title="Enrollments")
    table.add_column("Course")
    table.add_column("Semester")
    table.add_column("Role")

    for e in enrollments:
        course = await get_course_by_id(e.course_id)
        if course:
            table.add_row(course.code, course.semester, e.role)
        else:
            table.add_row(f"[dim]{e.course_id}[/]", "?", e.role)

    con.print(table)


async def _cmd_admin(
    email: str,
    *,
    remove: bool = False,
    console: Console | None = None,
) -> None:
    """Set or remove admin status for a user (local DB + Stytch)."""
    from promptgrimoire.db.users import set_admin as db_set_admin

    con = console or Console()
    user = await _require_user(email, con)

    if remove:
        await db_set_admin(user.id, False)
        con.print(f"[green]Removed[/] admin from '{email}' (local DB).")
        await _update_stytch_metadata(user, {"is_admin": False}, console=con)
    else:
        await db_set_admin(user.id, True)
        con.print(f"[green]Granted[/] admin to '{email}' (local DB).")
        await _update_stytch_metadata(user, {"is_admin": True}, console=con)


async def _cmd_instructor(
    email: str,
    *,
    remove: bool = False,
    console: Console | None = None,
) -> None:
    """Set or remove instructor status via Stytch trusted_metadata."""
    con = console or Console()
    user = await _require_user(email, con)

    if remove:
        metadata = {"eduperson_affiliation": ""}
    else:
        metadata = {"eduperson_affiliation": "staff"}

    success = await _update_stytch_metadata(user, metadata, console=con)
    if success:
        action = "Removed" if remove else "Granted"
        con.print(f"[green]{action}[/] instructor for '{email}'.")
    elif not remove:
        con.print(
            "[dim]Tip: user must log in via SSO once before instructor can be set.[/]"
        )


async def _cmd_enroll(
    email: str,
    code: str,
    semester: str,
    *,
    role: str = "student",
    console: Console | None = None,
) -> None:
    """Enroll a user in a course."""
    from promptgrimoire.db.courses import DuplicateEnrollmentError, enroll_user

    con = console or Console()
    user = await _require_user(email, con)
    course = await _require_course(code, semester, con)

    try:
        await enroll_user(course_id=course.id, user_id=user.id, role=role)
        con.print(f"[green]Enrolled[/] '{email}' in {code} {semester} as {role}.")
    except DuplicateEnrollmentError:
        con.print(f"[yellow]Already enrolled:[/] '{email}' in {code} {semester}.")


async def _cmd_unenroll(
    email: str,
    code: str,
    semester: str,
    *,
    console: Console | None = None,
) -> None:
    """Remove a user from a course."""
    from promptgrimoire.db.courses import unenroll_user

    con = console or Console()
    user = await _require_user(email, con)
    course = await _require_course(code, semester, con)

    removed = await unenroll_user(course_id=course.id, user_id=user.id)
    if removed:
        con.print(f"[green]Removed[/] '{email}' from {code} {semester}.")
    else:
        con.print(f"[yellow]Not enrolled:[/] '{email}' in {code} {semester}.")


async def _cmd_role(
    email: str,
    code: str,
    semester: str,
    new_role: str,
    *,
    console: Console | None = None,
) -> None:
    """Change a user's role in a course."""
    from promptgrimoire.db.courses import update_user_role

    con = console or Console()
    user = await _require_user(email, con)
    course = await _require_course(code, semester, con)

    result = await update_user_role(
        course_id=course.id,
        user_id=user.id,
        role=new_role,
    )
    if result:
        con.print(
            f"[green]Updated[/] '{email}' role to {new_role} in {code} {semester}."
        )
    else:
        con.print(f"[yellow]Not enrolled:[/] '{email}' in {code} {semester}.")


# ---------------------------------------------------------------------------
# Typer command wrappers
# ---------------------------------------------------------------------------


@admin_app.command("list")
def list_users(
    include_all: bool = typer.Option(
        False, "--all", help="Include users who haven't logged in"
    ),
) -> None:
    """List all users."""
    asyncio.run(_cmd_list(include_all=include_all))


@admin_app.command("show")
def show(
    email: str = typer.Argument(..., help="User email address"),
) -> None:
    """Show user details and enrollments."""
    asyncio.run(_cmd_show(email))


@admin_app.command("create")
def create(
    email: str = typer.Argument(..., help="User email address"),
    name: str | None = typer.Option(
        None, help="Display name (default: derived from email)"
    ),
) -> None:
    """Create a new user."""
    asyncio.run(_cmd_create(email, name=name))


@admin_app.command("admin")
def admin(
    email: str = typer.Argument(..., help="User email address"),
    remove: bool = typer.Option(False, "--remove", help="Remove admin status"),
) -> None:
    """Set or remove admin status."""
    asyncio.run(_cmd_admin(email, remove=remove))


@admin_app.command("instructor")
def instructor(
    email: str = typer.Argument(..., help="User email address"),
    remove: bool = typer.Option(False, "--remove", help="Remove instructor status"),
) -> None:
    """Set or remove instructor status (updates Stytch)."""
    asyncio.run(_cmd_instructor(email, remove=remove))


@admin_app.command("enroll")
def enroll(
    email: str = typer.Argument(..., help="User email address"),
    code: str = typer.Argument(..., help="Course code (e.g. LAWS1100)"),
    semester: str = typer.Argument(..., help="Semester (e.g. 2026-S1)"),
    role: str = typer.Option("student", help="Role (default: student)"),
) -> None:
    """Enroll user in a course."""
    asyncio.run(_cmd_enroll(email, code, semester, role=role))


@admin_app.command("unenroll")
def unenroll(
    email: str = typer.Argument(..., help="User email address"),
    code: str = typer.Argument(..., help="Course code"),
    semester: str = typer.Argument(..., help="Semester"),
) -> None:
    """Remove user from a course."""
    asyncio.run(_cmd_unenroll(email, code, semester))


@admin_app.command("role")
def role(
    email: str = typer.Argument(..., help="User email address"),
    code: str = typer.Argument(..., help="Course code"),
    semester: str = typer.Argument(..., help="Semester"),
    new_role: str = typer.Argument(..., help="New role"),
) -> None:
    """Change user's role in a course."""
    asyncio.run(_cmd_role(email, code, semester, new_role))
