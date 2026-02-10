#!/usr/bin/env python3
"""Post-write hook to run ruff and ty on Python files (read-only checks).

This hook runs after any Write or Edit operation on .py files:
1. ruff format (format code)
2. ruff check (report issues WITHOUT autofix)
3. ty check (type checking)

Note: Autofix (--fix) is intentionally NOT used here to avoid removing
"unused" imports before all files are written. The Stop hook runs
comprehensive linting with --fix when Claude finishes work.

Exit codes:
- 0: Success (or non-Python file, skipped)
- 2: Lint warnings shown to Claude (PostToolUse exit 2 cannot block, only shows stderr)
"""

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 1

    # Get the file path from tool_input
    file_path = input_data.get("tool_input", {}).get("file_path", "")

    # Only process .py files
    if not file_path.endswith(".py"):
        return 0

    # Verify file exists
    path = Path(file_path)
    if not path.exists():
        return 0

    # Skip linting if file has merge conflict markers — ruff will always
    # fail on them, and the error output just wastes context.
    content = path.read_text(errors="replace")
    if "<<<<<<< " in content:
        return 0

    errors = []

    # Step 1: ruff format
    result = subprocess.run(
        ["uv", "run", "--quiet", "ruff", "format", file_path],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ruff format failed:\n{result.stderr}")

    # Step 2: ruff check (report issues, no autofix)
    result = subprocess.run(
        ["uv", "run", "--quiet", "ruff", "check", file_path],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ruff check issues:\n{result.stdout}{result.stderr}")

    # Step 3: ty check (via uvx)
    result = subprocess.run(
        ["uvx", "--quiet", "ty", "check", file_path],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ty check failed:\n{result.stdout}{result.stderr}")

    if errors:
        error_summary = "\n".join(errors)
        msg = f"Lint/type errors in {file_path}:\n{error_summary}"
        # Exit 2 to show warnings to Claude (PostToolUse can't block, tool already ran)
        print(msg, file=sys.stderr)
        return 2

    print(json.dumps({"continue": True, "suppressOutput": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
