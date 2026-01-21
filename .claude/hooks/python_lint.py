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
- 2: Blocking error (lint/type check failed)
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

    errors = []

    # Step 1: ruff format
    result = subprocess.run(
        ["uv", "run", "ruff", "format", file_path],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ruff format failed:\n{result.stderr}")

    # Step 2: ruff check (report issues, no autofix)
    result = subprocess.run(
        ["uv", "run", "ruff", "check", file_path],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ruff check issues:\n{result.stdout}{result.stderr}")

    # Step 3: ty check (via uvx)
    result = subprocess.run(
        ["uvx", "ty", "check", file_path],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"ty check failed:\n{result.stdout}{result.stderr}")

    if errors:
        # Output errors as JSON for Claude to see
        print(json.dumps({"status": "error", "errors": errors}))
        return 2  # Blocking error

    print(json.dumps({"status": "success", "file": file_path}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
