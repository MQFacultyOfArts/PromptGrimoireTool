#!/usr/bin/env python3
"""Stop hook to run comprehensive linting when Claude finishes work.

This hook runs when Claude stops responding, applying autofixes to all
modified Python files. Running at Stop (rather than per-file) prevents
ruff from removing "unused" imports before all files are written.

Exit codes:
- 0: Always (Stop hooks should not block)
"""

import json
import os
import subprocess
import sys


def get_modified_python_files() -> list[str]:
    """Get list of modified .py files from git status."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=os.environ.get("CLAUDE_PROJECT_DIR", "."),
        check=False,
    )
    if result.returncode != 0:
        return []

    files = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        # Format: "XY filename" where X=index, Y=worktree
        status = line[:2]
        filepath = line[3:].strip()
        # Include modified, added, or renamed files
        if (status[0] in "MAR" or status[1] in "MAR") and filepath.endswith(".py"):
            files.append(filepath)
    return files


def main() -> int:
    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"decision": "approve"}))
        return 0

    # Prevent infinite loops if Stop hook already fired
    if input_data.get("stop_hook_active"):
        print(json.dumps({"decision": "approve"}))
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    files = get_modified_python_files()

    if not files:
        print(json.dumps({"decision": "approve"}))
        return 0

    errors = []

    # Step 1: ruff check --fix on all modified files
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "--fix", *files],
        capture_output=True,
        text=True,
        cwd=project_dir,
        timeout=60,
        check=False,
    )
    # Autofix modifies files, don't treat non-zero as error

    # Step 2: ruff format on all modified files
    result = subprocess.run(
        ["uv", "run", "ruff", "format", *files],
        capture_output=True,
        text=True,
        cwd=project_dir,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ruff format issues:\n{result.stderr}")

    # Step 3: ruff check (verify no remaining issues)
    result = subprocess.run(
        ["uv", "run", "ruff", "check", *files],
        capture_output=True,
        text=True,
        cwd=project_dir,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ruff check issues:\n{result.stdout}{result.stderr}")

    # Step 4: ty check on all modified files
    result = subprocess.run(
        ["uvx", "ty", "check", *files],
        capture_output=True,
        text=True,
        cwd=project_dir,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ty check issues:\n{result.stdout}{result.stderr}")

    # Report results (never block Stop)
    if errors:
        error_summary = "\n".join(errors)
        msg = f"Lint issues in {len(files)} file(s):\n{error_summary}"
        print(json.dumps({"decision": "approve", "reason": msg}))
    else:
        print(json.dumps({"decision": "approve"}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
