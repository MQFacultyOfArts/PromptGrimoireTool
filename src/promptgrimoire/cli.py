"""Command-line utilities for PromptGrimoire development.

Provides pytest wrappers with logging and timing for debugging test failures.
Also includes admin bootstrap commands.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def test_debug() -> None:
    """Run pytest with debug flags, capturing output to a log file.

    Flags applied:
        -x: Stop on first failure
        --lf: Run last-failed tests first
        --durations=10: Show 10 slowest tests
        --tb=short: Shorter tracebacks

    Output saved to: test-failures.log

    Usage:
        uv run test-debug           # Run with defaults
        uv run test-debug -v        # Add verbosity
        uv run test-debug tests/unit  # Specific path
    """
    log_path = Path("test-failures.log")
    start_time = datetime.now()

    # Build pytest args: our defaults + user args
    default_args = ["-x", "--lf", "--durations=10", "--tb=short"]
    user_args = sys.argv[1:]
    all_args = ["uv", "run", "pytest", *default_args, *user_args]

    header = f"""{"=" * 60}
Test Debug Run
Started: {start_time.isoformat()}
Command: {" ".join(all_args[2:])}
{"=" * 60}

"""
    print(header, end="")

    # Run pytest as subprocess, tee to both terminal and log
    with log_path.open("w") as log_file:
        log_file.write(header)
        log_file.flush()

        # Use Popen to stream output in real-time
        process = subprocess.Popen(
            all_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output line by line
        for line in process.stdout or []:
            print(line, end="")
            log_file.write(line)
            log_file.flush()

        process.wait()
        exit_code = process.returncode

        # Footer
        end_time = datetime.now()
        duration = end_time - start_time
        footer = f"""
{"=" * 60}
Finished: {end_time.isoformat()}
Duration: {duration}
Exit code: {exit_code}
{"=" * 60}
"""
        print(footer, end="")
        log_file.write(footer)

    print(f"\nLog saved to: {log_path}")
    sys.exit(exit_code)


def test_all() -> None:
    """Run full test suite with timing.

    Output saved to: test-all.log
    """
    log_path = Path("test-all.log")
    start_time = datetime.now()

    default_args = ["--durations=10", "-v"]
    user_args = sys.argv[1:]
    all_args = ["uv", "run", "pytest", *default_args, *user_args]

    header = f"""{"=" * 60}
Full Test Suite
Started: {start_time.isoformat()}
Command: {" ".join(all_args[2:])}
{"=" * 60}

"""
    print(header, end="")

    with log_path.open("w") as log_file:
        log_file.write(header)
        log_file.flush()

        process = subprocess.Popen(
            all_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in process.stdout or []:
            print(line, end="")
            log_file.write(line)
            log_file.flush()

        process.wait()
        exit_code = process.returncode

        end_time = datetime.now()
        duration = end_time - start_time
        footer = f"""
{"=" * 60}
Finished: {end_time.isoformat()}
Duration: {duration}
Exit code: {exit_code}
{"=" * 60}
"""
        print(footer, end="")
        log_file.write(footer)

    print(f"\nLog saved to: {log_path}")
    sys.exit(exit_code)


def set_admin() -> None:
    """Set a user as admin by email.

    Usage:
        uv run set-admin user@example.com
    """
    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: uv run set-admin <email>")
        sys.exit(1)

    email = sys.argv[1]

    if not os.environ.get("DATABASE_URL"):
        print("Error: DATABASE_URL not set")
        sys.exit(1)

    async def _set_admin() -> None:
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session, init_db
        from promptgrimoire.db.models import User

        await init_db()

        async with get_session() as session:
            result = await session.exec(select(User).where(User.email == email))
            user = result.one_or_none()

            if user is None:
                print(f"Error: No user found with email '{email}'")
                print("User must log in at least once before being set as admin.")
                sys.exit(1)
                return  # unreachable, but helps type checker

            if user.is_admin:
                print(f"User '{email}' is already an admin.")
                return

            user.is_admin = True
            session.add(user)
            await session.commit()
            print(f"Success: '{email}' is now an admin.")

    asyncio.run(_set_admin())
