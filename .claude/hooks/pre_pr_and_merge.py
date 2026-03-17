#!/usr/bin/env python3
"""PreToolUse hook: require E2E + smoke tests before PR creation or merge to main.

Gates two operations:
1. `gh pr create` — requires full test suite to pass first
2. `git merge` to main — same gate

Uses a stamp-file approach for background execution:
- First attempt: blocks the command, launches tests in background
- Subsequent attempts: checks stamp file for recent pass/fail
- Stamp expires after 1 hour

Exit codes:
- 0: Allowed (not a gated command, or tests recently passed)
- 2: Blocked — tests running or failed
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

STAMP_DIR = Path(__file__).parent
STAMP_PASS = STAMP_DIR / ".e2e_passed"
STAMP_FAIL = STAMP_DIR / ".e2e_failed"
STAMP_RUNNING = STAMP_DIR / ".e2e_running"
STAMP_MAX_AGE = 3600  # 1 hour


def _extract_command(input_data: dict) -> str:
    return input_data.get("tool_input", {}).get("command", "")


def _strip_heredocs_and_strings(command: str) -> str:
    """Strip heredoc bodies and quoted strings to avoid false matches.

    Commit messages often contain 'git merge' or 'gh pr create' as text
    inside heredocs (e.g. commit message body). We only want to match
    actual shell commands, not string content.
    """
    # Strip heredoc bodies: $(cat <<'EOF' ... EOF\n)
    stripped = re.sub(
        r"\$\(cat\s+<<['\"]?(\w+)['\"]?\n.*?\n\1\s*\)",
        "",
        command,
        flags=re.DOTALL,
    )
    # Strip -m "..." arguments (double-quoted commit messages)
    stripped = re.sub(r'-m\s+"[^"]*"', "", stripped)
    # Strip -m '...' arguments (single-quoted commit messages)
    stripped = re.sub(r"-m\s+'[^']*'", "", stripped)
    return stripped


def _is_pr_create(command: str) -> bool:
    return "gh pr create" in _strip_heredocs_and_strings(command)


def _is_merge_to_main(command: str) -> bool:
    cmd = _strip_heredocs_and_strings(command)
    if ("checkout main" in cmd or "switch main" in cmd) and "git merge" in cmd:
        return True

    if "git merge" in cmd and "main" not in cmd:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                cwd=os.environ.get("CLAUDE_PROJECT_DIR", "."),
            )
            if result.returncode == 0 and result.stdout.strip() == "main":
                return True
        except subprocess.TimeoutExpired, FileNotFoundError:
            pass

    return False


def _stamp_age(path: Path) -> float | None:
    """Return age in seconds, or None if stamp doesn't exist."""
    if not path.exists():
        return None
    return time.time() - path.stat().st_mtime


def _clean_stamps() -> None:
    for stamp in (STAMP_PASS, STAMP_FAIL, STAMP_RUNNING):
        stamp.unlink(missing_ok=True)


def _launch_tests_background(project_dir: str) -> None:
    """Launch e2e all in background, write stamp on completion."""
    # Write a runner script that records pass/fail
    runner = STAMP_DIR / ".e2e_runner.sh"
    runner.write_text(f"""#!/bin/bash
cd "{project_dir}"
uv run grimoire e2e all > "{STAMP_DIR}/.e2e_output.log" 2>&1
rc=$?
if [ $rc -eq 0 ]; then
    touch "{STAMP_PASS}"
    rm -f "{STAMP_FAIL}" "{STAMP_RUNNING}"
else
    tail -100 "{STAMP_DIR}/.e2e_output.log" > "{STAMP_FAIL}"
    rm -f "{STAMP_PASS}" "{STAMP_RUNNING}"
fi
rm -f "{runner}"
""")
    runner.chmod(0o755)

    STAMP_RUNNING.touch()
    subprocess.Popen(
        [str(runner)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _check_stamps(action: str, project_dir: str) -> int:
    """Check stamp files and return exit code. 0 = allow, 2 = block."""
    # Check for recent pass stamp
    pass_age = _stamp_age(STAMP_PASS)
    if pass_age is not None and pass_age < STAMP_MAX_AGE:
        print(
            f"Tests passed {int(pass_age)}s ago — {action} allowed.",
            file=sys.stderr,
        )
        STAMP_PASS.unlink(missing_ok=True)  # consume the stamp
        print(json.dumps({"continue": True}))
        return 0

    # Check for recent failure
    fail_age = _stamp_age(STAMP_FAIL)
    if fail_age is not None and fail_age < STAMP_MAX_AGE:
        output = STAMP_FAIL.read_text()
        _clean_stamps()
        msg = f"BLOCKED: {action} — tests FAILED. Fix failures and retry.\n\n{output}"
        print(msg, file=sys.stderr)
        return 2

    # Check if tests are already running
    running_age = _stamp_age(STAMP_RUNNING)
    if running_age is not None and running_age < STAMP_MAX_AGE:
        mins = int(running_age // 60)
        msg = (
            f"BLOCKED: {action} — tests already running "
            f"({mins}m elapsed). Retry when complete."
        )
        print(msg, file=sys.stderr)
        return 2

    # No recent stamp — launch tests in background
    _clean_stamps()
    _launch_tests_background(project_dir)
    msg = (
        f"BLOCKED: {action} — launched `e2e all` in background. "
        f"Retry this command after tests complete."
    )
    print(msg, file=sys.stderr)
    return 2


def main() -> int:
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    command = _extract_command(input_data)
    if not command:
        return 0

    is_pr = _is_pr_create(command)
    is_merge = _is_merge_to_main(command)

    if not is_pr and not is_merge:
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return 0

    action = "PR creation" if is_pr else "merge to main"
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    return _check_stamps(action, project_dir)


if __name__ == "__main__":
    sys.exit(main())
