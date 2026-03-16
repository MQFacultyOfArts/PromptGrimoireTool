"""User and role management commands."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path  # noqa: TC003 -- Typer resolves annotations at runtime
from typing import TYPE_CHECKING

import typer
from rich.console import Console

if TYPE_CHECKING:
    from datetime import datetime

    from promptgrimoire.db.models import Course, User

admin_app = typer.Typer(help="User, role, and course enrollment management.")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_last_login(dt: datetime | None) -> str:
    """Format a last_login timestamp for display."""
    if dt is None:
        return "Never"
    return dt.strftime("%Y-%m-%d %H:%M")


async def _find_course(code: str, semester: str) -> Course | None:
    """Look up a course by code + semester. Returns None if not found."""
    from sqlmodel import select

    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Course

    async with get_session() as session:
        result = await session.exec(
            select(Course).where(Course.code == code).where(Course.semester == semester)
        )
        return result.first()


async def _require_user(email: str, con: Console) -> User:
    """Look up user by email or exit with error."""
    from promptgrimoire.db.users import get_user_by_email

    user = await get_user_by_email(email)
    if user is None:
        con.print(f"[red]Error:[/] no user found with email '{email}'")
        con.print("[dim]User must log in at least once.[/]")
        sys.exit(1)
    return user


async def _require_course(code: str, semester: str, con: Console) -> Course:
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
# Command handlers
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

    is_admin = not remove
    await db_set_admin(user.id, is_admin)
    action = "Removed" if remove else "Granted"
    con.print(
        f"[green]{action}[/] admin {'from' if remove else 'to'} '{email}' (local DB)."
    )
    await _update_stytch_metadata(user, {"is_admin": is_admin}, console=con)


async def _cmd_instructor(
    email: str,
    *,
    remove: bool = False,
    console: Console | None = None,
) -> None:
    """Set or remove instructor status via Stytch trusted_metadata."""
    con = console or Console()
    user = await _require_user(email, con)

    affiliation = "" if remove else "staff"
    success = await _update_stytch_metadata(
        user, {"eduperson_affiliation": affiliation}, console=con
    )
    action = "Removed" if remove else "Granted"
    if success:
        con.print(f"[green]{action}[/] instructor for '{email}'.")
    elif not remove:
        con.print(
            "[dim]Tip: user must log in via SSO once before instructor can be set.[/]"
        )


async def _cmd_ban(
    email: str,
    *,
    console: Console | None = None,
) -> None:
    """Ban a user: set DB flag, update Stytch metadata, revoke sessions, kick."""
    import httpx

    from promptgrimoire.auth import get_auth_client
    from promptgrimoire.config import get_settings
    from promptgrimoire.db.users import set_banned

    con = console or Console()
    user = await _require_user(email, con)

    if user.is_admin:
        con.print("[yellow]Warning:[/] target is an admin user")

    await set_banned(user.id, True)
    await _update_stytch_metadata(user, {"banned": "true"}, console=con)

    # Revoke Stytch sessions
    if user.stytch_member_id:
        auth_client = get_auth_client()
        await auth_client.revoke_member_sessions(member_id=user.stytch_member_id)
    else:
        con.print(
            "[yellow]Warning:[/] No stytch_member_id, skipping session revocation."
        )

    # Kick active UI clients
    settings = get_settings()
    secret = settings.admin.admin_api_secret.get_secret_value()
    if secret:
        base_url = settings.app.base_url
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.post(
                    f"{base_url}/api/admin/kick",
                    json={"user_id": str(user.id)},
                    headers={"Authorization": f"Bearer {secret}"},
                )
                kick_data = resp.json()
                con.print(
                    f"[green]Banned[/] '{email}'. "
                    f"{kick_data.get('kicked', 0)} client(s) kicked."
                )
        except Exception as exc:
            con.print(
                f"[green]Banned[/] '{email}'. "
                f"[yellow]Warning:[/] kick endpoint failed: {exc}"
            )
    else:
        con.print(
            f"[green]Banned[/] '{email}'. "
            "[dim]ADMIN_API_SECRET not set, skipping kick.[/]"
        )


async def _cmd_unban(
    email: str,
    *,
    console: Console | None = None,
) -> None:
    """Unban a user: clear DB flag and Stytch metadata."""
    from promptgrimoire.db.users import set_banned

    con = console or Console()
    user = await _require_user(email, con)

    await set_banned(user.id, False)
    await _update_stytch_metadata(user, {"banned": ""}, console=con)
    con.print(f"[green]Unbanned[/] '{email}'.")


async def _cmd_list_banned(
    *,
    console: Console | None = None,
) -> None:
    """Display all banned users. Placeholder — implemented in Task 3."""
    con = console or Console()
    con.print("[dim]Not yet implemented.[/]")


async def _cmd_enroll_bulk(
    xlsx_file: Path,
    code: str,
    semester: str,
    *,
    role: str = "student",
    force: bool = False,
    console: Console | None = None,
) -> None:
    """Bulk-enrol students from a Moodle Grades XLSX export."""
    from rich.table import Table

    from promptgrimoire.db.enrolment import StudentIdConflictError, bulk_enrol
    from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError, parse_xlsx

    con = console or Console()

    # Parse XLSX
    data = xlsx_file.read_bytes()
    try:
        entries = parse_xlsx(data)
    except EnrolmentParseError as exc:
        for err in exc.errors:
            con.print(f"[red]Error:[/] {err}")
        sys.exit(1)

    # Resolve course
    course = await _require_course(code, semester, con)

    # Bulk enrol
    try:
        report = await bulk_enrol(entries, course.id, role=role, force=force)
    except StudentIdConflictError as exc:
        for email, old, new in exc.conflicts:
            con.print(f"[red]Conflict:[/] {email}: existing={old!r}, new={new!r}")
        con.print("\n[dim]Hint: use --force to overwrite conflicting student IDs.[/]")
        sys.exit(1)

    # Warnings for force-overwritten IDs
    if force and report.student_id_warnings:
        for email, old, new in report.student_id_warnings:
            con.print(
                f"[yellow]Warning:[/] {email}: student ID changed {old!r} -> {new!r}"
            )

    # Summary table
    table = Table(title="Enrolment Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Entries processed", str(report.entries_processed))
    table.add_row("Users created", str(report.users_created))
    table.add_row("Users existing", str(report.users_existing))
    table.add_row("Enrolments created", str(report.enrolments_created))
    table.add_row("Enrolments skipped", str(report.enrolments_skipped))
    table.add_row("Groups created", str(report.groups_created))
    table.add_row("Group memberships", str(report.group_memberships_created))
    if report.student_ids_overwritten:
        table.add_row(
            "[yellow]Student IDs overwritten[/]",
            str(report.student_ids_overwritten),
        )
    con.print(table)


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


@admin_app.command("ban")
def ban(
    email: str = typer.Argument(None, help="User email to ban"),
    list_banned: bool = typer.Option(False, "--list", help="List all banned users"),
) -> None:
    """Ban a user or list banned users."""
    if list_banned:
        asyncio.run(_cmd_list_banned())
    elif email:
        asyncio.run(_cmd_ban(email))
    else:
        Console().print("[red]Error:[/] Provide an email or use --list")
        raise typer.Exit(code=1)


@admin_app.command("unban")
def unban(
    email: str = typer.Argument(..., help="User email to unban"),
) -> None:
    """Unban a user."""
    asyncio.run(_cmd_unban(email))


@admin_app.command("enroll-bulk")
def enroll_bulk(
    xlsx_file: Path = typer.Argument(..., help="Path to Moodle Grades XLSX export"),  # noqa: B008 -- standard Typer pattern
    code: str = typer.Argument(..., help="Course code (e.g. LAWS1100)"),
    semester: str = typer.Argument(..., help="Semester (e.g. 2026-S1)"),
    role: str = typer.Option("student", help="Enrolment role (default: student)"),
    force: bool = typer.Option(False, "--force", help="Override student ID conflicts"),
) -> None:
    """Bulk-enrol students from a Moodle Grades XLSX export."""
    asyncio.run(_cmd_enroll_bulk(xlsx_file, code, semester, role=role, force=force))


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


# ---------------------------------------------------------------------------
# Webhook test
# ---------------------------------------------------------------------------


@admin_app.command("webhook")
def webhook() -> None:
    """Send a test alert to the configured Discord webhook and show the response."""
    import asyncio

    import httpx

    from promptgrimoire.config import get_settings
    from promptgrimoire.logging_discord import DiscordAlertProcessor

    console = Console()
    url = get_settings().alerting.discord_webhook_url
    if not url:
        console.print("[red]ALERTING__DISCORD_WEBHOOK_URL is not set in .env[/red]")
        raise typer.Exit(code=1)

    # Build a test payload directly
    processor = DiscordAlertProcessor(webhook_url=url)
    payload = processor._build_payload(
        "error",
        {
            "event": "webhook_test_alert",
            "level": "error",
            "operation": "admin_webhook",
            "exc_info": "RuntimeError: Test alert from `uv run grimoire admin webhook`",
        },
    )

    async def _send() -> int:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code

    console.print(f"[bold]Posting to {url[:60]}...[/bold]")
    status = asyncio.run(_send())
    if status in (200, 204):
        console.print(f"[green]Discord returned {status} — check your channel.[/green]")
    else:
        console.print(f"[red]Discord returned {status} — check the webhook URL.[/red]")
        raise typer.Exit(code=1)
